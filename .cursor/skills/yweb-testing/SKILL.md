---
name: yweb-testing
description: YWeb 框架 Pytest 单元测试编写规范。适用于 yweb-core 底层框架本身，以及通过 pip install yweb 安装后基于该框架开发的任何上层应用。涵盖测试目录结构、conftest 编写、fixture 模式、ORM 测试、API 测试、Service 测试、Domain 测试、Mock 策略、异步测试等场景。
---

# YWeb Pytest 单元测试编写规范

本 Skill 是 AI 编程助手为 yweb 框架生态编写 pytest 测试文件的**权威指南**。适用于两种场景：

1. **yweb-core 底层框架本身**：测试 ORM、缓存、认证、异常处理等基础模块
2. **基于 yweb 开发的上层应用**：通过 `pip install yweb` 安装框架后，测试应用自身的 API 层、Service 层、Domain 层业务逻辑

> **关于上层应用**：本文档中的"上层应用"指任何通过 `pip install yweb` 引入框架后独立开发的项目。文档中以虚构的示例项目 `my-app` 演示目录结构和代码模板，实际项目名称和结构请根据自身项目调整。上层应用**看不到** yweb-core 的源码和测试文件，只能通过 `from yweb import ...` 使用框架提供的公共 API。

> **核心原则**：测试代码的质量标准与生产代码一致。测试应快速、可靠、可维护、易读。

---

## 1. 测试目录结构

### 1.1 yweb-core 底层框架

```
yweb-core/
├── pytest.ini              # pytest 配置
├── tests/
│   ├── __init__.py
│   ├── conftest.py         # 全局公共 fixtures
│   ├── helpers/            # 测试辅助工具（非测试类）
│   │   ├── __init__.py
│   │   ├── auth_helpers.py
│   │   └── transaction_helpers.py
│   ├── test_orm/
│   │   ├── __init__.py
│   │   ├── unit/           # 单元测试
│   │   │   ├── __init__.py
│   │   │   ├── test_base_model.py
│   │   │   └── test_query.py
│   │   └── integration/    # 集成测试
│   │       ├── __init__.py
│   │       └── test_transaction.py
│   ├── test_auth/
│   ├── test_cache/
│   ├── test_exceptions/
│   └── test_response/
```

### 1.2 上层应用（通过 `pip install yweb` 引入框架的独立项目）

> 上层应用是独立的项目，通过 `pip install yweb` 安装框架，只能使用 `from yweb import ...` 的公共 API。
> 应用看不到 yweb-core 的源码或测试文件，测试目录结构需要自行建立。

```
my-app/                     # 你的项目根目录（名称自定义）
├── pytest.ini              # pytest 配置（需创建）
├── tests/
│   ├── __init__.py
│   ├── conftest.py         # 全局公共 fixtures（数据库、TestClient、认证等）
│   ├── helpers/            # 测试辅助工具
│   │   ├── __init__.py
│   │   ├── factory.py      # 测试数据工厂
│   │   └── auth_utils.py   # 认证辅助
│   ├── test_api/           # API 层测试（HTTP 端点）
│   │   ├── __init__.py
│   │   ├── test_role_api.py
│   │   └── test_user_api.py
│   ├── test_services/      # Service 层测试（业务编排）
│   │   ├── __init__.py
│   │   └── test_auth_service.py
│   ├── test_domain/        # Domain 层测试（领域模型 + 领域服务）
│   │   ├── __init__.py
│   │   ├── test_user_model.py
│   │   └── test_role_service.py
│   └── test_orm/           # ORM 功能测试
│       ├── __init__.py
│       └── test_models.py
```

### 1.3 目录命名规则

- 测试目录以 `test_` 前缀命名，对应被测模块
- 大型模块拆分 `unit/` 和 `integration/` 子目录
- `helpers/` 目录放测试辅助工具（不是测试文件）
- 每个测试目录都要有 `__init__.py`

---

## 2. pytest 配置

### 2.1 pytest.ini

