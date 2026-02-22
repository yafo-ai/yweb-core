"""当前用户追踪集成测试

核心改进：
1. 不使用 subprocess 隔离
2. 不使用独立的 VersioningManager
3. 依赖 conftest.py 的全局初始化（带 CurrentUserPlugin）
4. 所有测试共享同一个 sqlalchemy-history 配置

优势：
- 性能优秀（无进程开销）
- 调试友好（完整 IDE 支持）
- 架构简单（无隔离逻辑）
- 不污染其他测试（共享全局配置）

前提条件：
- conftest.py 必须在导入时调用 init_versioning(plugins=[CurrentUserPlugin()])
- 所有测试文件都使用相同的全局配置

完整的端到端测试场景：
1. 创建 User 和 Article 模型（启用历史记录）
2. 通过 Web API 模拟登录获取 Token
3. 用户1创建文章、修改文章
4. 切换用户2修改文章
5. 验证历史记录中的 user_id 是否正确记录
"""

import pytest
from fastapi import FastAPI, Depends, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import Column, String, Text, Integer, create_engine
from sqlalchemy.orm import sessionmaker, Session, registry, configure_mappers
from sqlalchemy.pool import StaticPool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from yweb.orm import is_versioning_initialized, get_version_class, set_user
from yweb.middleware.current_user import (
    set_current_user_id, clear_current_user_id, get_current_user_id
)


# ==================== 测试模型定义 ====================

# 创建独立的 registry（避免与其他测试冲突）
_test_registry = registry()
_TestBase = _test_registry.generate_base()


class User(_TestBase):
    """测试用户模型"""
    __tablename__ = 'v3_test_users'
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password = Column(String(100), nullable=False)


class Article(_TestBase):
    """测试文章模型（启用历史记录）"""
    __tablename__ = 'v3_test_articles'
    __table_args__ = {'extend_existing': True}
    __versioned__ = {}  # 启用版本控制
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    content = Column(Text)
    status = Column(String(20), default='draft')


# 配置 mappers（必须在使用模型之前）
try:
    configure_mappers()
except Exception:
    pass


# ==================== Pytest Fixtures ====================

@pytest.fixture(scope="function")
def test_db():
    """创建测试数据库（内存数据库 + StaticPool）"""
    # 验证全局初始化
    assert is_versioning_initialized(), "conftest.py 必须先调用 init_versioning()"
    
    # 创建内存数据库
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False}
    )
    
    # 创建所有表
    _TestBase.metadata.create_all(engine)
    
    # 创建历史表（使用全局 versioning_manager）
    from sqlalchemy_history import versioning_manager
    
    if versioning_manager.transaction_cls and hasattr(versioning_manager.transaction_cls, '__table__'):
        versioning_manager.transaction_cls.__table__.create(bind=engine, checkfirst=True)
    
    for key, ver_cls in versioning_manager.version_class_map.items():
        if ver_cls and hasattr(ver_cls, '__table__'):
            ver_cls.__table__.create(bind=engine, checkfirst=True)
    
    # 创建 session
    SessionLocal = sessionmaker(bind=engine)
    
    yield SessionLocal
    
    # 清理
    engine.dispose()


@pytest.fixture
def test_app(test_db):
    """创建测试用 FastAPI 应用"""
    SessionLocal = test_db
    app = FastAPI()
    
    def get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()
    
    # 认证中间件（从 Authorization Header 提取 user_id）
    class TestAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next) -> Response:
            auth = request.headers.get("Authorization", "")
            user_id = None
            if auth.startswith("Bearer user_"):
                try:
                    user_id = int(auth.replace("Bearer user_", ""))
                except ValueError:
                    pass
            
            if user_id is not None:
                set_current_user_id(user_id)
            
            try:
                response = await call_next(request)
                return response
            finally:
                clear_current_user_id()
    
    app.add_middleware(TestAuthMiddleware)
    
    # ==================== API 路由 ====================
    
    @app.post("/register")
    def register(username: str, password: str, db: Session = Depends(get_db)):
        """注册用户"""
        user = User(username=username, password=password)
        db.add(user)
        db.commit()
        db.refresh(user)
        return {"id": user.id, "username": user.username}
    
    @app.post("/login")
    def login(username: str, password: str, db: Session = Depends(get_db)):
        """登录"""
        user = db.query(User).filter(User.username == username).first()
        if not user or user.password != password:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return {"access_token": f"user_{user.id}", "user_id": user.id}
    
    @app.post("/articles")
    def create_article(title: str, content: str = "", db: Session = Depends(get_db)):
        """创建文章"""
        user_id = get_current_user_id()
        if user_id is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        # 设置当前用户（用于历史记录）
        set_user(db, user_id)
        
        article = Article(title=title, content=content)
        db.add(article)
        db.commit()
        db.refresh(article)
        return {"id": article.id, "title": article.title}
    
    @app.put("/articles/{article_id}")
    def update_article(
        article_id: int,
        title: str = None,
        content: str = None,
        status: str = None,
        db: Session = Depends(get_db)
    ):
        """更新文章"""
        user_id = get_current_user_id()
        if user_id is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        article = db.query(Article).filter(Article.id == article_id).first()
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        
        # 设置当前用户
        set_user(db, user_id)
        
        if title is not None:
            article.title = title
        if content is not None:
            article.content = content
        if status is not None:
            article.status = status
        
        db.commit()
        db.refresh(article)
        return {"id": article.id, "title": article.title, "content": article.content}
    
    @app.get("/articles/{article_id}/history")
    def get_article_history(article_id: int, db: Session = Depends(get_db)):
        """获取文章历史记录"""
        from sqlalchemy_history import versioning_manager
        
        ArticleVersion = get_version_class(Article)
        Transaction = versioning_manager.transaction_cls
        
        versions = db.query(ArticleVersion).filter_by(id=article_id).order_by(
            ArticleVersion.transaction_id
        ).all()
        
        history = []
        for v in versions:
            tx_user_id = None
            if Transaction and hasattr(Transaction, '__table__'):
                tx = db.query(Transaction).filter_by(id=v.transaction_id).first()
                if tx and hasattr(tx, 'user_id'):
                    tx_user_id = tx.user_id
            
            history.append({
                "version": v.transaction_id,
                "title": v.title,
                "content": v.content,
                "status": v.status,
                "operation_type": v.operation_type,
                "user_id": tx_user_id,
            })
        
        return {"article_id": article_id, "history": history}
    
    return TestClient(app)


