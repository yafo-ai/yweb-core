# 发布流程说明

本文档描述 yweb 发布到 PyPI 的完整流程，以及 AI 助手在协助发布时必须遵守的规则。

## 一、前置准备

1. **PyPI token**：在 `.pypirc` 中配置好正式 token（`[pypi]` section），推荐使用 "Upload only" 权限的 token。
2. **testpypi token**（可选）：在 `.pypirc` 中配置好 `[testpypi]` section，用于预发布验证。
3. **构建工具**：首次使用需安装 `python -m pip install --upgrade pip build twine`。

## 二、版本号管理

### 版本号规则

遵循 [Semantic Versioning 2.0.0](https://semver.org/lang/zh-CN/)：

| 场景 | 版本号变化 |
|---|---|
| 修复 bug、内部改动、文档补充 | 修订号 +1（0.1.4 → 0.1.5） |
| 新增功能、向后兼容 | 次版本号 +1（0.1.5 → 0.2.0） |
| 破坏性变更（API 不兼容） | 主版本号 +1（0.2.0 → 1.0.0） |

### 版本号必须同步的两个位置

每次发布前必须同时修改这两处：

```
1. pyproject.toml          version = "0.1.5"
2. yweb/version.py         __version__ = "0.1.5"
```

**两处必须一致。**

### CHANGELOG

每次发布后更新根目录下的 `CHANGELOG.md`，在顶部添加新版本的条目，按以下格式：

```markdown
## [0.1.5] - 2026-10-15

### 新增
- xxx

### 修复
- xxx

### 破坏性变更
- xxx
```

## 三、发布命令

在打包根目录（有 `pyproject.toml` 的那层）执行：

```powershell
# 构建并发布到正式 PyPI
.\publish.ps1

# 构建并发布到 testpypi（先验证推荐用这个）
.\publish.ps1 -Repo testpypi

# 只构建不上传（检查产物内容）
.\publish.ps1 -SkipUpload
```

也可以手动执行等价步骤：

```powershell
cd yweb-core/yweb-core

# 清理旧产物
rmdir /s /q dist
rmdir /s /q build

# 构建
python -m build

# 验证产物
dir dist\

# 上传到正式 PyPI
python -m twine upload --config-file .pypirc dist/*

# 或者上传到 testpypi
python -m twine upload --repository testpypi dist/*
```

### 产物验证

上传前可以先看 wheel 里打进去了什么：

```powershell
# 列出 wheel 里的所有文件
python -m zipfile -l dist\yweb-X.X.X-py3-none-any.whl

# 查看 wheel 的元数据（README 内容、版本号等）
python -c "import zipfile; z=zipfile.ZipFile('dist/yweb-X.X.X-py3-none-any.whl'); print(z.read('yweb-X.X.X.dist-info/METADATA').decode('utf-8'))"
```

### PyPI 不允许同版本重复上传

如果上传时报错 `File already exists`，说明这个版本号已经发过了。**必须递增版本号**，不能覆盖。

## 四、AI 助手协助发布时的强制规则

AI 助手在协助用户发布新版本时，**必须**遵守以下流程，禁止跳过任何一步：

### 规则 1：版本号必须先询问用户

AI 在动手修改版本号、构建、上传之前，**必须先向用户确认这次要用什么版本号**。即使 AI 根据改动量推测出了一个合理的版本号，也不能直接用，必须先问。

✅ 正确做法：
> 根据这次的改动（修复打包问题、新增 py.typed），建议版本号从 0.1.4 升到 0.1.5（修订号 +1）。你确认用 0.1.5 吗？

❌ 错误做法：
> 我帮你把版本号改成 0.1.5 然后发布

### 规则 2：构建完成后等用户确认

构建产物出来后，如果不是用 `-SkipUpload`，AI 应该把产物列表展示给用户，再问一次是否确认上传，而不是直接一路跑到 twine upload。

### 规则 3：发 CHANGELOG 前等用户过目

CHANGELOG 的内容由 AI 根据本次改动起草，但必须给用户看一眼确认后再 commit 或作为发布说明使用。

### 规则 4：不要替用户 commit

AI 不应该替用户执行 `git add`、`git commit`、`git push` 操作。版本号修改和 CHANGELOG 更新属于用户代码的一部分，commit 是用户的决策权。

## 五、常见问题

### Q: pyproject.toml 里的 license 字段有 deprecation 警告？
A: setuptools ≥ 77 推荐把 `license = { text = "MIT" }` 改成简单字符串 `license = "MIT"`，同时移除 classifiers 里的 `License :: OSI Approved :: MIT License`。这个在 2027-02-18 前迁移即可，不影响当前构建和上传。

### Q: .pypirc 里的 token 安全吗？
A: PyPI 推荐用 token 而不是密码。建议使用 "Upload only" 权限的 token，即使泄露也只能上传不能删除包。`.pypirc` 文件**必须**加入 `.gitignore`，不要提交到仓库。

### Q: testpypi 和正式 PyPI 有什么区别？
A: testpypi.org 是 PyPI 的测试环境，独立账号、独立数据库。包名在 testpypi 被占用不影响正式 PyPI。推荐先在 testpypi 发一遍确认 README 展示、版本号、包名都对，再发正式。

### Q: 用户 `pip install yweb` 时会下载什么？
A: 默认下载最新版本。如果用户想锁定版本：`pip install yweb==0.1.5`。