```ini
[pytest]
# 测试发现
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*

# 输出配置
addopts = -v --tb=short

# 标记
markers =
    slow: 标记为慢速测试
    integration: 标记为集成测试
    unit: 标记为单元测试

# 过滤警告
filterwarnings =
    ignore::DeprecationWarning
    ignore::PendingDeprecationWarning
```

### 2.2 常用依赖

```
# requirements-dev.txt
pytest>=8.0
pytest-asyncio>=0.23
pytest-mock>=3.12
pytest-cov>=4.1
httpx>=0.27           # 异步 TestClient 支持
```

---

## 3. 命名规范

### 3.1 测试文件命名

```
test_<模块名>.py        # 例：test_base_model.py、test_role_api.py
```

### 3.2 测试类命名

```python
class TestBaseModel:       # 测试类：Test + 被测类/模块名
class TestRoleService:     # 测试类：Test + 被测服务名
class TestRoleAPI:         # 测试类：Test + 被测 API 名
```

### 3.3 测试方法命名

```python
def test_create_user_with_valid_email(self):        # test_ + 动作 + 条件/场景
def test_delete_role_raises_error_for_system_role(self):
def test_get_user_returns_none_when_not_found(self):
```

### 3.4 非测试类命名（关键！必须遵守！）

> **严重警告**：pytest 的测试发现机制会自动将 `test_*.py` 文件中所有以 `Test` 开头的 class 识别为测试类，并尝试收集其中以 `test_` 开头的方法作为测试用例。如果辅助类、实体类、模型类以 `Test` 开头，pytest 会产生警告或错误。

**规则：只有真正的测试类才以 `Test` 开头，其他所有类一律禁止。**

这条规则适用于测试文件中定义的所有非测试类，包括但不限于：
- **测试用 ORM 模型**（如用于建表的 Model 类）
- **Mock 类 / Stub 类**
- **数据传输对象 / 辅助实体类**
- **工厂类**
- **配置类**

```python
# ✅ 正确 — 非测试类不以 Test 开头
class UserModel(BaseModel):           # 测试用 ORM 模型
class MockUser:                        # Mock 类
class SampleRole:                      # 示例实体
class RoleFactory:                     # 工厂类
class FakeEmailService:                # Fake 类

# ❌ 错误 — pytest 会误识别为测试类并发出警告
class TestUserModel(BaseModel):        # ← 会被 pytest 当作测试类！
class TestHelper:                      # ← 会被 pytest 当作测试类！
class TestData:                        # ← 会被 pytest 当作测试类！
```

> **记忆口诀**：文件名 `test_` 开头，测试类 `Test` 开头，测试方法 `test_` 开头——只有这三者可以用 test 前缀，**其余一切类和函数都不能以 test/Test 开头**。

### 3.5 文档字符串（中文）

```python
class TestBaseModel:
    """BaseModel 基础功能测试"""
    
    def test_model_has_id(self):
        """测试模型创建后自动分配 ID"""
        ...
    
    def test_soft_delete_restore(self):
        """测试软删除后恢复记录"""
        ...
```

---

## 4. conftest.py 编写规范

### 4.1 yweb-core 根 conftest.py 模板

