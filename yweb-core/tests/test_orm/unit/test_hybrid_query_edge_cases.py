"""HybridQuery 边缘场景 / trap 测试（Phase 7B.3 / 7B.4 / 7B.5）

覆盖：
  - 7B.3 Lazy 加载 trap
      · 反例：async 路径取完对象后 middleware 关闭 session → 访问关系属性
              抛 DetachedInstanceError
      · 正例：`options(joinedload(...))` 一次性取齐，关闭 session 后仍可访问关系
  - 7B.4 `lazy='dynamic'` 固化行为
      · `rel` 返回 SA 原生 AppenderQuery，不经过 HybridQueryProperty 包装
      · 终端（`.all()` / `.count()`）直接返回 Python 原生类型，不是 _HybridTerminal
      · 在 async 下对终端结果 `await` → TypeError（用户自担：改 joinedload 或 async_db_call）
  - 7B.5 DetachedInstanceError 处理策略
      · 反例：默认 lazy='select'，session 关闭后访问关系 → DetachedInstanceError
      · 正例：joinedload 预载，session 关闭后访问仍 OK

为什么合并这 3 项：三者都围绕「关系加载 × session 生命周期」，共享一套关系模型
（Author/Post 演示 lazy='select'；Team/Member 演示 lazy='dynamic'），避免重复 fixture。

注意：
- 本文件 0 处 `lazy='dynamic'` 在生产代码中（Phase 0 扫描确认），测试是**预防性固化**，
  防止未来有人加 `lazy='dynamic'` 时静默踩坑（进程阻塞 / await 失败）。
- `EdgeAuthor / EdgePost / EdgeTeam / EdgeMember` 表名全部走 `extend_existing=True`，
  与 Phase 5B.3 的 scheduler metadata 隔离策略一致（BaseModel.metadata 累积可接受，
  因为表名不与其他测试冲突）。
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import Query as SAQuery
from sqlalchemy.orm import joinedload, relationship
from sqlalchemy.orm.exc import DetachedInstanceError

from yweb.orm import (
    BaseModel,
    db_manager,
    init_database,
    on_request_end,
)
from yweb.orm.hybrid_query import HybridQuery


# ==================== 测试模型 ====================


class EdgeAuthor(BaseModel):
    __tablename__ = "edge_author"
    __table_args__ = {"extend_existing": True}

    email = Column(String(200))
    # 默认 lazy='select'：访问时懒加载，session 关闭后 → DetachedInstanceError
    posts = relationship(
        "EdgePost",
        back_populates="author",
        cascade="all, delete-orphan",
    )


class EdgePost(BaseModel):
    __tablename__ = "edge_post"
    __table_args__ = {"extend_existing": True}

    author_id = Column(Integer, ForeignKey("edge_author.id"))
    title = Column(String(200))
    author = relationship("EdgeAuthor", back_populates="posts")


class EdgeTeam(BaseModel):
    __tablename__ = "edge_team"
    __table_args__ = {"extend_existing": True}

    # lazy='dynamic'：team.members 返回 AppenderQuery（SA 原生 Query 子类），不是 HybridQuery
    members = relationship(
        "EdgeMember",
        back_populates="team",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )


class EdgeMember(BaseModel):
    __tablename__ = "edge_member"
    __table_args__ = {"extend_existing": True}

    team_id = Column(Integer, ForeignKey("edge_team.id"))
    team = relationship("EdgeTeam", back_populates="members")


# ==================== 公共 fixture ====================


@pytest.fixture
def db_setup():
    """每个测试独立 engine + metadata.create_all；不 seed，每个测试自己准备数据"""
    init_database(database_url="sqlite:///:memory:")
    BaseModel.metadata.create_all(bind=db_manager.engine)

    yield

    on_request_end()
    db_manager._session_scope.registry.registry.clear()


# ==================== 7B.3 + 7B.5 — lazy='select' × session 生命周期 ====================


class TestLazyLoadSessionLifecycle:
    """默认 lazy='select' 的加载行为 × session 关闭前后 × 是否 joinedload。

    这类 trap 的根因：ORM 对象在 session 关闭后变成 detached，再访问未加载的关系属性
    没有 session 可以发 SELECT，SA 抛 DetachedInstanceError。
    """

    def test_lazy_load_within_live_session_works(self, db_setup):
        """基线：session 还活着时，懒加载正常工作（7B.3 基线）"""
        author = EdgeAuthor(name="A", email="a@test.com")
        author.save(commit=True)
        EdgePost(name="P", title="T", author_id=author.id).save(commit=True)

        got = EdgeAuthor.query.filter(EdgeAuthor.id == author.id).first()
        # 未 on_request_end，session 活着 → 触发 lazy load → 拿到 posts
        assert len(got.posts) == 1
        assert got.posts[0].title == "T"

    def test_access_relationship_after_session_closed_raises_detached(self, db_setup):
        """7B.5 反例：session 关闭后访问未预载关系 → DetachedInstanceError"""
        author = EdgeAuthor(name="A", email="a@test.com")
        author.save(commit=True)
        EdgePost(name="P", title="T", author_id=author.id).save(commit=True)

        got = EdgeAuthor.query.filter(EdgeAuthor.id == author.id).first()

        # 模拟请求结束 —— middleware 的 finally 路径
        on_request_end()

        # 再访问未加载的关系 → detached
        with pytest.raises(DetachedInstanceError):
            _ = got.posts

    def test_joinedload_keeps_relationship_accessible_after_session_closed(
        self, db_setup
    ):
        """7B.5 正例：options(joinedload(...)) 预载，session 关闭后仍可访问"""
        author = EdgeAuthor(name="A", email="a@test.com")
        author.save(commit=True)
        EdgePost(name="P", title="T", author_id=author.id).save(commit=True)

        got = (
            EdgeAuthor.query.options(joinedload(EdgeAuthor.posts))
            .filter(EdgeAuthor.id == author.id)
            .first()
        )

        on_request_end()

        # joinedload 已经把 posts 预载到对象里 → 无需 session 也能访问
        posts = got.posts
        assert len(posts) == 1
        assert posts[0].title == "T"


class TestLazyLoadInAsyncRoute:
    """HybridQuery + async def 路由下的关系加载行为。

    关键点：
      - `await EdgeAuthor.query.options(joinedload(...)).first()` 在线程池里跑，返回前 joinedload 已生效
      - middleware 结束时 session 关闭，但对象已带 posts，route 序列化不会踩 DetachedInstance
    """

    def test_async_route_with_joinedload_returns_relations(self, db_setup):
        """7B.3 正例：async def + joinedload，TestClient 成功返回 JSON，posts 字段齐全"""
        author = EdgeAuthor(name="A", email="a@test.com")
        author.save(commit=True)
        EdgePost(name="P1", title="T1", author_id=author.id).save(commit=True)
        EdgePost(name="P2", title="T2", author_id=author.id).save(commit=True)
        # 缓存为 python int —— 避免 on_request_end 后 author.id 触发 expire 重载（DetachedInstance）
        author_id = author.id
        on_request_end()

        from yweb.middleware import RequestIDMiddleware

        app = FastAPI()
        app.add_middleware(RequestIDMiddleware)

        @app.get("/author-with-posts/{aid}")
        async def get_author(aid: int):
            got = (
                await EdgeAuthor.query.options(joinedload(EdgeAuthor.posts))
                .filter(EdgeAuthor.id == aid)
                .first()
            )
            if got is None:
                return {"author": None}
            # 在 route 里直接用 posts —— joinedload 已经预载，不触发额外 SQL
            return {
                "id": got.id,
                "name": got.name,
                "posts": [{"title": p.title} for p in got.posts],
            }

        with TestClient(app) as client:
            resp = client.get(f"/author-with-posts/{author_id}")
            assert resp.status_code == 200
            data = resp.json()
            assert data["name"] == "A"
            assert {p["title"] for p in data["posts"]} == {"T1", "T2"}


# ==================== 7B.4 — lazy='dynamic' 固化 ====================


class TestLazyDynamicIsAppenderNotHybrid:
    """`lazy='dynamic'` 返回 SA 原生 AppenderQuery，不经过 HybridQueryProperty 包装。

    固化理由：生产代码目前 0 处使用 `lazy='dynamic'`（Phase 0 扫描确认）。但若未来有人
    引入，他需要**立刻知道**：
      1. `team.members` 不是 HybridQuery，终端方法**不是**双态（返回 list 而不是 _HybridTerminal）
      2. 所以 `await team.members.all()` 会抛 TypeError（对 list 做 await）
      3. 想在 async 下用，必须走 `async_db_call(lambda: team.members.filter(...).all())`
         或者改 relationship 为默认 lazy='select' + joinedload
    """

    def test_dynamic_relation_returns_sa_appender_query(self, db_setup):
        """team.members 是 SA 原生 Query 子类，不是 HybridQuery"""
        team = EdgeTeam(name="T1")
        team.save(commit=True)

        got = EdgeTeam.query.first()
        members_q = got.members

        # 关键断言：不是 HybridQuery，是 SA 原生 Query（AppenderQuery 是 Query 子类）
        assert isinstance(members_q, SAQuery)
        assert not isinstance(members_q, HybridQuery)

    def test_dynamic_relation_terminal_returns_python_native(self, db_setup):
        """AppenderQuery 的 `.all()` / `.count()` 直接返回 Python 原生类型，不是 _HybridTerminal"""
        team = EdgeTeam(name="T1")
        team.save(commit=True)
        EdgeMember(name="M1", team_id=team.id).save(commit=True)
        EdgeMember(name="M2", team_id=team.id).save(commit=True)

        got = EdgeTeam.query.first()

        members_list = got.members.all()
        assert isinstance(members_list, list)
        assert len(members_list) == 2

        count = got.members.count()
        assert isinstance(count, int)
        assert count == 2

    def test_dynamic_relation_terminal_await_on_list_raises_typeerror(self, db_setup):
        """演示：AppenderQuery.all() 返回 list，对 list 做 await 必然 TypeError。

        固化 HybridQuery 不覆盖 dynamic relation 的事实 —— 在 async 下写
        ``await team.members.all()`` 会触发 ``TypeError: object list can't be used
        in 'await' expression``。上游使用者必须改走 joinedload 或 async_db_call。

        用 ``asyncio.run`` 模拟 async 上下文，避免 ``pytest.mark.asyncio`` + 直接
        ``team.save()`` 会踩 primary_key_generators.py:290 的已知 trap（详见 23 号清单
        Phase 7B 发现项 1）。
        """
        import asyncio

        team = EdgeTeam(name="T1")
        team.save(commit=True)
        EdgeMember(name="M1", team_id=team.id).save(commit=True)
        EdgeMember(name="M2", team_id=team.id).save(commit=True)

        got = EdgeTeam.query.first()
        result = got.members.all()
        assert isinstance(result, list)
        assert len(result) == 2

        async def _oops():
            await result  # list 不可 await

        with pytest.raises(TypeError):
            asyncio.run(_oops())


# ==================== Phase 7B 发现项 1 修复回归 ====================


class TestPrimaryKeyInAsyncContext:
    """主键生成器在 async 上下文下的回归（Phase 7B 发现项 1 修复）。

    背景：``primary_key_generators.py::generate_with_retry`` 是 SA ``before_insert``
    钩子的下游（钩子本身同步）。但用户在 ``async def`` 里直接 ``Model(...).save()`` 时，
    ``model_class.query.filter_by(id=new_id).first()`` 原会返回 ``_HybridTerminal``
    代替 None，被误判为「主键冲突」→ 死循环重试 → ``RuntimeError: 生成主键失败``。

    修复：钩子内部用 ``allow_sync()`` 显式声明本次查询是本地幂等的冲突检测，
    强制走 sync 路径（不论 ``HybridQuery`` 是否启用都拿到真值或 None）。

    这不代表在 async def 里直接 ``.save()`` 是被推荐的写法 —— 它仍会阻塞事件循环，
    文档仍引导用 ``def`` 路由 / ``async_db_call`` / ``db_session_scope``。本回归只是保证
    框架**不再向用户抛一个指向错误方向的 RuntimeError**。
    """

    @pytest.mark.asyncio
    async def test_save_in_async_def_does_not_loop_primary_key(self, db_setup):
        """回归：async def 里直接 save()，pk_generator 正常生成 id（不再死循环）"""
        u = EdgeAuthor(name="pk-async", email="pk@test.com")
        u.save(commit=True)

        assert u.id is not None

        # async 上下文里要 await —— 这里就是验证「save 成功 + 可以 await 查回」的完整闭环
        got = await EdgeAuthor.query.filter(EdgeAuthor.id == u.id).first()
        assert got is not None
        assert got.name == "pk-async"

    @pytest.mark.asyncio
    async def test_consecutive_saves_in_async_def_yield_unique_ids(self, db_setup):
        """边界：async def 连续 save 多个对象，pk 互不冲突（allow_sync 不破坏重试逻辑）"""
        a = EdgeAuthor(name="A", email="a@test.com")
        a.save(commit=True)
        b = EdgeAuthor(name="B", email="b@test.com")
        b.save(commit=True)
        c = EdgeAuthor(name="C", email="c@test.com")
        c.save(commit=True)

        assert a.id != b.id
        assert b.id != c.id
        assert a.id != c.id
