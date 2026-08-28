"""async 安全检测测试

验证 yweb ORM 层能正确检测并阻止在 async 上下文中直接调用同步数据库操作。

测试场景：

  单元测试（检测逻辑）:
    1. async 上下文检测 → 抛出 SynchronousOnlyOperation
    2. 错误信息包含修复指导（def 路由 + async_db_call 两种方式）
    3. 同步上下文 → 正常放行
    4. async_db_call() 包装 → 正常放行
    5. async_db_call() *args/**kwargs 透传 → 参数正确传递
    6. async_db_call() 内函数抛异常 → 异常正确传播到调用方
    7. async_db_call() 非 HTTP 请求上下文 → 输出警告日志
    8. @with_db_session() 装饰 async 函数 → 不被拦截，正常执行
    9. YWEB_ASYNC_SAFETY=off → 禁用检测
    9. YWEB_ASYNC_SAFETY=warn → 警告但不报错
    10. 异常类型继承关系

  FastAPI 集成测试:
    8.  async def 路由直接调 ORM → 500
    9.  def 路由调 ORM → 200
    10. async def + async_db_call() → 200
    11. async_db_call 内完整 CRUD（增删改查）→ 数据正确
    12. async_db_call 内嵌套 ORM 调用（model.save() 等）→ 不误报
    13. 同一请求内多次 async_db_call 共享 Session → 数据一致
"""

import asyncio
import unittest.mock

import pytest
from sqlalchemy import Column, String
from sqlalchemy.orm import sessionmaker, scoped_session

from fastapi import FastAPI
from fastapi.testclient import TestClient

from yweb.orm import (
    CoreModel,
    BaseModel,
    db_manager,
    init_database,
    on_request_end,
    async_db_call,
    SynchronousOnlyOperation,
    check_async_safety,
)
from yweb.orm import async_safety


# ==================== 测试模型 ====================

class AsyncTestUser(BaseModel):
    __tablename__ = "async_test_users"
    __table_args__ = {'extend_existing': True}

    email = Column(String(200))


# ==================== 单元测试 ====================

