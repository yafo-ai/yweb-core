# 异常处理模块测试

本目录包含 YWeb 异常处理模块的完整测试套件。

## 测试文件结构

```
test_exceptions/
├── __init__.py                      # 模块初始化
├── test_exceptions.py               # 测试业务异常类
├── test_handlers.py                 # 测试全局异常处理器
├── test_integration.py              # 测试集成场景
├── test_exception_conversion.py     # 测试异常转换
└── README.md                        # 本文件
```

## 测试覆盖范围

### 1. test_exceptions.py - 业务异常类测试

测试所有业务异常类的基本功能：

- ✅ `BusinessException` 基类
- ✅ `AuthenticationException` (401)
- ✅ `AuthorizationException` (403)
- ✅ `ResourceNotFoundException` (404)
- ✅ `ResourceConflictException` (409)
- ✅ `ValidationException` (422)
- ✅ `ServiceUnavailableException` (503)
- ✅ 异常链保留
- ✅ 自定义异常子类

**测试用例数：** 20+

### 2. test_handlers.py - 全局异常处理器测试

测试 FastAPI 全局异常处理器：

- ✅ 业务异常自动转换为 JSON 响应
- ✅ Pydantic 验证异常处理
- ✅ 系统异常处理
- ✅ 调试模式支持
- ✅ 响应格式一致性
- ✅ 多种异常类型集成

**测试用例数：** 25+

### 3. test_integration.py - 集成场景测试

测试实际业务场景中的异常处理：

- ✅ 用户获取场景
- ✅ 用户创建场景（冲突、验证）
- ✅ 用户删除场景（权限检查）
- ✅ 认证场景
- ✅ 异常链在集成中的保留
- ✅ 响应格式一致性

**测试用例数：** 15+

### 4. test_exception_conversion.py - 异常转换测试

测试内部异常转换为业务异常：

- ✅ 数据库异常转换
- ✅ HTTP 异常转换
- ✅ 异常链保留
- ✅ 敏感信息隐藏
- ✅ 上下文信息添加
- ✅ Repository 层模式
- ✅ Service 层模式

**测试用例数：** 12+

## 运行测试

### 运行所有异常处理测试

```bash
# 在项目根目录
pytest tests/test_exceptions/ -v

# 或者使用相对路径
cd tests
pytest test_exceptions/ -v
```

### 运行特定测试文件

```bash
# 测试业务异常类
pytest tests/test_exceptions/test_exceptions.py -v

# 测试全局处理器
pytest tests/test_exceptions/test_handlers.py -v

# 测试集成场景
pytest tests/test_exceptions/test_integration.py -v

# 测试异常转换
pytest tests/test_exceptions/test_exception_conversion.py -v
```

### 运行特定测试类

```bash
# 测试 BusinessException
pytest tests/test_exceptions/test_exceptions.py::TestBusinessException -v

# 测试认证异常
pytest tests/test_exceptions/test_exceptions.py::TestAuthenticationException -v

# 测试全局处理器
pytest tests/test_exceptions/test_handlers.py::TestBusinessExceptionHandler -v
```

### 运行特定测试用例

```bash
# 测试基本异常创建
pytest tests/test_exceptions/test_exceptions.py::TestBusinessException::test_basic_exception -v

# 测试异常响应格式
pytest tests/test_exceptions/test_handlers.py::TestBusinessExceptionHandler::test_business_exception_response -v
```

### 查看测试覆盖率

```bash
# 安装 pytest-cov
pip install pytest-cov

# 运行测试并生成覆盖率报告
pytest tests/test_exceptions/ --cov=yweb.exceptions --cov-report=html

# 查看覆盖率报告
# 打开 htmlcov/index.html
```

### 运行测试并显示详细输出

```bash
# 显示 print 输出
pytest tests/test_exceptions/ -v -s

# 显示失败的详细信息
pytest tests/test_exceptions/ -v --tb=long

# 只运行失败的测试
pytest tests/test_exceptions/ --lf
```

## 测试示例

### 示例 1: 测试业务异常

```python
def test_business_exception():
    """测试业务异常"""
    exc = BusinessException(
        "操作失败",
        code="OPERATION_FAILED",
        details=["详细信息"]
    )

    assert exc.message == "操作失败"
    assert exc.code == "OPERATION_FAILED"
    assert exc.status_code == 400
```

