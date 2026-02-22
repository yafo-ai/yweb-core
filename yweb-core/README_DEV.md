# yweb-core 安装与开发指南

## 目录

- [安装指南](#安装指南)
  - [方式一：可编辑模式安装（开发推荐）](#方式一可编辑模式安装开发推荐)
  - [方式二：从本地路径安装](#方式二从本地路径安装)
  - [方式三：从 Git 仓库安装](#方式三从-git-仓库安装)
  - [方式四：打包发布安装](#方式四打包发布安装)
  - [验证安装](#验证安装)
- [开发指南](#开发指南)
  - [开发环境设置](#开发环境设置)
  - [项目结构](#项目结构)
  - [代码规范](#代码规范)
  - [运行测试](#运行测试)
  - [代码质量检查](#代码质量检查)
  - [调试技巧](#调试技巧)
- [常见问题](#常见问题)

---

## 安装指南

### 方式一：可编辑模式安装（开发推荐）

适用于需要同时开发框架和业务项目的场景。

```bash
# 进入你的项目目录
cd /path/to/your-project

# 以可编辑模式安装（推荐使用 compat 模式，确保 IDE 能正确导航源码）
pip install -e /path/to/yweb-core --config-settings editable_mode=compat
```

**Windows PowerShell 示例：**
```powershell
cd E:\GPT\y-sso\y-sso-system
pip install -e E:\GPT\y-sso\yweb-core --config-settings editable_mode=compat
```

> **为什么需要 `--config-settings editable_mode=compat`？**
>
> 新版 setuptools 的 editable 安装默认使用 "finder" 机制（在 `.pth` 文件中注册自定义
> import finder），Python 运行时能正常工作，但 IDE 的静态分析器（如 Pylance/Pyright）
> 不会执行 `.pth` 中的 Python 代码，导致**无法导航到源码、无法跳转定义、import 飘红**。
>
> 加上 `--config-settings editable_mode=compat` 后，setuptools 会退回传统模式，
> 在 `.pth` 文件中直接写入源码路径（如 `E:\GPT\y-sso\yweb-core`），
> IDE 就能正确识别和导航了。

**优点：**
- ✅ 修改 yweb-core 代码后立即生效
- ✅ 无需重新安装
- ✅ 方便调试和开发
- ✅ IDE 能正确导航到框架源码（使用 compat 模式）

### 方式二：从本地路径安装

适用于框架已稳定，不需要频繁修改的场景。

```bash
pip install /path/to/yweb-core
```

### 方式三：从 Git 仓库安装

适用于框架托管在 Git 仓库的场景。

```bash
# 从 GitHub 安装
pip install git+https://github.com/your-username/yweb-core.git

# 从私有仓库安装（带认证）
pip install git+https://<token>@github.com/your-username/yweb-core.git

# 安装特定分支
pip install git+https://github.com/your-username/yweb-core.git@branch-name

# 安装特定标签
pip install git+https://github.com/your-username/yweb-core.git@v1.0.0
```

### 方式四：打包发布安装

适用于正式发布和生产环境。

**1. 构建包：**
```bash
cd /path/to/yweb-core
pip install build
python -m build
```

**2. 安装构建的包：**
```bash
pip install dist/yweb-0.1.0-py3-none-any.whl
```

**3. 发布到 PyPI（可选）：**
```bash
pip install twine
twine upload dist/*
```

发布后可直接通过 pip 安装：
```bash
pip install yweb
```

### 验证安装

```bash
pip show yweb
```

预期输出：
```
Name: yweb
Version: 0.1.0
Summary: A lightweight web framework based on FastAPI
Location: /path/to/site-packages  # 或可编辑模式下显示源码路径
```

**Python 中验证：**
```python
import yweb
print(yweb.__version__)  # 输出: 0.1.0
```

---

## 开发指南

### 开发环境设置

**1. 克隆仓库：**
```bash
git clone https://github.com/your-username/yweb-core.git
cd yweb-core
```

**2. 创建虚拟环境：**
```bash
# 使用 venv
python -m venv .venv

# Windows 激活
.venv\Scripts\activate

# Linux/macOS 激活
source .venv/bin/activate
```

**3. 安装开发依赖：**
```bash
# 安装运行时依赖 + 开发依赖
pip install -r requirements-dev.txt

# 或使用 pip install -e 安装可编辑模式
pip install -e . --config-settings editable_mode=compat
pip install -r requirements-dev.txt
```

**4. IDE 配置（VS Code / Cursor）：**

确保 `.vscode/settings.json` 包含以下配置：
```json
{
  "python.analysis.extraPaths": ["./yweb"],
  "python.testing.pytestEnabled": true,
  "python.testing.unittestEnabled": false,
  "python.formatting.provider": "none",
  "[python]": {
    "editor.formatOnSave": true,
    "editor.defaultFormatter": "charliermarsh.ruff"
  }
}
```

### 项目结构

```
yweb-core/
├── yweb/                     # 核心包
│   ├── orm/                  # ORM（Active Record、分页、软删除、Mixin）
│   ├── auth/                 # 认证（JWT 双 Token、setup_auth 一键启用）
│   ├── permission/           # 权限（RBAC、角色继承）
│   ├── organization/         # 组织管理（setup_organization 一键启用）
│   ├── cache/                # 缓存（@cached 装饰器、自动失效）
│   ├── scheduler/            # 定时任务（Cron / Interval / Once、Builder 模式）
│   ├── response/             # 统一响应（Resp 快捷类、DTO）
│   ├── exceptions/           # 异常处理（Err 快捷类、全局处理器）
│   ├── middleware/           # 中间件（请求日志、ID 追踪、性能监控、IP 控制）
│   ├── storage/              # 文件存储（本地 / OSS / S3）
│   ├── log/                  # 日志（时间+大小轮转、敏感数据过滤）
│   ├── config/               # 配置（YAML + 环境变量、AppSettings）
│   ├── validators/           # 验证约束（类似 .NET MVC 特性）
│   └── utils/                # 工具（加密、文件大小解析）
├── docs/                     # 文档
├── tests/                    # 测试
│   ├── test_auth/            # 认证模块测试
│   ├── test_cache/           # 缓存模块测试
│   ├── test_config/          # 配置模块测试
│   ├── test_exceptions/      # 异常模块测试
│   ├── test_log/             # 日志模块测试
│   ├── test_middleware/      # 中间件测试
│   ├── test_organization/    # 组织模块测试
│   ├── test_orm/             # ORM 测试
│   ├── test_permission/      # 权限模块测试
│   ├── test_response/        # 响应模块测试
│   ├── test_scheduler/       # 定时任务测试
│   ├── test_storage/         # 存储模块测试
│   └── test_utils/           # 工具模块测试
├── examples/                 # 示例代码
├── pyproject.toml            # 项目配置（依赖、pytest、ruff、mypy）
├── pytest.ini                # pytest 配置
├── requirements.txt          # 运行时依赖
└── requirements-dev.txt      # 开发依赖
```

### 代码规范

**格式化工具：** 使用 Ruff 进行代码格式化和检查。

**命名规范：**
| 类型 | 规范 | 示例 |
|------|------|------|
| 模块 | 小写下划线 | `base_model.py` |
| 类 | 大驼峰 | `BaseModel` |
| 函数/方法 | 小写下划线 | `get_user_by_id` |
| 常量 | 大写下划线 | `MAX_RETRY_COUNT` |
| 私有属性 | 单下划线前缀 | `_internal_cache` |

**导入顺序（isort 规范）：**
```python
# 标准库
import os
import sys
from typing import Optional, List

# 第三方库
from fastapi import FastAPI, Depends
from sqlalchemy import Column, String

# 本地模块
from yweb.orm import BaseModel
from yweb.response import Resp
```

**类型注解：**
```python
# 推荐：使用类型注解
def get_user(user_id: int) -> Optional[User]:
    return User.get(user_id)

# 推荐：使用 Type Alias
from typing import TypeAlias
JsonDict: TypeAlias = dict[str, Any]
```

### 运行测试

**运行所有测试：**
```bash
pytest
```

**运行指定模块测试：**
```bash
# 测试 auth 模块
pytest tests/test_auth

# 测试 ORM 模块
pytest tests/test_orm
```

**运行单个测试文件：**
```bash
pytest tests/test_auth/test_jwt.py
```

**运行指定测试函数：**
```bash
pytest tests/test_auth/test_jwt.py::test_create_token
```

**查看测试覆盖率：**
```bash
# 快速测试并查看覆盖率
pytest yweb-core/tests -q --cov=yweb

# 运行测试并生成覆盖率报告
pytest --cov=yweb

# 查看详细覆盖率（显示未覆盖的行号）
pytest --cov=yweb --cov-report=term-missing

# 生成 HTML 覆盖率报告
pytest --cov=yweb --cov-report=html

# 打开 HTML 报告
# Windows
start htmlcov/index.html
# macOS
open htmlcov/index.html
# Linux
xdg-open htmlcov/index.html
```

**测试指定模块的覆盖率：**
```bash
# 测试 auth 模块覆盖率
pytest tests/test_auth --cov=yweb.auth --cov-report=term-missing -q

# 测试 ORM 模块覆盖率
pytest tests/test_orm --cov=yweb.orm --cov-report=term-missing -q
```

**查看已有覆盖率报告：**
```bash
# 查看终端报告（使用上次的 .coverage 文件）
coverage report

# 查看未覆盖的行号
coverage report -m
```

### 代码质量检查

**Ruff 检查：**
```bash
# 检查代码问题
ruff check yweb

# 自动修复可修复的问题
ruff check yweb --fix

# 格式化代码
ruff format yweb
```

**Mypy 类型检查：**
```bash
# 类型检查
mypy yweb
```

**一键检查（推荐）：**
```bash
# 格式化 + 检查 + 类型检查
ruff format yweb && ruff check yweb --fix && mypy yweb
```

### 调试技巧

**1. 使用 pytest 的详细输出：**
```bash
# 显示 print 输出
pytest -s

# 显示详细错误信息
pytest -v --tb=long

# 进入 pdb 调试（失败时）
pytest --pdb
```

**2. 使用 logging 调试：**
```python
from yweb.log import get_logger

logger = get_logger()
logger.debug("调试信息: %s", some_value)
```

**3. 启用 SQL 日志：**

在配置文件中开启 SQL 日志：
```yaml
logging:
  sql_log_enabled: true
```

或在代码中临时启用：
```python
import logging
logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
```

**4. 测试隔离：**

测试使用独立的数据库，避免污染开发数据。测试配置见 `tests/conftest.py`。

---

## 依赖要求

- Python >= 3.8（推荐 Python 3.11，性能最优）
- FastAPI >= 0.100.0
- SQLAlchemy >= 2.0.0
- Pydantic >= 2.0.0
- PyYAML >= 6.0
- python-jose[cryptography] >= 3.3.0

### Python 版本选择建议

| 版本 | 推荐度 | 说明 |
|------|--------|------|
| **3.11** | ⭐⭐⭐⭐⭐ | **最佳选择** - 性能提升显著，生态成熟稳定 |
| 3.10 | ⭐⭐⭐⭐ | 稳定选择，但性能不如 3.11 |
| 3.12 | ⭐⭐⭐ | 最新特性，但第三方库兼容性待完善 |
| 3.8-3.9 | ⭐⭐ | 最低要求，不建议用于新项目 |

完整依赖列表见 `requirements.txt`。

---

## 快速开始

安装完成后，在你的项目中导入使用：

```python
# 导入 ORM 相关
from yweb.orm import BaseModel, init_database, get_db

# 导入响应相关
from yweb.response import OK, BadRequest, NotFound

# 导入中间件
from yweb.middleware import RequestIDMiddleware, PerformanceMonitoringMiddleware

# 导入日志
from yweb.log import setup_logger, api_logger

# 导入配置
from yweb.config import CoreSettings, load_yaml_config
```

详细使用说明请参考 `PROJECT_SUMMARY.md` 或 `docs/` 目录下的文档。

---

## 常见问题

### Q: IDE（VS Code / Cursor）中 `from yweb import ...` 飘红、无法跳转到源码？

这是因为安装时没有使用 compat 模式。执行以下命令重新安装即可：

```bash
pip uninstall yweb -y
pip install -e /path/to/yweb-core --config-settings editable_mode=compat
```

安装后重启 IDE 或重新加载窗口（Ctrl+Shift+P → "Reload Window"）。

**原理**：新版 setuptools 默认的 editable 模式使用 finder 机制，IDE 静态分析器无法识别；compat 模式会直接将源码路径写入 `.pth` 文件，IDE 就能正确解析了。

### Q: 修改了 yweb-core 代码但没有生效？

确认是否使用可编辑模式安装：
```bash
pip show yweb
```
查看 `Editable project location` 字段是否指向源码目录。

### Q: 如何卸载？

```bash
pip uninstall yweb
```

### Q: 如何更新？

**可编辑模式：** 直接修改源码或 git pull 即可。

**其他模式：** 重新执行安装命令，或使用：
```bash
pip install --upgrade /path/to/yweb-core
```

### Q: 测试运行失败，提示数据库连接错误？

检查测试配置文件 `tests/conftest.py`，确保测试数据库配置正确。默认使用内存 SQLite 数据库。

### Q: 如何只运行单元测试或集成测试？

```bash
# 只运行单元测试
pytest -m unit

# 只运行集成测试
pytest -m integration

# 排除慢速测试
pytest -m "not slow"
```

### Q: 如何查看测试覆盖率报告的历史记录？

覆盖率报告保存在 `.coverage` 文件中，每次运行 `pytest --cov` 会覆盖。如需保留历史记录，可以：
```bash
# 生成并保存 HTML 报告
pytest --cov=yweb --cov-report=html --cov-report=xml
```