class TestAsyncSafetyDetection:
    """测试 async 安全检测的核心逻辑"""

    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库"""
        BaseModel.metadata.create_all(bind=memory_engine)
        session_maker = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        session_scope = scoped_session(session_maker)
        CoreModel.query = session_scope.query_property()
        self._session_scope = session_scope
        yield
        session_scope.remove()

    @pytest.fixture(autouse=True)
    def reset_mode(self):
        """每个测试结束后恢复默认模式"""
        original = async_safety._mode
        yield
        async_safety._mode = original

    def test_sync_context_check_passes(self):
        """同步上下文中调用检测函数应直接通过，不抛异常"""
        check_async_safety()

    def test_async_context_raises_error(self):
        """在 async 上下文中调用检测函数应抛出 SynchronousOnlyOperation"""
        async def _run():
            check_async_safety()

        with pytest.raises(SynchronousOnlyOperation):
            asyncio.run(_run())

    def test_error_message_suggests_def_route(self):
        """错误信息应包含"方式1：def 路由"的修复指导"""
        async def _run():
            check_async_safety()

        with pytest.raises(SynchronousOnlyOperation) as exc_info:
            asyncio.run(_run())

        msg = str(exc_info.value)
        assert "def" in msg

    def test_error_message_suggests_async_db_call(self):
        """错误信息应包含"方式2：async_db_call()"的修复指导"""
        async def _run():
            check_async_safety()

        with pytest.raises(SynchronousOnlyOperation) as exc_info:
            asyncio.run(_run())

        msg = str(exc_info.value)
        assert "async_db_call" in msg

    def test_async_db_call_bypasses_detection(self):
        """通过 async_db_call() 包装后的调用应安全通过检测（在线程池执行）"""
        async def _run():
            await async_db_call(check_async_safety)

        asyncio.run(_run())

    def test_async_db_call_passes_args_and_kwargs(self):
        """async_db_call 应正确透传位置参数和关键字参数给被调用函数"""
        def add(a, b, extra=0):
            return a + b + extra

        async def _run():
            return await async_db_call(add, 1, 2, extra=10)

        assert asyncio.run(_run()) == 13

    def test_async_db_call_propagates_exception(self):
        """async_db_call 内函数抛出的异常应正确传播到 async 调用方"""
        def failing():
            raise ValueError("数据库操作失败")

        async def _run():
            await async_db_call(failing)

        with pytest.raises(ValueError, match="数据库操作失败"):
            asyncio.run(_run())

    def test_async_db_call_warns_outside_http_context(self):
        """非 HTTP 请求上下文中调用 async_db_call 应输出警告日志"""
        from yweb.orm.db_session import db_manager

        assert not db_manager._request_id_explicit.get(), \
            "测试前提：不在 managed request context 中"

        async def _run():
            await async_db_call(lambda: "ok")

        with unittest.mock.patch("yweb.orm.db_session._logger") as mock_logger:
            asyncio.run(_run())
            mock_logger.warning.assert_called_once()
            msg = mock_logger.warning.call_args[0][0]
            assert "非 HTTP 请求上下文" in msg

    def test_with_db_session_async_does_not_raise(self):
        """@with_db_session() 装饰 async 函数应正常工作，不被 async 安全检测拦截"""
        from yweb.orm import with_db_session

        @with_db_session()
        async def async_task(session):
            return session is not None

        async def _run():
            return await async_task()

        init_database(database_url="sqlite:///:memory:")
        BaseModel.metadata.create_all(bind=db_manager.engine)
        assert asyncio.run(_run()) is True

    def test_mode_off_disables_detection(self):
        """YWEB_ASYNC_SAFETY=off 应完全禁用检测"""
        async_safety._mode = "off"

        async def _run():
            check_async_safety()

        asyncio.run(_run())

    def test_mode_warn_emits_warning_instead_of_error(self):
        """YWEB_ASYNC_SAFETY=warn 应发出 RuntimeWarning 而非抛异常"""
        async_safety._mode = "warn"

        async def _run():
            check_async_safety()

        with pytest.warns(RuntimeWarning, match="async"):
            asyncio.run(_run())

    def test_exception_is_runtime_error_subclass(self):
        """SynchronousOnlyOperation 应是 RuntimeError 的子类"""
        assert issubclass(SynchronousOnlyOperation, RuntimeError)


# ==================== FastAPI 集成测试 ====================

class TestAsyncSafetyFastAPIIntegration:
    """FastAPI 路由层的集成测试：验证 async 安全检测在真实请求中的表现"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """初始化数据库和 FastAPI 应用"""
        init_database(database_url="sqlite:///:memory:")
        BaseModel.metadata.create_all(bind=db_manager.engine)

        user = AsyncTestUser(name="Alice", email="alice@test.com")
        user.save(commit=True)

        from yweb.middleware import RequestIDMiddleware

        app = FastAPI()
        app.add_middleware(RequestIDMiddleware)

        @app.get("/async-users")
        async def get_users_async():
            """async def 路由直接调 ORM → 应被拦截"""
            users = AsyncTestUser.query.filter_by(name="Alice").all()
            return {"count": len(users)}

        @app.get("/sync-users")
        def get_users_sync():
            """def 路由调 ORM → 应正常工作"""
            users = AsyncTestUser.query.filter_by(name="Alice").all()
            return {"count": len(users)}

        @app.get("/async-users-safe")
        async def get_users_async_safe():
            """async def + async_db_call() → 应正常工作"""
            users = await async_db_call(
                lambda: AsyncTestUser.query.filter_by(name="Alice").all()
            )
            return {"count": len(users)}

        self.client = TestClient(app, raise_server_exceptions=False)
        yield
        on_request_end()

    @pytest.fixture(autouse=True)
    def ensure_error_mode(self):
        """确保集成测试在 error 模式下运行"""
        original = async_safety._mode
        async_safety._mode = "error"
        yield
        async_safety._mode = original

    def test_async_route_direct_orm_returns_500(self):
        """async def 路由直接调用 ORM 应返回 500（被 async 安全检测拦截）"""
        resp = self.client.get("/async-users")
        assert resp.status_code == 500

    def test_sync_route_orm_returns_200(self):
        """def 路由调用 ORM 应正常返回 200"""
        resp = self.client.get("/sync-users")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 0

    def test_async_route_with_async_db_call_returns_200(self):
        """async def + async_db_call() 调用 ORM 应正常返回 200"""
        resp = self.client.get("/async-users-safe")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 0


# ==================== async_db_call 完整功能测试 ====================

class TestRunDbCRUDAndSessionSharing:
    """验证 async_db_call 包装下的完整 CRUD 操作、嵌套调用、Session 共享"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """初始化数据库和 FastAPI 应用"""
        init_database(database_url="sqlite:///:memory:")
        BaseModel.metadata.create_all(bind=db_manager.engine)

        from yweb.middleware import RequestIDMiddleware

        app = FastAPI()
        app.add_middleware(RequestIDMiddleware)

        @app.post("/run-db-crud")
        async def async_db_call_crud():
            """async_db_call 内完整 CRUD 测试"""

            def do_crud():
                # Create
                user = AsyncTestUser(name="Bob", email="bob@test.com")
                user.save(commit=True)

                # Read
                found = AsyncTestUser.get(user.id)
                created_name = found.name

                # Update
                found.update(commit=True, email="bob_new@test.com")
                updated = AsyncTestUser.get(user.id)
                updated_email = updated.email

                # Delete
                user_id = updated.id
                updated.delete(commit=True)
                deleted = AsyncTestUser.get(user_id)

                return {
                    "created_name": created_name,
                    "updated_email": updated_email,
                    "deleted_is_none": deleted is None,
                }

            return await async_db_call(do_crud)

        @app.post("/run-db-nested")
        async def async_db_call_nested():
            """async_db_call 内嵌套多步 ORM 操作（模拟 Service 层）"""

            def service_create_user_with_update():
                user = AsyncTestUser(name="Nested", email="v1@test.com")
                user.save(commit=True)
                user.update(commit=True, email="v2@test.com")
                refreshed = AsyncTestUser.get(user.id)
                return {
                    "id": refreshed.id,
                    "name": refreshed.name,
                    "email": refreshed.email,
                }

            result = await async_db_call(service_create_user_with_update)
            return result

        @app.get("/run-db-session-sharing")
        async def async_db_call_session_sharing():
            """多次 async_db_call 调用共享同一 Session（同一 request_id）"""

            user = await async_db_call(lambda: AsyncTestUser(
                name="Shared", email="shared@test.com"
            ))
            await async_db_call(lambda: user.save(commit=True))

            found = await async_db_call(
                lambda: AsyncTestUser.query.filter_by(name="Shared").first()
            )

            return {
                "created_id": user.id,
                "found_id": found.id if found else None,
                "same_record": user.id == found.id if found else False,
            }

        self.client = TestClient(app, raise_server_exceptions=True)
        yield
        on_request_end()

    def test_async_db_call_crud_operations(self):
        """async_db_call 包装下的增删改查应全部正确执行"""
        resp = self.client.post("/run-db-crud")
        assert resp.status_code == 200
        data = resp.json()
        assert data["created_name"] == "Bob"
        assert data["updated_email"] == "bob_new@test.com"
        assert data["deleted_is_none"] is True

    def test_async_db_call_nested_orm_calls(self):
        """async_db_call 内嵌套的多步 ORM 操作（save + update + get）不应误报"""
        resp = self.client.post("/run-db-nested")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Nested"
        assert data["email"] == "v2@test.com"
        assert data["id"] is not None

    def test_multiple_async_db_call_calls_share_session(self):
        """同一请求内多次 async_db_call 调用应能看到彼此的数据变更"""
        resp = self.client.get("/run-db-session-sharing")
        assert resp.status_code == 200
        data = resp.json()
        assert data["same_record"] is True
        assert data["created_id"] is not None
        assert data["created_id"] == data["found_id"]

