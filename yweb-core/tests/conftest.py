"""
Pytest 公共配置和 Fixtures

提供测试所需的公共资源：
- 数据库连接
- 测试客户端
- 模拟对象
- 全局版本化初始化（带 CurrentUserPlugin）
"""

import pytest
import os
import tempfile
from typing import Generator

# FastAPI 测试客户端
from fastapi import FastAPI
from fastapi.testclient import TestClient

# SQLAlchemy
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool


# ==================== Pytest Hook：全局初始化 ====================

def pytest_configure(config):
    """Pytest 配置钩子 - 全局初始化 sqlalchemy-history
    
    重要说明：
    1. 此钩子会在所有测试运行前执行（最早执行）
    2. 会初始化 sqlalchemy-history + CurrentUserPlugin
    3. 所有测试共享同一个全局配置（避免重复初始化冲突）
    4. 不要在测试中重复调用 init_versioning()
    5. 不要修改全局 versioning_manager 的状态
    
    优势：
    - 比模块级导入更早执行
    - 只执行一次，避免冲突
    - 所有测试共享同一个配置
    - 性能优秀（无重复初始化开销）
    
    环境变量控制（可选）：
        YWEB_TEST_USER_TRACKING=false pytest tests/  # 禁用 CurrentUserPlugin
        YWEB_TEST_USER_TRACKING=true pytest tests/   # 启用 CurrentUserPlugin（默认）
    
    """
    import os
    from yweb.orm import init_versioning, CurrentUserPlugin, is_versioning_initialized
    
    if is_versioning_initialized():
        return
    
    # 通过环境变量控制是否启用 CurrentUserPlugin（默认启用）
    enable_user_tracking = os.getenv('YWEB_TEST_USER_TRACKING', 'true').lower() == 'true'
    
    if enable_user_tracking:
        init_versioning(plugins=[CurrentUserPlugin()])
    else:
        init_versioning()


# ==================== 基础 Fixtures ====================

@pytest.fixture(scope="session")
def temp_dir():
    """创建临时目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def temp_file(temp_dir):
    """创建临时文件的工厂函数"""
    created_files = []
    
    def _create_file(filename: str, content: str = "") -> str:
        filepath = os.path.join(temp_dir, filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True) if os.path.dirname(filepath) else None
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        created_files.append(filepath)
        return filepath
    
    yield _create_file
    
    # 清理
    for f in created_files:
        if os.path.exists(f):
            os.remove(f)


# ==================== FastAPI Fixtures ====================

@pytest.fixture
def app():
    """创建测试用 FastAPI 应用"""
    from yweb import OK, BadRequest, NotFound
    from yweb.middleware import RequestIDMiddleware
    
    test_app = FastAPI(title="Test App")
    
    # 添加中间件
    test_app.add_middleware(RequestIDMiddleware)
    
    # 添加测试路由
    @test_app.get("/health")
    def health():
        return OK({"status": "healthy"})
    
    @test_app.get("/users/{user_id}")
    def get_user(user_id: int):
        if user_id == 1:
            return OK({"id": 1, "name": "Test User"})
        return NotFound("用户不存在")
    
    @test_app.post("/users")
    def create_user(name: str = None):
        if not name:
            return BadRequest("用户名不能为空")
        return OK({"id": 2, "name": name}, "创建成功")
    
    return test_app


@pytest.fixture
def client(app):
    """创建测试客户端"""
    return TestClient(app)


# ==================== 数据库 Fixtures ====================

@pytest.fixture(scope="function")
def sqlite_engine(temp_dir):
    """创建 SQLite 内存数据库引擎"""
    db_path = os.path.join(temp_dir, "test.db")
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def memory_engine():
    """创建内存数据库引擎
    
    使用 StaticPool 和 check_same_thread=False 确保：
    1. 所有操作使用同一个连接（StaticPool）
    2. 允许跨线程访问（check_same_thread=False）
    这避免了 pytest 清理阶段可能出现的 SQLite 线程错误。
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


# ==================== JWT Fixtures ====================

@pytest.fixture
def jwt_secret_key():
    """JWT 测试密钥"""
    return "test-secret-key-for-testing-only"


@pytest.fixture
def jwt_manager(jwt_secret_key):
    """创建 JWT 管理器"""
    from yweb.auth import JWTManager
    return JWTManager(
        secret_key=jwt_secret_key,
        algorithm="HS256",
        access_token_expire_minutes=30,
        refresh_token_expire_days=7
    )


@pytest.fixture
def sample_token_payload():
    """示例 Token 载荷"""
    from yweb.auth import TokenPayload
    return TokenPayload(
        sub="testuser",
        user_id=1,
        username="testuser",
        email="test@example.com",
        roles=["user", "admin"]
    )


# ==================== 配置 Fixtures ====================

@pytest.fixture
def sample_yaml_config(temp_file):
    """创建示例 YAML 配置文件"""
    yaml_content = """
app_name: "Test Application"
debug: true

database:
  url: "sqlite:///test.db"
  pool_size: 5
  
jwt:
  secret_key: "test-secret"
  algorithm: "HS256"
  access_token_expire_minutes: 30

logging:
  level: "DEBUG"
  file_path: "logs/test.log"
"""
    return temp_file("config/settings.yaml", yaml_content)


@pytest.fixture
def sample_env_file(temp_file):
    """创建示例 .env 文件"""
    env_content = """
YWEB_APP_NAME=Test App
YWEB_DEBUG=true
YWEB_DATABASE_URL=sqlite:///test.db
YWEB_JWT_SECRET_KEY=env-secret-key
"""
    return temp_file(".env", env_content)


# ==================== 日志 Fixtures ====================

@pytest.fixture
def log_dir(temp_dir):
    """创建日志目录"""
    log_path = os.path.join(temp_dir, "logs")
    os.makedirs(log_path, exist_ok=True)
    return log_path


# ==================== Mock Fixtures ====================

@pytest.fixture
def mock_user():
    """模拟用户对象"""
    class MockUser:
        def __init__(self, id=1, username="testuser", email="test@example.com", is_active=True):
            self.id = id
            self.username = username
            self.email = email
            self.is_active = is_active
    
    return MockUser


@pytest.fixture
def user_getter(mock_user):
    """模拟用户获取函数"""
    users = {
        1: mock_user(id=1, username="user1"),
        2: mock_user(id=2, username="user2"),
    }
    
    def _get_user(user_id: int):
        return users.get(user_id)
    
    return _get_user