# ==================== 测试用例 ====================

class TestAuditIntegrationv3:
    """当前用户追踪集成测试 v3（不隔离，共享全局配置）"""
    
    def test_full_audit_trail_with_multiple_users(self, test_app):
        """完整的多用户审计追踪测试"""
        client = test_app
        
        # 1. 注册两个用户
        r1 = client.post("/register", params={"username": "张三", "password": "pass123"})
        assert r1.status_code == 200
        user1_id = r1.json()["id"]
        
        r2 = client.post("/register", params={"username": "李四", "password": "pass456"})
        assert r2.status_code == 200
        user2_id = r2.json()["id"]
        
        # 2. 用户1登录并创建文章
        login1 = client.post("/login", params={"username": "张三", "password": "pass123"})
        token1 = login1.json()["access_token"]
        headers1 = {"Authorization": f"Bearer {token1}"}
        
        create_resp = client.post(
            "/articles",
            params={"title": "测试文章", "content": "原始内容"},
            headers=headers1
        )
        assert create_resp.status_code == 200
        article_id = create_resp.json()["id"]
        
        # 3. 用户1修改文章
        client.put(
            f"/articles/{article_id}",
            params={"content": "用户1第一次修改"},
            headers=headers1
        )
        
        # 4. 用户2登录并修改文章
        login2 = client.post("/login", params={"username": "李四", "password": "pass456"})
        token2 = login2.json()["access_token"]
        headers2 = {"Authorization": f"Bearer {token2}"}
        
        client.put(
            f"/articles/{article_id}",
            params={"content": "用户2的修改", "status": "published"},
            headers=headers2
        )
        
        # 5. 验证历史记录
        history_resp = client.get(f"/articles/{article_id}/history")
        assert history_resp.status_code == 200
        history = history_resp.json()["history"]
        
        # 断言
        assert len(history) == 3, f"期望3条历史，实际{len(history)}条"
        assert history[0]["user_id"] == user1_id, f"创建者应是用户1({user1_id})，实际{history[0]['user_id']}"
        assert history[1]["user_id"] == user1_id, f"修改者应是用户1({user1_id})，实际{history[1]['user_id']}"
        assert history[2]["user_id"] == user2_id, f"修改者应是用户2({user2_id})，实际{history[2]['user_id']}"
        
        print("✓ 审计追踪测试通过")
    
    def test_unauthenticated_request_rejected(self, test_app):
        """测试未认证请求被拒绝"""
        client = test_app
        
        resp = client.post("/articles", params={"title": "测试", "content": "内容"})
        assert resp.status_code == 401
        
        print("✓ 未认证拒绝测试通过")
    
    def test_user_switching_between_requests(self, test_app):
        """测试请求之间的用户切换"""
        client = test_app
        
        # 注册用户
        client.post("/register", params={"username": "user_a", "password": "pass"})
        client.post("/register", params={"username": "user_b", "password": "pass"})
        
        # 登录
        resp_a = client.post("/login", params={"username": "user_a", "password": "pass"})
        token_a = resp_a.json()["access_token"]
        user_a_id = resp_a.json()["user_id"]
        
        resp_b = client.post("/login", params={"username": "user_b", "password": "pass"})
        token_b = resp_b.json()["access_token"]
        user_b_id = resp_b.json()["user_id"]
        
        # 用户A创建文章
        resp = client.post(
            "/articles",
            params={"title": "文章", "content": "内容"},
            headers={"Authorization": f"Bearer {token_a}"}
        )
        article_id = resp.json()["id"]
        
        # 交替修改
        client.put(
            f"/articles/{article_id}",
            params={"content": "B修改1"},
            headers={"Authorization": f"Bearer {token_b}"}
        )
        client.put(
            f"/articles/{article_id}",
            params={"content": "A修改1"},
            headers={"Authorization": f"Bearer {token_a}"}
        )
        client.put(
            f"/articles/{article_id}",
            params={"content": "B修改2"},
            headers={"Authorization": f"Bearer {token_b}"}
        )
        
        # 验证历史记录
        history = client.get(f"/articles/{article_id}/history").json()["history"]
        
        expected = [user_a_id, user_b_id, user_a_id, user_b_id]
        actual = [h["user_id"] for h in history]
        assert actual == expected, f"期望{expected}，实际{actual}"
        
        print("✓ 用户切换测试通过")


if __name__ == "__main__":
    # 直接运行测试
    pytest.main([__file__, "-v", "-s"])