```python
"""
Pytest 公共配置和 Fixtures

提供测试所需的公共资源：
- 数据库连接（内存 SQLite）
- FastAPI 测试客户端
- JWT 相关 fixtures
- Mock 用户
"""

import pytest
import os
import tempfile
from typing import Generator

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, scoped_session
from sqlalchemy.pool import StaticPool

from yweb.orm import CoreModel, BaseModel


# ==================== Pytest Hook：全局初始化 ====================

def pytest_configure(config):
    """全局初始化钩子（最早执行，仅一次）"""
    from yweb.orm import init_versioning, CurrentUserPlugin, is_versioning_initialized
    
    if is_versioning_initialized():
        return
    
    enable_user_tracking = os.getenv('YWEB_TEST_USER_TRACKING', 'true').lower() == 'true'
    if enable_user_tracking:
        init_versioning(plugins=[CurrentUserPlugin()])
    else:
        init_versioning()


# ==================== 数据库 Fixtures ====================

@pytest.fixture(scope="function")
def memory_engine():
    """创建内存数据库引擎（每个测试函数独立）
    
    使用 StaticPool + check_same_thread=False 确保：
    1. 所有操作使用同一个连接
    2. 允许跨线程访问
    """
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(memory_engine) -> Generator[Session, None, None]:
    """创建数据库会话"""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ==================== FastAPI Fixtures ====================

@pytest.fixture
def app():
    """创建测试用 FastAPI 应用"""
    test_app = FastAPI(title="Test App")
    return test_app


@pytest.fixture
def client(app):
    """创建测试客户端"""
    return TestClient(app)


# ==================== 临时文件 Fixtures ====================

@pytest.fixture(scope="session")
def temp_dir():
    """创建临时目录（session 级别）"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def temp_file(temp_dir):
    """临时文件工厂"""
    created_files = []
    
    def _create_file(filename: str, content: str = "") -> str:
        filepath = os.path.join(temp_dir, filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True) if os.path.dirname(filepath) else None
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        created_files.append(filepath)
        return filepath
    
    yield _create_file
    for f in created_files:
        if os.path.exists(f):
            os.remove(f)
```

### 4.2 上层应用 conftest.py 模板（适用于任何基于 yweb 的独立项目）

```python
"""
应用层 Pytest 公共配置和 Fixtures

提供：
- 完整的应用实例（含路由、中间件）
- 已认证的测试客户端
- 测试数据库会话（自动清理）
- 测试用户和角色

注意：上层应用通过 pip install yweb 安装框架，
     只能使用 from yweb import ... 的公共 API。
     以下 import 路径中的 app.xxx 需要替换为你自己项目的实际模块路径。
"""

import pytest
from typing import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import StaticPool

# yweb 框架公共 API（通过 pip install yweb 安装）
from yweb.orm import CoreModel, BaseModel


# ==================== 数据库 Fixtures ====================

@pytest.fixture(scope="function")
def memory_engine():
    """内存数据库引擎"""
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def setup_db(memory_engine):
    """自动初始化数据库（每个测试函数前执行）"""
    BaseModel.metadata.create_all(bind=memory_engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
    session_scope = scoped_session(SessionLocal)
    CoreModel.query = session_scope.query_property()
    yield session_scope
    session_scope.remove()


# ==================== 应用 Fixtures ====================

@pytest.fixture
def app(setup_db):
    """创建完整的测试应用实例
    
    注意：下面的 import 路径需要替换为你自己项目的实际路径，例如：
    - from myproject.main import create_app
    - from app.main import create_app
    """
    from app.main import create_app  # ← 替换为你的项目模块路径
    test_app = create_app()
    return test_app


@pytest.fixture
def client(app) -> TestClient:
    """未认证的测试客户端"""
    return TestClient(app)


@pytest.fixture
def auth_client(app) -> TestClient:
    """已认证的测试客户端（携带 JWT Token）"""
    client = TestClient(app)
    # 创建测试用户并获取 Token
    # token = create_test_token(user_id=1, username="testadmin")
    # client.headers["Authorization"] = f"Bearer {token}"
    return client


# ==================== 测试数据 Fixtures ====================

@pytest.fixture
def sample_user(setup_db):
    """创建测试用户
    
    注意：下面的 import 路径需要替换为你自己项目的用户模型路径
    """
    from app.domain.auth.model.user import User  # ← 替换为你的用户模型路径
    user = User(username="testuser", email="test@example.com")
    user.set_password("Test123456")
    user.add(True)
    return user
```

---

## 5. 测试文件编写模板

### 5.1 ORM 模型测试（通用，适用于 yweb-core 和任何上层应用）

