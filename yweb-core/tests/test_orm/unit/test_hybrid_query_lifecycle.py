"""HybridQuery 生命周期与并发行为测试（Phase 5.2）

覆盖 docs/orm_docs/22_hybrid_query_sync_async_refactor.md §7.2.3 的"强制清单"：

  L1. 串行多终端 → 中间件 finally 清理 session，registry 归空
  L2. 路由异常路径 → 中间件 finally 仍清理 session（不泄漏）
  L4. 无中间件反例 → session 泄漏可观测（反面用例，提醒必须挂中间件）
  L5. asyncio.gather 并发多终端 → 同一 Session 并发行为有限，必须串行或独立 scope
  L6. 脚本入口 with db_session_scope(): await q.all() → 正常清理

设计约束:
- 用 init_database(sqlite:///:memory:) + StaticPool 确保与生产路径（HybridQueryProperty）一致
- 断言标准：
    a) db_manager._session_scope.registry.has() == False  （会话已清理）
    b) TestClient 不抛 500 / 按预期抛 500
- StaticPool 只有 1 个连接，不用来测真正的 pool_size/max_overflow 压测
  （L7 压测需要文件 sqlite + QueuePool，规模更大，defer 到 Phase 5b 或 Phase 7）

注意：
- HybridQueryProperty 会在 init_database() 内部生效（Phase 4 已接入）
- 所有测试里的 async def 路由必须 await 终端方法，否则立刻 TypeError（Phase 3.3 A2 策略）
"""

import asyncio

import pytest
from sqlalchemy import Column, String
from fastapi import FastAPI
from fastapi.testclient import TestClient

from yweb.orm import (
    CoreModel,
    BaseModel,
    db_manager,
    init_database,
    on_request_end,
    async_db_call,
    db_session_scope,
)


# ==================== 测试模型 ====================

class LifecycleUser(BaseModel):
    __tablename__ = "lifecycle_users"
    __table_args__ = {'extend_existing': True}

    email = Column(String(200))


# ==================== 公共 fixture ====================

@pytest.fixture
def db_setup():
    """初始化 yweb ORM 并 seed 数据；每个测试独立 engine"""
    init_database(database_url="sqlite:///:memory:")
    BaseModel.metadata.create_all(bind=db_manager.engine)

    u = LifecycleUser(name="Alice", email="alice@test.com")
    u.save(commit=True)
    # seed 完强清 registry（避免 setup 在 worker 线程的残留 session 干扰后续断言）
    on_request_end()
    db_manager._session_scope.registry.registry.clear()

    yield
    on_request_end()
    db_manager._session_scope.registry.registry.clear()


def _registry_has() -> bool:
    """session_scope.registry 当前 scope 是否还挂着 session（未清理则 True）"""
    scope = db_manager._session_scope
    return bool(scope and scope.registry.has())


def _leaked_session_count() -> int:
    """跨所有 scope 观察 ScopedRegistry 中挂载的 session 数量

    说明：`registry.has()` 只看 scopefunc() 当前返回值对应的 session；
    当泄漏发生在 threadpool worker 的 ContextVar copy 中（HybridQuery 的 await
    走 run_in_threadpool）时，主协程的 scopefunc 结果已不同，`has()` 查不到。
    此函数直接穿透到 ScopedRegistry 内部 dict 长度，能捕获所有残留 session。
    """
    scope = db_manager._session_scope
    if not scope:
        return 0
    inner = getattr(scope.registry, "registry", None)
    return len(inner) if isinstance(inner, dict) else 0


# ==================== L1 + L2 + L5: 挂 RequestIDMiddleware 的请求路径 ====================

