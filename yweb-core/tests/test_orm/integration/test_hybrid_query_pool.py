"""HybridQuery 连接池并发压测（Phase 7B.2）

覆盖 ``docs/orm_docs/22_hybrid_query_sync_async_refactor.md`` §7.2.3 强制清单 L7：
连接池在 HybridQuery ``await`` 终端并发路径下能正确归还连接。

为什么与 ``test_connection_pool.py`` 并存：
    - 后者把 ``CoreModel.query`` 设成原生 SA ``session_scope.query_property()``，
      不经过 HybridQuery，测的是同步路径的连接回收
    - 本文件走 ``init_database``（Phase 4 起内部自动装 ``HybridQueryProperty``），
      用真实 HTTP 并发（``httpx.AsyncClient`` + ASGITransport + RequestIDMiddleware）
      发出 N = pool_size + max_overflow + 余量 个请求，每个 async 路由里
      ``await Model.query.count()``，验证 gather 返回后 ``pool.checkedout()``
      回到 0

设计要点：
    - pool_size=3, max_overflow=2 → 最大 5 个并发连接
    - concurrency=10（= 5 上限 + 5 排队）→ 部分请求会在 pool queue 上等连接
    - 每个请求 → 独立 request_id（由 ``RequestIDMiddleware`` 分配）→ 独立 session
      → 独立 connection
    - 请求结束中间件 finally 调 ``on_request_end()`` → connection 回 pool
"""

import asyncio
import os
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import Column, String

from yweb.middleware import RequestIDMiddleware
from yweb.orm import BaseModel, init_database, on_request_end


class PoolHybridUser(BaseModel):
    """压测专用模型 —— 放本文件避免与其他 integration 测试共享表"""

    __tablename__ = "pool_hybrid_users"
    __table_args__ = {"extend_existing": True}

    email = Column(String(100))


class TestHybridQueryConcurrentPool:
    """Phase 7B.2：HybridQuery await 路径下连接池并发回收"""

    DB_FILE = Path(__file__).parent / "test_hybrid_query_pool.db"
    POOL_SIZE = 3
    MAX_OVERFLOW = 2
    POOL_TIMEOUT = 10  # 秒；sqlite count 很快，10s 足以让所有排队请求轮转完
    CONCURRENCY = 10   # = pool_size + max_overflow + 5 余量

    @pytest.fixture(autouse=True)
    def setup_db(self):
        """独立 file sqlite + QueuePool；seed 10 条用户数据"""
        if self.DB_FILE.exists():
            os.remove(self.DB_FILE)

        engine, session_scope = init_database(
            f"sqlite:///{self.DB_FILE}",
            echo=False,
            pool_size=self.POOL_SIZE,
            max_overflow=self.MAX_OVERFLOW,
            pool_timeout=self.POOL_TIMEOUT,
        )
        # 注：Phase 4 起 init_database 内部会把 CoreModel.query 装成
        # HybridQueryProperty（见 db_session.py 末段 _attach_query_property），
        # 所以不需要手动赋值

        BaseModel.metadata.create_all(engine)

        for i in range(10):
            PoolHybridUser(name=f"u{i}", email=f"u{i}@t.com").save(commit=True)
        on_request_end()  # 清掉 seed 阶段的主协程 session，让测试从干净 pool 开始

        self.engine = engine
        yield

        try:
            session_scope.remove()
        except Exception:  # pragma: no cover
            pass
        engine.dispose()
        if self.DB_FILE.exists():
            try:
                os.remove(self.DB_FILE)
            except PermissionError:  # pragma: no cover (Windows file lock)
                pass

    def _pool_status(self):
        p = self.engine.pool
        return {
            "checkedout": p.checkedout(),
            "checkedin": p.checkedin(),
            "overflow": p.overflow(),
        }

    @pytest.mark.asyncio
    async def test_concurrent_hybrid_await_releases_connections(self):
        """N 并发 HTTP 请求各自 await HybridQuery 终端后 pool 完全归还"""
        app = FastAPI()
        app.add_middleware(RequestIDMiddleware)

        @app.get("/count")
        async def get_count():
            total = await PoolHybridUser.query.count()
            return {"total": total}

        # 基线：压测前 pool 无签出
        assert self._pool_status()["checkedout"] == 0, (
            f"基线不成立：压测前仍有签出 {self._pool_status()}"
        )

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            responses = await asyncio.gather(
                *[client.get("/count") for _ in range(self.CONCURRENCY)]
            )

        status_codes = [r.status_code for r in responses]
        assert all(c == 200 for c in status_codes), (
            f"有请求失败：{status_codes}；pool 可能 timeout 或 HybridQuery 抛错"
        )

        bodies = [r.json() for r in responses]
        assert all(b["total"] == 10 for b in bodies), (
            f"并发查询结果不一致（session 并发安全异常？）：{bodies}"
        )

        # 所有请求结束 → 中间件 finally 清 session → connection 回 pool
        final = self._pool_status()
        assert final["checkedout"] == 0, (
            f"{self.CONCURRENCY} 并发 HybridQuery await 后 pool 未归还："
            f"checkedout={final['checkedout']}, overflow={final['overflow']}"
        )

    @pytest.mark.asyncio
    async def test_burst_exceeding_pool_capacity_still_drains(self):
        """压测边界：并发 > pool_size + max_overflow 时，全部处理完，pool 归零"""
        burst = (self.POOL_SIZE + self.MAX_OVERFLOW) * 3  # = 15
        app = FastAPI()
        app.add_middleware(RequestIDMiddleware)

        @app.get("/count")
        async def get_count():
            total = await PoolHybridUser.query.count()
            return {"total": total}

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            responses = await asyncio.gather(
                *[client.get("/count") for _ in range(burst)]
            )

        # burst 过载下不应 500（pool_timeout 足够大时排队等待即可完成）
        assert all(r.status_code == 200 for r in responses), (
            f"burst={burst} 并发下出现失败：{[r.status_code for r in responses]}"
        )

        final = self._pool_status()
        assert final["checkedout"] == 0, (
            f"burst={burst} 后 pool 未归还：{final}"
        )