```python
"""UserModel 模块测试

测试用户模型的 CRUD、软删除、查询等功能
"""

import pytest
from sqlalchemy import Column, String, create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import StaticPool

from yweb.orm import CoreModel, BaseModel


# ==================== 测试模型定义 ====================

class UserModel(BaseModel):
    """测试用户模型"""
    __tablename__ = "test_users"
    __table_args__ = {'extend_existing': True}
    
    email = Column(String(200), comment="邮箱")


# ==================== 测试类 ====================

class TestUserModel:
    """用户模型 CRUD 测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """自动初始化数据库会话
        
        标准模式：创建表 → 创建会话 → 设置 query → yield → 清理
        """
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        session_scope = scoped_session(SessionLocal)
        CoreModel.query = session_scope.query_property()
        yield
        session_scope.remove()
    
    def test_create_user(self):
        """测试创建用户"""
        user = UserModel(name="Alice", email="alice@example.com")
        user.add(True)
        
        assert user.id is not None
        assert user.name == "Alice"
        assert user.email == "alice@example.com"
    
    def test_update_user(self):
        """测试更新用户"""
        user = UserModel(name="Bob", email="bob@example.com")
        user.add(True)
        
        user.email = "bob_new@example.com"
        user.update(True)
        
        found = UserModel.get(user.id)
        assert found.email == "bob_new@example.com"
    
    def test_soft_delete_user(self):
        """测试软删除用户"""
        user = UserModel(name="Charlie", email="charlie@example.com")
        user.add(True)
        user_id = user.id
        
        user.delete(True)
        
        # 默认查询过滤已删除记录
        assert UserModel.get(user_id) is None
    
    def test_query_filter(self):
        """测试条件查询"""
        UserModel(name="User1", email="u1@example.com").add(True)
        UserModel(name="User2", email="u2@example.com").add(True)
        
        found = UserModel.query.filter(UserModel.name == "User1").first()
        assert found is not None
        assert found.email == "u1@example.com"
```

### 5.2 API 层测试（上层应用 - import 路径需替换为你的项目）

```python
"""角色管理 API 测试

测试 /api/v1/roles 相关端点
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

from yweb.response import OK, BadRequest, NotFound


# ==================== 测试类 ====================

class TestRoleAPI:
    """角色 API 端点测试"""
    
    @pytest.fixture
    def app(self):
        """创建含角色路由的测试应用"""
        from app.api.v1.role import create_role_router  # ← 替换为你的路由模块
        
        test_app = FastAPI()
        role_router = create_role_router()
        test_app.include_router(role_router, prefix="/api/v1/roles")
        return test_app
    
    @pytest.fixture
    def client(self, app):
        return TestClient(app)
    
    def test_list_roles(self, client):
        """测试获取角色列表"""
        response = client.get("/api/v1/roles")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "success"
    
    def test_create_role_success(self, client):
        """测试创建角色 - 正常情况"""
        payload = {"name": "管理员", "code": "admin", "description": "系统管理员"}
        response = client.post("/api/v1/roles/create", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["code"] == "admin"
    
    def test_create_role_duplicate_code(self, client):
        """测试创建角色 - 编码重复应返回 409"""
        payload = {"name": "管理员", "code": "admin"}
        client.post("/api/v1/roles/create", json=payload)
        
        # 重复创建
        response = client.post("/api/v1/roles/create", json=payload)
        assert response.status_code == 409
    
    def test_delete_system_role_forbidden(self, client):
        """测试删除系统角色 - 应被禁止"""
        response = client.delete("/api/v1/roles/system_admin")
        assert response.status_code in [400, 403]
```

### 5.3 Service 层测试（上层应用 - import 路径需替换为你的项目）