class TestLifecycleWithMiddleware:
    """挂了 RequestIDMiddleware 的正常请求路径"""

    @pytest.fixture(autouse=True)
    def setup(self, db_setup):
        from yweb.middleware import RequestIDMiddleware

        app = FastAPI()
        app.add_middleware(RequestIDMiddleware)

        @app.get("/serial-multi-terminal")
        async def serial_multi():
            """L1：同一请求内串行执行 3 个终端方法"""
            count = await LifecycleUser.query.count()
            first = await LifecycleUser.query.first()
            all_users = await LifecycleUser.query.all()
            return {
                "count": count,
                "first_name": first.name if first else None,
                "total": len(all_users),
            }

        @app.get("/boom-after-terminal")
        async def boom():
            """L2：先跑一个终端方法，再抛异常"""
            await LifecycleUser.query.count()
            raise RuntimeError("boom")

        @app.get("/gather-terminals")
        async def gather_terminals():
            """L5：asyncio.gather 并发多个终端
            同一个 scoped_session 下，多个 _HybridTerminal 在 threadpool 并发执行
            → Session 非线程安全，SA 可能抛并发错误；即便碰巧通过，也应视作"禁止"用法
            本测试不强制 raise，但记录并断言一件事：要么全部成功、要么明确抛错，不能静默数据错乱
            """
            results = await asyncio.gather(
                LifecycleUser.query.count(),
                LifecycleUser.query.count(),
                LifecycleUser.query.count(),
                return_exceptions=True,
            )
            return {
                "results": [r if not isinstance(r, Exception) else f"err:{type(r).__name__}" for r in results]
            }

        self.client = TestClient(app, raise_server_exceptions=False)
        yield

    def test_l1_serial_multi_terminal_session_cleaned(self):
        """L1: 串行多终端请求完成后 registry 归空"""
        resp = self.client.get("/serial-multi-terminal")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["count"] >= 1
        assert data["first_name"] == "Alice"
        assert data["total"] >= 1
        assert _registry_has() is False, "中间件 finally 未清理 session"

    def test_l2_exception_path_session_cleaned(self):
        """L2: 路由先跑终端再抛异常，中间件 finally 仍清理 session"""
        resp = self.client.get("/boom-after-terminal")
        assert resp.status_code == 500
        assert _registry_has() is False, "异常路径下 session 未清理，存在连接泄漏风险"

    def test_l5_gather_concurrent_terminals_behavior(self):
        """L5: asyncio.gather 并发多终端
        断言：
          - 请求不崩溃（TestClient 不 500）
          - 清理仍归零
          - 允许出现并发错误（results 里可以有 err:<Type>），但至少不能全部静默返回错误数据
        """
        resp = self.client.get("/gather-terminals")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data["results"]) == 3
        assert _registry_has() is False

        ok_results = [r for r in data["results"] if isinstance(r, int)]
        if ok_results:
            assert all(r == ok_results[0] for r in ok_results), (
                "gather 并发终端里成功的结果不一致，说明 Session 层可能已发生 race："
                f"{data['results']}"
            )


# ==================== L4: 无中间件反例（session 泄漏） ====================

class TestLifecycleWithoutMiddleware:
    """反面用例：未挂 RequestIDMiddleware 的情况下，session 不会被自动清理"""

    @pytest.fixture(autouse=True)
    def setup(self, db_setup):
        app = FastAPI()

        @app.get("/no-middleware-terminal")
        async def route():
            await LifecycleUser.query.count()
            return {"ok": True}

        self.client = TestClient(app, raise_server_exceptions=False)
        yield
        on_request_end()

    def test_l4_no_middleware_leaks_session(self):
        """无中间件时，请求成功但 session 泄漏（ScopedRegistry 内部仍挂载）
        这是反例：文档 §7.2.3 强制要求挂载 RequestIDMiddleware（或等价），
        本测试以 CI 固化形式提醒该前置条件。

        注意：HybridQuery 的 await 走 run_in_threadpool，worker 线程里
        scopefunc 返回的 request_id 和主协程不同 → 泄漏发生在 worker 对应
        的 registry key 上，`registry.has()` 查不到，必须走 `_leaked_session_count`
        穿透到内部 dict 才观察得到。
        """
        assert _leaked_session_count() == 0, "setup 未清理干净，基线不成立"
        resp = self.client.get("/no-middleware-terminal")
        assert resp.status_code == 200
        assert _leaked_session_count() >= 1, (
            "无中间件时，期望 ScopedRegistry 内部残留 ≥1 个未清理的 session；"
            "若此处为 0，说明 HybridQuery 的 threadpool 路径没有触发 session 创建，"
            "或某处有隐式清理 —— 需重新核对中间件假设"
        )