### 示例 2: 测试异常处理器

```python
def test_exception_handler(client):
    """测试异常处理器"""
    response = client.get("/test/business-error")

    assert response.status_code == 400
    data = response.json()

    assert data["status"] == "error"
    assert data["error_code"] == "TEST_ERROR"
```

### 示例 3: 测试异常转换

```python
def test_exception_conversion():
    """测试异常转换"""
    try:
        raise OperationalError("connection failed", None, None)
    except OperationalError as e:
        raise ServiceUnavailableException(
            "数据库服务暂时不可用"
        ) from e
```

## 测试数据

测试使用模拟数据，不依赖真实数据库：

```python
USERS_DB = {
    1: {"id": 1, "username": "admin", "role": "admin"},
    2: {"id": 2, "username": "user1", "role": "user"},
}
```

## 测试配置

### pytest.ini 配置

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

### conftest.py 配置

测试使用 fixtures 来管理测试应用和客户端：

```python
@pytest.fixture
def app():
    """测试应用"""
    return create_test_app()

@pytest.fixture
def client(app):
    """测试客户端"""
    return TestClient(app)
```

## 持续集成

### GitHub Actions 示例

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: 3.9
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov
      - name: Run tests
        run: pytest tests/test_exceptions/ -v --cov=yweb.exceptions
```

## 测试最佳实践

### 1. 测试命名

- 测试文件：`test_*.py`
- 测试类：`Test*`
- 测试函数：`test_*`

### 2. 测试结构

```python
class TestFeature:
    """测试某个功能"""

    def test_normal_case(self):
        """测试正常情况"""
        pass

    def test_edge_case(self):
        """测试边界情况"""
        pass

    def test_error_case(self):
        """测试错误情况"""
        pass
```

### 3. 断言

```python
# 使用明确的断言
assert response.status_code == 400
assert data["error_code"] == "TEST_ERROR"

# 使用 pytest.raises 测试异常
with pytest.raises(BusinessException) as exc_info:
    raise BusinessException("测试")

assert exc_info.value.code == "BUSINESS_ERROR"
```

### 4. Fixtures

```python
@pytest.fixture
def user():
    """用户 fixture"""
    return {"id": 1, "username": "test"}

def test_with_fixture(user):
    """使用 fixture 的测试"""
    assert user["id"] == 1
```

## 故障排查

### 测试失败

```bash
# 查看详细错误信息
pytest tests/test_exceptions/ -v --tb=long

# 进入调试模式
pytest tests/test_exceptions/ --pdb
```

### 导入错误

```bash
# 确保 yweb 包可以被导入
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# 或者安装为开发模式
pip install -e .
```

### 依赖问题

```bash
# 安装测试依赖
pip install pytest pytest-cov fastapi httpx

# 或者从 requirements.txt 安装
pip install -r requirements-dev.txt
```

## 贡献指南

### 添加新测试

1. 在相应的测试文件中添加测试用例
2. 遵循现有的命名和结构约定
3. 确保测试可以独立运行
4. 添加清晰的文档字符串

### 测试覆盖率目标

- 代码覆盖率：> 90%
- 分支覆盖率：> 85%
- 所有公共 API 都应该有测试

## 相关文档

- [异常处理完整指南](../../docs/exception_handling_guide.md)
- [快速参考](../../docs/exception_handling_quick_reference.md)
- [实施报告](../../docs/exception_handling_implementation_report.md)

## 总结

本测试套件提供了完整的异常处理功能测试，包括：

- ✅ 70+ 测试用例
- ✅ 覆盖所有异常类型
- ✅ 测试全局处理器
- ✅ 测试实际业务场景
- ✅ 测试异常转换模式
- ✅ 高代码覆盖率

运行所有测试：

```bash
pytest tests/test_exceptions/ -v
```

预期输出：

```
tests/test_exceptions/test_exceptions.py::TestBusinessException::test_basic_exception PASSED
tests/test_exceptions/test_exceptions.py::TestBusinessException::test_exception_with_code PASSED
...
========================= 70 passed in 2.5s =========================
```

🎉 所有测试通过！