```python
"""认证应用服务测试

测试 AuthApplicationService 的业务编排逻辑
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy import Column, String, create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import StaticPool

from yweb.orm import CoreModel, BaseModel


class TestAuthApplicationService:
    """认证服务测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化测试数据库"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        session_scope = scoped_session(SessionLocal)
        CoreModel.query = session_scope.query_property()
        yield
        session_scope.remove()
    
    @pytest.fixture
    def auth_service(self):
        """创建认证服务实例"""
        from app.services.auth_app import AuthApplicationService  # ← 替换为你的服务模块
        return AuthApplicationService()
    
    def test_register_user_success(self, auth_service):
        """测试用户注册 - 正常流程"""
        result = auth_service.register(
            username="newuser",
            password="Secure123!",
            email="new@example.com"
        )
        assert result is not None
        assert result.username == "newuser"
    
    def test_register_duplicate_username(self, auth_service):
        """测试用户注册 - 用户名重复"""
        auth_service.register(username="existuser", password="Pass123!", email="a@b.com")
        
        with pytest.raises(ValueError, match="已存在"):
            auth_service.register(username="existuser", password="Pass456!", email="c@d.com")
    
    def test_change_password_wrong_old_password(self, auth_service):
        """测试修改密码 - 旧密码错误"""
        user = auth_service.register(username="pwduser", password="OldPass1!", email="p@q.com")
        
        with pytest.raises(ValueError, match="密码"):
            auth_service.change_password(
                user_id=user.id,
                old_password="WrongOld!",
                new_password="NewPass1!"
            )
```

### 5.4 Domain 层测试（领域服务 - import 路径需替换为你的项目）

```python
"""角色领域服务测试

测试 RoleService 的业务规则
"""

import pytest
from unittest.mock import Mock
from sqlalchemy import Column, String, create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import StaticPool

from yweb.orm import CoreModel, BaseModel


class TestRoleService:
    """角色服务测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化测试数据库"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        session_scope = scoped_session(SessionLocal)
        CoreModel.query = session_scope.query_property()
        yield
        session_scope.remove()
    
    @pytest.fixture
    def role_service(self):
        """创建角色服务实例"""
        from app.domain.auth.role_service import RoleService  # ← 替换为你的领域服务模块
        # RoleService 通过构造函数注入模型类
        return RoleService(role_model=RoleModel, user_model=UserModel)
    
    def test_create_role(self, role_service):
        """测试创建角色"""
        role = role_service.create_role(name="编辑", code="editor")
        assert role.code == "editor"
    
    def test_create_role_duplicate_code_raises(self, role_service):
        """测试创建重复编码角色应抛出 ValueError"""
        role_service.create_role(name="管理员", code="admin")
        
        with pytest.raises(ValueError, match="已存在"):
            role_service.create_role(name="管理员2", code="admin")
    
    def test_delete_system_role_raises(self, role_service):
        """测试删除系统角色应被禁止"""
        role = role_service.create_role(name="超级管理员", code="super_admin", is_system=True)
        
        with pytest.raises(ValueError, match="系统角色"):
            role_service.delete_role(role.id)
```

---

## 6. 核心 Fixture 模式

### 6.1 数据库 Setup（最常用，必须掌握）

这是 yweb ORM 测试的**标准模式**，几乎每个测试文件都需要：

```python
@pytest.fixture(autouse=True)
def setup_db(self, memory_engine):
    """标准数据库 setup fixture
    
    步骤：
    1. 创建所有表
    2. 创建会话工厂
    3. 创建 scoped_session
    4. 设置 CoreModel.query（使 Active Record 方法工作）
    5. yield（测试执行）
    6. 清理会话
    """
    BaseModel.metadata.create_all(bind=memory_engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
    session_scope = scoped_session(SessionLocal)
    CoreModel.query = session_scope.query_property()
    yield
    session_scope.remove()
```

**关键点**：
- `memory_engine` 来自根 conftest.py（使用 `StaticPool`）
- `autouse=True` 使其对类内所有测试方法自动生效
- 必须设置 `CoreModel.query`，否则 `.add()` / `.get()` / `.query` 等 Active Record 方法无法工作
- `yield` 后调用 `session_scope.remove()` 清理

### 6.2 测试模型定义

```python
class UserModel(BaseModel):
    """测试用户模型"""
    __tablename__ = "test_users"
    __table_args__ = {'extend_existing': True}  # 防止跨文件重复定义
    
    email = Column(String(200), comment="邮箱")
```

**关键点**：
- `__tablename__` 使用 `test_` 前缀，避免与生产表名冲突
- **必须**设置 `__table_args__ = {'extend_existing': True}`，防止 pytest 多文件加载时重复定义错误
- 类名**不能**以 `Test` 开头

