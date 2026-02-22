"""Web API 连接池集成测试

测试通过 FastAPI Web API + 中间件的方式，验证连接池资源管理。

测试场景：
1. 同步路由函数 + 多次查询（模拟真实项目场景）
2. 验证 RequestIDMiddleware 正确清理 session，不会导致连接泄漏

关键点：
- 使用文件数据库（支持真实连接池行为）
- 同步路由函数在线程池中运行（模拟真实场景）
- 设置较小的连接池，便于检测泄漏
- 每个测试有超时限制，防止连接池耗尽时无限等待
"""

import pytest
from fastapi import FastAPI, Query
from fastapi.testclient import TestClient
from sqlalchemy import Column, String
from typing import Optional


from yweb.orm import (
    CoreModel,
    BaseModel,
    init_database,
    on_request_end,
)
from yweb.middleware import RequestIDMiddleware
from yweb.response import OK


# ==================== 测试模型定义 ====================

class PoolTestUserModel(BaseModel):
    """连接池测试用户模型"""
    __tablename__ = "pool_test_users"
    __table_args__ = {'extend_existing': True}
    
    username = Column(String(50))
    email = Column(String(100))
    status = Column(String(20), default="active")


# ==================== 测试类 ====================

class TestConnectionPoolWebApi:
    """Web API 连接池测试
    
    使用真实连接池 + 同步路由函数，验证：
    1. 多次查询不会耗尽连接池
    2. RequestIDMiddleware 正确清理 session
    """
    
    @pytest.fixture(autouse=True)
    def setup_app(self, tmp_path):
        """初始化 FastAPI 应用和数据库"""
        # 使用临时文件数据库
        db_path = tmp_path / "test_pool.db"
        db_url = f"sqlite:///{db_path}"
        
        # 使用 init_database 初始化，设置较小的连接池
        # pool_size=3, max_overflow=2 → 最大 5 个连接
        engine, session_scope = init_database(
            database_url=db_url,
            echo=False,
            pool_size=3,
            max_overflow=2,
            pool_timeout=3,  # 3秒超时，便于快速检测泄漏
        )
        
        # 设置 ORM query 属性
        CoreModel.query = session_scope.query_property()
        BaseModel.metadata.create_all(engine)
        
        self.engine = engine
        self.session_scope = session_scope
        self.db_path = db_path
        
        # 准备测试数据
        self._prepare_test_data()
        
        # 创建 FastAPI 应用
        app = FastAPI(title="Connection Pool Test API")
        
        # 添加 RequestIDMiddleware（纯 ASGI 实现）
        app.add_middleware(RequestIDMiddleware)
        
        # ==================== 同步路由（在线程池中运行）====================
        
        @app.get("/users/by-name/{name}")
        def get_user_by_name(name: str):
            """同步路由：根据名称获取用户"""
            user = PoolTestUserModel.get_by_name(name)
            if user:
                return OK({
                    "id": user.id,
                    "name": user.name,
                    "username": user.username,
                    "email": user.email
                })
            return OK(None, "用户不存在")
        
        @app.get("/users")
        def get_users_paginated(
            page: int = Query(default=1, ge=1),
            page_size: int = Query(default=10, ge=1, le=100),
            status: Optional[str] = None
        ):
            """同步路由：分页查询用户列表"""
            query = PoolTestUserModel.query
            
            if status:
                query = query.filter(PoolTestUserModel.status == status)
            
            page_result = query.paginate(page=page, page_size=page_size)
            
            return OK({
                "rows": [
                    {
                        "id": u.id,
                        "name": u.name,
                        "username": u.username,
                        "email": u.email,
                        "status": u.status
                    }
                    for u in page_result.rows
                ],
                "total_records": page_result.total_records,
                "page": page_result.page,
                "page_size": page_result.page_size,
                "total_pages": page_result.total_pages
            })
        
        @app.get("/users/{user_id}")
        def get_user_by_id(user_id: int):
            """同步路由：根据ID获取用户"""
            user = PoolTestUserModel.get(user_id)
            if user:
                return OK({
                    "id": user.id,
                    "name": user.name,
                    "username": user.username,
                    "email": user.email
                })
            return OK(None, "用户不存在")
        
        # 创建测试客户端
        self.client = TestClient(app)
        self.app = app
        
        yield
        
        # 清理
        on_request_end()
    
    def _prepare_test_data(self):
        """准备测试数据"""
        users = []
        for i in range(30):
            user = PoolTestUserModel(
                name=f"pool_user_{i:03d}",
                username=f"pool_username_{i:03d}",
                email=f"pool_user{i}@example.com",
                status="active" if i % 3 != 0 else "inactive"
            )
            users.append(user)
        PoolTestUserModel.add_all(users, commit=True)
        # 清理准备数据时的 session
        on_request_end()
    
    # ==================== 连接池泄漏测试 ====================
    # 注意：连接池配置 pool_timeout=5 秒，如果有泄漏会抛出 TimeoutError
    
    def test_no_connection_leak_after_20_requests(self):
        """测试：20 次请求后不会耗尽连接池
        
        连接池配置：pool_size=3, max_overflow=2, 最大 5 个连接
        如果有泄漏，第 6 次请求就会超时
        """
        for i in range(20):
            response = self.client.get(f"/users?page=1&page_size=10")
            assert response.status_code == 200, f"第 {i+1} 次请求失败: {response.text}"
            
            data = response.json()
            assert data["data"]["total_records"] == 30
    
    def test_no_connection_leak_get_by_name_30_times(self):
        """测试：get_by_name 30 次不会耗尽连接池"""
        for i in range(30):
            name = f"pool_user_{i % 30:03d}"
            response = self.client.get(f"/users/by-name/{name}")
            assert response.status_code == 200, f"第 {i+1} 次请求失败"
    

    def test_no_connection_leak_paginate_50_times(self):
        """测试：分页查询 50 次不会耗尽连接池"""
        for i in range(50):
            page = (i % 3) + 1
            page_size = [5, 10, 15][i % 3]
            response = self.client.get(f"/users?page={page}&page_size={page_size}")
            assert response.status_code == 200, f"第 {i+1} 次请求失败"
    

    def test_request_id_in_response_header(self):
        """测试：验证 RequestIDMiddleware 正常工作"""
        for i in range(10):
            response = self.client.get("/users?page=1&page_size=10")
            
            assert response.status_code == 200
            # 验证响应头中有 X-Request-ID
            assert "x-request-id" in response.headers
            request_id = response.headers["x-request-id"]
            assert len(request_id) > 0
