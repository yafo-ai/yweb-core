# 测试隔离指南：防止全局状态污染

## 背景

在使用 `sqlalchemy-history`（或类似的全局状态库）时，测试之间可能会相互影响，导致难以排查的测试失败。本文档总结了我们在 `yweb-core` 项目中的实践经验。

---

## 问题：全局状态污染

### 什么是全局状态？

```python
# sqlalchemy-history 的全局状态
from sqlalchemy_history import versioning_manager, make_versioned

# 这些是全局的，一旦设置就会影响整个 Python 进程
make_versioned()  # 注册全局事件监听器
versioning_manager.transaction_cls  # 全局 Transaction 类
versioning_manager.version_class_map  # 全局版本类映射
```

### 污染场景

```
测试A (模块级初始化)          测试B
    │                           │
    ├─ make_versioned()         │
    │   注册全局事件            │
    │                           │
    ├─ 运行测试 ────────────────┼─ 测试B导入了被污染的全局状态
    │   PASS                    │   FAIL ❌
```

### 症状

1. **单独运行测试 PASS，全部运行 FAIL**
2. **测试顺序影响结果**（换个顺序就 PASS/FAIL）
3. **错误信息涉及 "already defined"、"registry" 等**

```
sqlalchemy.exc.InvalidRequestError: Table 'xxx_version' is already defined
sqlalchemy_history.exc.ClassNotVersioned: Article
KeyError: 'User'
```

---

## 解决方案

### 方案对比

| 方案 | 隔离性 | 实现难度 | 推荐场景 |
|------|--------|----------|----------|
| 1. 跳过测试 | ⭐ | ⭐ | 临时方案 |
| 2. 延迟初始化 | ⭐⭐ | ⭐⭐ | 轻度污染 |
| 3. subprocess 隔离 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | **推荐** |
| 4. pytest-forked | ⭐⭐⭐⭐ | ⭐ | Linux/Mac |

---

### 方案 1：跳过测试（临时方案）

```python
import os
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION_TESTS") != "1",
    reason="集成测试需要单独运行"
)
```

**运行方式：**
```bash
# 跳过
pytest tests/ -v

# 单独运行
RUN_INTEGRATION_TESTS=1 pytest tests/test_xxx.py -v
```

**缺点：** 不是真正的解决方案，CI 中需要分开配置。

---

### 方案 2：延迟初始化

将模块级别的初始化代码移到函数/fixture 中：

```python
# ❌ 错误：模块级初始化（导入时执行）
from sqlalchemy_history import make_versioned
make_versioned()  # 立即污染全局状态

# ✅ 正确：延迟初始化
_initialized = False

def _init_models():
    global _initialized
    if _initialized:
        return
    
    from sqlalchemy_history import make_versioned
    make_versioned()
    _initialized = True

# 只在测试实际运行时初始化
class TestXxx:
    @pytest.fixture
    def setup(self):
        _init_models()
        yield
```

**缺点：** 仍然会污染后续测试，只是延迟了污染时机。

---

### 方案 3：subprocess 隔离（推荐）

**原理：** 每个测试在独立的子进程中运行，进程结束后全局状态自动销毁。

```python
import subprocess
import sys
import json

# 测试代码作为字符串
_TEST_CODE = '''
import json
import sys

# 初始化代码（只在子进程中执行）
from sqlalchemy_history import make_versioned
make_versioned()

def run_test():
    # 测试逻辑...
    return {"success": True, "message": "测试通过"}

if __name__ == "__main__":
    result = run_test()
    print(json.dumps(result))
    sys.exit(0 if result["success"] else 1)
'''


def _run_in_subprocess(test_name: str, tmp_path) -> dict:
    """在子进程中运行测试"""
    # 写入临时文件
    test_file = tmp_path / "_test_runner.py"
    test_file.write_text(_TEST_CODE, encoding='utf-8')
    
    # 运行子进程
    result = subprocess.run(
        [sys.executable, str(test_file), test_name],
        capture_output=True,
        text=True,
        cwd=str(tmp_path.parent.parent.parent),  # 项目根目录
    )
    
    # 解析结果
    try:
        return json.loads(result.stdout.strip().split('\n')[-1])
    except json.JSONDecodeError:
        return {"success": False, "stdout": result.stdout, "stderr": result.stderr}


class TestIntegration:
    def test_xxx(self, tmp_path):
        result = _run_in_subprocess("test_xxx", tmp_path)
        assert result["success"], result.get("message")
```

**优点：**
- ✅ 完全隔离，互不影响
- ✅ 子进程结束后状态自动清理
- ✅ 可以和其他测试一起运行
- ✅ 跨平台（Windows/Linux/Mac）

**缺点：**
- 启动子进程有一定开销
- 调试不太方便（需要看子进程输出）

---

### 方案 4：pytest-forked（仅 Linux/Mac）

```bash
pip install pytest-forked
```

```python
import pytest

@pytest.mark.forked
def test_xxx():
    # 在独立进程中运行
    from sqlalchemy_history import make_versioned
    make_versioned()
    # ...
```

**注意：** Windows 不支持 `fork()`，此方案在 Windows 上不可用。

---

## 最佳实践

### 1. 识别全局状态

检查以下模式：

```python
# 模块级别的初始化
make_versioned()
configure_mappers()
create_engine()

# 全局单例
versioning_manager
Base.metadata
```

### 2. 测试文件组织

```
tests/
├── unit/                    # 单元测试（无全局状态）
│   ├── test_xxx.py
│   └── test_yyy.py
├── integration/             # 集成测试（可能有全局状态）
│   └── test_audit.py        # 使用 subprocess 隔离
└── conftest.py
```

### 3. 调试技巧

当测试单独 PASS 但全部运行 FAIL 时：

```bash
# 1. 检查测试顺序
pytest tests/ -v --collect-only

# 2. 打乱顺序运行
pip install pytest-randomly
pytest tests/ -v -p randomly

# 3. 逐步排查
pytest tests/test_a.py tests/test_b.py -v  # 组合运行，找出冲突
```

### 4. CI 配置示例

```yaml
# .github/workflows/test.yml
jobs:
  test:
    steps:
      - name: Run unit tests
        run: pytest tests/unit/ -v
      
      - name: Run integration tests (isolated)
        run: pytest tests/integration/ -v
```

---

## 总结

| 场景 | 推荐方案 |
|------|----------|
| 临时解决 | 方案 1：跳过测试 |
| 轻度污染 | 方案 2：延迟初始化 |
| 重度污染（推荐） | 方案 3：subprocess 隔离 |
| Linux/Mac 环境 | 方案 4：pytest-forked |

**核心原则：** 如果某个库使用了全局状态且难以清理，最可靠的方案是**进程级隔离**。