# ==================== L6: 脚本入口 db_session_scope + await ====================

class TestLifecycleScriptEntry:
    """脚本/定时任务入口：db_session_scope() 的 session 生命周期

    L6 覆盖 doc 22 §7.2.3 的脚本入口场景：
    - L6a / L6b：同步脚本下 `with db_session_scope():` 自动清理（含异常路径）
    - L6c：async 脚本 **推荐路径** —— async_db_call + on_request_end
    - L6d：Phase 5B.2 方案 A 落地后，async 脚本下也可直接 `with db_session_scope():`
          （内部自动 allow_sync），验证：可进入 / 可 commit / 退出后 session 清理
    """

    @pytest.fixture(autouse=True)
    def setup(self, db_setup):
        yield

    def test_l6a_sync_script_entry_cleans_session(self):
        """L6a: 同步脚本 `with db_session_scope(): User.query.all()` → 退出后清理"""
        with db_session_scope():
            users = LifecycleUser.query.all()
            assert len(users) >= 1
            assert users[0].name == "Alice"
        assert _registry_has() is False, "db_session_scope 退出后仍未清理 session"

    def test_l6b_sync_script_exception_still_cleaned(self):
        """L6b: 同步脚本 scope 内抛异常：退出后仍清理（finally 保证）"""
        with pytest.raises(RuntimeError):
            with db_session_scope():
                LifecycleUser.query.count()
                raise RuntimeError("boom-in-script")
        assert _registry_has() is False

    @pytest.mark.asyncio
    async def test_l6c_async_script_with_async_db_call_cleans_session(self):
        """L6c: 在 async 脚本里正确的做法是 async_db_call（不用 db_session_scope）

        这一用例验证：async 入口 + async_db_call 后 session 能被清理。
        注意：async_db_call 本身不会自动清理（清理靠 on_request_end 或中间件），
        这里手动调 on_request_end 模拟任务结束。
        """
        count = await async_db_call(LifecycleUser.query.count)
        assert count >= 1
        on_request_end()
        assert _registry_has() is False

    @pytest.mark.asyncio
    async def test_l6d_db_session_scope_usable_in_async(self):
        """L6d (Phase 5B.2 方案 A)：async 上下文下 `with db_session_scope():` 可用

        Phase 5B.2 落地：db_session_scope 内部自动 allow_sync bypass，
        使用者在 async 脚本里可直接 `with db_session_scope():` 做同步 ORM 操作，
        退出后 session 正常清理。
        """
        with db_session_scope():
            users = LifecycleUser.query.all()
            assert len(users) >= 1
        assert _registry_has() is False, (
            "async 下 db_session_scope 退出后应清理 session"
        )

    @pytest.mark.asyncio
    async def test_l6e_db_session_scope_in_async_commits_on_exit(self):
        """L6e: async 下 db_session_scope 的 auto_commit 真的落库"""
        new_name = "l6e-async-written"
        with db_session_scope():
            LifecycleUser(name=new_name, email="l6e@example.com").save()

        with db_session_scope():
            got = LifecycleUser.query.filter(LifecycleUser.name == new_name).first()
            assert got is not None, "auto_commit 未落库"
            assert got.email == "l6e@example.com"

    @pytest.mark.asyncio
    async def test_l6f_db_session_scope_in_async_rolls_back_on_exception(self):
        """L6f: async 下 db_session_scope 异常路径 rollback + 清理"""
        marker = "l6f-should-not-persist"
        with pytest.raises(RuntimeError, match="boom-async"):
            with db_session_scope():
                LifecycleUser(name=marker, email="l6f@example.com").save()
                raise RuntimeError("boom-async")

        assert _registry_has() is False, "异常路径未清理 session"

        with db_session_scope():
            got = LifecycleUser.query.filter(LifecycleUser.name == marker).first()
            assert got is None, "rollback 未生效，脏数据已落库"