### 6.3 MockUser / 工厂 Fixture

```python
@pytest.fixture
def mock_user():
    """模拟用户对象工厂"""
    class MockUser:
        def __init__(self, id=1, username="testuser", email="test@example.com", is_active=True):
            self.id = id
            self.username = username
            self.email = email
            self.is_active = is_active
    return MockUser


@pytest.fixture
def sample_user(setup_db):
    """创建实际的测试用户（写入数据库）"""
    user = UserModel(name="测试用户", email="test@example.com")
    user.add(True)
    return user
```

---

## 7. Mock 策略

### 7.1 推荐方式优先级

1. **`unittest.mock`（Mock / MagicMock / AsyncMock / patch）** — 项目主要使用方式
2. **`pytest-mock`（mocker fixture）** — 简单场景可选用
3. **自定义 Mock 类（通过 fixture）** — 复杂对象推荐

### 7.2 使用 unittest.mock

```python
from unittest.mock import Mock, patch, MagicMock, AsyncMock


class TestSyncService:
    """同步服务测试"""
    
    def test_sync_calls_api(self):
        """测试同步操作调用外部 API"""
        with patch("app.domain.xxx.client.XxxClient.get_departments") as mock_api:  # ← 替换为实际路径
            mock_api.return_value = [{"id": 1, "name": "技术部"}]
            
            service = SyncService()
            result = service.sync_departments()
            
            mock_api.assert_called_once()
            assert len(result) == 1
    
    def test_service_with_mock_dependency(self):
        """使用 Mock 替代依赖"""
        mock_repo = Mock()
        mock_repo.find_by_id.return_value = SampleRole(id=1, name="admin")
        
        service = RoleService(role_model=mock_repo)
        role = service.get_role(1)
        
        assert role.name == "admin"
        mock_repo.find_by_id.assert_called_once_with(1)
```

### 7.3 使用 mocker fixture（pytest-mock）

```python
def test_cache_hit(self, mocker):
    """测试缓存命中"""
    mock_get = mocker.patch("yweb.cache.backend.get")
    mock_get.return_value = '{"id": 1, "name": "cached"}'
    
    result = get_user_cached(1)
    assert result["name"] == "cached"
    mock_get.assert_called_once()
```

### 7.4 异步 Mock

```python
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_async_job_execution(self):
    """测试异步任务执行"""
    mock_handler = AsyncMock(return_value="done")
    
    result = await execute_job(mock_handler)
    
    assert result == "done"
    mock_handler.assert_awaited_once()
```

---

## 8. 异步测试

### 8.1 基本异步测试

```python
import pytest

@pytest.mark.asyncio
async def test_async_operation():
    """测试异步操作"""
    result = await some_async_function()
    assert result is not None
```

### 8.2 异步测试类

```python
class TestAsyncService:
    """异步服务测试"""
    
    @pytest.mark.asyncio
    async def test_fetch_data(self):
        """测试异步数据获取"""
        service = AsyncDataService()
        data = await service.fetch()
        assert len(data) > 0
```

### 8.3 pytest-asyncio 配置

如果整个文件都是异步测试，可在文件头部声明：

```python
import pytest

pytestmark = pytest.mark.asyncio  # 整个文件的测试方法都标记为 asyncio
```

---

## 9. 断言规范

### 9.1 基本断言

```python
# 值断言
assert user.id is not None
assert user.name == "Alice"
assert isinstance(user.id, int)

# 集合断言
assert len(users) == 3
assert "admin" in role_codes

# 带描述的断言（调试友好）
assert user.ver == 1, f"初始版本号应为 1，实际为 {user.ver}"
assert user.updated_at is None, "首次添加时 updated_at 应为空"
```

### 9.2 异常断言

```python
# 断言抛出异常
with pytest.raises(ValueError):
    service.create_role(name="", code="")

# 断言异常消息
with pytest.raises(ValueError, match="已存在"):
    service.create_role(name="dup", code="admin")

# 获取异常信息
with pytest.raises(ValueError) as exc_info:
    service.delete_system_role(role_id)
assert "系统角色" in str(exc_info.value)
```

### 9.3 响应断言（API 测试）

```python
# HTTP 状态码
assert response.status_code == 200

# 响应体结构（yweb 统一响应格式）
data = response.json()
assert data["status"] == "success"
assert data["message"] == "操作成功"
assert data["data"]["id"] is not None

# 错误响应
assert data["status"] == "error"
assert "不存在" in data["message"]
```

---

## 10. 参数化测试

### 10.1 @pytest.mark.parametrize

```python
@pytest.mark.parametrize("email,is_valid", [
    ("user@example.com", True),
    ("user@test.org", True),
    ("invalid-email", False),
    ("", False),
    (None, False),
])
def test_email_validation(self, email, is_valid):
    """测试邮箱校验"""
    if is_valid:
        user = UserModel(name="Test", email=email)
        user.add(True)
        assert user.email == email
    else:
        with pytest.raises((ValueError, TypeError)):
            validate_email(email)


@pytest.mark.parametrize("role_code,should_protect", [
    ("super_admin", True),
    ("admin", True),
    ("custom_role", False),
])
def test_system_role_protection(self, role_code, should_protect):
    """测试系统角色保护机制"""
    role = create_role(code=role_code, is_system=should_protect)
    if should_protect:
        with pytest.raises(ValueError, match="系统角色"):
            role_service.delete_role(role.id)
    else:
        role_service.delete_role(role.id)  # 应成功
```

---

## 11. 测试标记

### 11.1 常用标记

```python
@pytest.mark.unit           # 单元测试
@pytest.mark.integration    # 集成测试
@pytest.mark.slow           # 慢速测试
@pytest.mark.asyncio        # 异步测试
```

### 11.2 按标记运行

```bash
pytest -m unit                    # 只跑单元测试
pytest -m "not slow"              # 跳过慢速测试
pytest -m "integration"           # 只跑集成测试
```

---

## 12. 测试辅助工具（helpers/）

### 12.1 设计原则

- helpers 目录放**非测试文件**，提供辅助函数和工具
- 避免在核心代码中添加测试专用方法
- 通过 `__init__.py` 导出公共接口

### 12.2 示例结构

```python
# tests/helpers/factory.py
"""测试数据工厂"""

def create_test_user(name="测试用户", email="test@example.com", **kwargs):
    """创建测试用户"""
    from app.domain.auth.model.user import User  # ← 替换为你的用户模型路径
    user = User(name=name, email=email, **kwargs)
    user.set_password("DefaultPass123!")
    user.add(True)
    return user


def create_test_role(name="测试角色", code="test_role", **kwargs):
    """创建测试角色"""
    from app.domain.permission.entities import Role  # ← 替换为你的角色模型路径
    role = Role(name=name, code=code, **kwargs)
    role.add(True)
    return role
```

```python
# tests/helpers/auth_utils.py
"""认证测试辅助"""

def create_test_token(user_id: int, username: str = "testuser") -> str:
    """生成测试用 JWT Token"""
    from yweb.auth import JWTManager
    manager = JWTManager(secret_key="test-secret", algorithm="HS256")
    payload = {"sub": username, "user_id": user_id}
    return manager.create_access_token(payload)


def get_auth_headers(user_id: int = 1) -> dict:
    """获取带认证的请求头"""
    token = create_test_token(user_id)
    return {"Authorization": f"Bearer {token}"}
```

---

## 13. 覆盖率

### 13.1 运行覆盖率

```bash
# 基础覆盖率
pytest --cov=yweb --cov-report=term-missing

# HTML 报告
pytest --cov=yweb --cov-report=html

# 指定最低覆盖率
pytest --cov=yweb --cov-fail-under=80
```

### 13.2 覆盖率关注重点

| 优先级 | 模块 | 目标 |
|--------|------|------|
| 高 | Domain 层（领域模型 + 领域服务） | ≥ 90% |
| 高 | Service 层（业务编排） | ≥ 85% |
| 中 | API 层（端点） | ≥ 80% |
| 中 | ORM 模型（自定义方法） | ≥ 80% |
| 低 | 配置/启动代码 | ≥ 60% |

---

## 14. 常见反模式（避免）

### 14.1 禁止的做法

```python
# ❌ 使用 unittest.TestCase（应使用纯 pytest 风格）
class TestUser(unittest.TestCase):  # 不要这样做
    def setUp(self):
        ...

# ❌ 测试方法测试多个不相关的行为
def test_user_crud_and_role_assignment():  # 职责不单一
    user = create_user(...)
    assert user.id
    assign_role(user, "admin")
    assert user.has_role("admin")

# ❌ 辅助类以 Test 开头
class TestUserFactory:  # pytest 会误识别
    ...

# ❌ 测试依赖执行顺序
def test_a_create():  # 不要依赖 test_a 在 test_b 之前执行
    global user_id
    user_id = create_user().id

def test_b_get():
    get_user(user_id)  # 依赖全局变量

# ❌ 硬编码数据库连接（应使用 fixture）
engine = create_engine("sqlite:///test.db")  # 不要在模块顶层这样做

# ❌ 在测试中直接导入并调用 init_database
from yweb.orm import init_database
init_database(...)  # 使用 fixture 管理，不要直接调用
```

### 14.2 推荐的做法

```python
# ✅ 纯 pytest 风格
class TestUser:
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        ...

# ✅ 单一职责
def test_create_user(self):
    ...

def test_assign_role_to_user(self):
    ...

# ✅ 辅助类不以 Test 开头
class UserFactory:
    ...

# ✅ 测试之间无依赖，每个测试自给自足
def test_get_user(self):
    user = UserModel(name="Test").add(True)  # 自己创建数据
    found = UserModel.get(user.id)
    assert found is not None

# ✅ 使用 fixture 管理数据库
@pytest.fixture(scope="function")
def memory_engine():
    ...
```

---

## 15. DDD 分层测试策略总览

```
┌──────────────────────────────────────────────────┐
│  API 层测试 (test_api/)                          │
│  - 使用 TestClient 发 HTTP 请求                  │
│  - 验证状态码、响应格式、DTO 转换                │
│  - Mock Service 层（或用真实 Service + 测试 DB）  │
├──────────────────────────────────────────────────┤
│  Service 层测试 (test_services/)                 │
│  - 测试业务编排逻辑                              │
│  - 可 Mock Domain 层依赖，也可用真实 DB          │
│  - 验证事务行为、跨聚合协调                      │
├──────────────────────────────────────────────────┤
│  Domain 层测试 (test_domain/)                    │
│  - 测试领域服务的业务规则                        │
│  - 测试领域模型的行为方法                        │
│  - 使用内存 DB + Active Record                   │
│  - 验证校验逻辑、状态变更、异常抛出              │
├──────────────────────────────────────────────────┤
│  ORM 层测试 (test_orm/)                          │
│  - 测试自定义 ORM 功能                           │
│  - CRUD、软删除、分页、关系等                    │
│  - 使用内存 SQLite + setup_db fixture            │
└──────────────────────────────────────────────────┘
```

---

## 16. 快速检查清单

编写测试文件前，对照此清单：

- [ ] 测试文件名以 `test_` 开头
- [ ] 测试类以 `Test` 开头，辅助类**不以** `Test` 开头
- [ ] 测试方法以 `test_` 开头，名称描述测试场景
- [ ] 每个测试方法有中文文档字符串
- [ ] 使用 `memory_engine` fixture（来自 conftest.py）
- [ ] ORM 测试包含 `setup_db` autouse fixture
- [ ] 测试模型设置了 `extend_existing=True`
- [ ] 测试模型表名使用 `test_` 前缀
- [ ] 每个测试方法独立，不依赖其他测试的执行顺序
- [ ] 异步测试方法标记了 `@pytest.mark.asyncio`
- [ ] 异常测试使用 `pytest.raises`
- [ ] 有适当的断言消息便于调试
