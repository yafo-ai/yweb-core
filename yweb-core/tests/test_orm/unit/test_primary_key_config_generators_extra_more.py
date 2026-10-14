"""primary_key_config / primary_key_generators 额外分支测试（新文件）"""

import re

import pytest

import yweb.orm.primary_key_generators as gen_mod
from yweb.orm.primary_key_config import (
    IdType,
    PrimaryKeyConfig,
    configure_primary_key,
    get_primary_key_config,
)
from yweb.orm.primary_key_generators import (
    PrimaryKeyGenerator,
    SnowflakeIDGenerator,
    create_primary_key_generator,
    generate_short_uuid,
    generate_snowflake_id,
    generate_uuid,
    get_snowflake_generator,
)


class QueryLike:
    def __init__(self, existing_ids=None, raise_on_query=False):
        self.existing_ids = set(existing_ids or [])
        self.raise_on_query = raise_on_query
        self._id = None

    def filter_by(self, **kwargs):
        self._id = kwargs.get("id")
        return self

    def first(self):
        if self.raise_on_query:
            raise RuntimeError("table missing")
        return object() if self._id in self.existing_ids else None


class ModelLike:
    __name__ = "ModelLike"
    query = QueryLike()


class SavepointSession:
    """模拟 ORM session 的 begin_nested()，统计进入 / 回滚次数。"""

    def __init__(self):
        self.entered = 0
        self.rolled_back = 0

    def begin_nested(self):
        outer = self

        class _Ctx:
            def __enter__(self):
                outer.entered += 1
                return self

            def __exit__(self, exc_type, exc, tb):
                if exc_type is not None:
                    outer.rolled_back += 1
                return False  # 不吞异常，交由上层处理

        return _Ctx()


class QueryWithSession(QueryLike):
    """带 session 的 Mock query，用于覆盖 _exists_by_id 的 SAVEPOINT 分支。"""

    def __init__(self, session, existing_ids=None, raise_on_query=False):
        super().__init__(existing_ids=existing_ids, raise_on_query=raise_on_query)
        self.session = session


class TestPrimaryKeyConfigAndGeneratorsExtraMore:
    def test_id_type_repr_and_configure_validations(self):
        assert str(IdType.UUID) == "uuid"
        assert repr(IdType.SNOWFLAKE) == "IdType.SNOWFLAKE"

        with pytest.raises(ValueError):
            PrimaryKeyConfig.configure(strategy=IdType.SHORT_UUID, short_uuid_length=7)
        with pytest.raises(ValueError):
            PrimaryKeyConfig.configure(strategy=IdType.SNOWFLAKE, snowflake_worker_id=32)
        with pytest.raises(ValueError):
            PrimaryKeyConfig.configure(strategy=IdType.SNOWFLAKE, snowflake_datacenter_id=32)
        with pytest.raises(ValueError):
            PrimaryKeyConfig.configure(strategy=IdType.CUSTOM, custom_generator=None)
        with pytest.raises(ValueError):
            PrimaryKeyConfig.configure(strategy=IdType.CUSTOM, custom_generator=123)
        with pytest.raises(ValueError):
            PrimaryKeyConfig.configure(strategy=IdType.UUID, max_retries=0)

        configure_primary_key(strategy=IdType.SHORT_UUID, short_uuid_length=9, max_retries=6)
        assert get_primary_key_config() is PrimaryKeyConfig
        assert PrimaryKeyConfig.get_strategy() == IdType.SHORT_UUID
        assert PrimaryKeyConfig.get_short_uuid_length() == 9
        assert PrimaryKeyConfig.get_max_retries() == 6
        PrimaryKeyConfig.reset()

    def test_uuid_short_uuid_and_factory_branches(self):
        uid = generate_uuid()
        assert len(uid) == 36 and "-" in uid

        sid = generate_short_uuid(8)
        assert len(sid) == 8
        assert re.fullmatch(r"[a-z2-7]+", sid)

        assert callable(create_primary_key_generator(IdType.UUID))
        assert create_primary_key_generator(IdType.AUTO_INCREMENT)() is None
        with pytest.raises(ValueError):
            create_primary_key_generator(IdType.CUSTOM, custom_generator=None)
        with pytest.raises(ValueError):
            create_primary_key_generator("invalid")

    def test_snowflake_generator_core_paths(self, monkeypatch):
        with pytest.raises(ValueError):
            SnowflakeIDGenerator(worker_id=-1, datacenter_id=1)
        with pytest.raises(ValueError):
            SnowflakeIDGenerator(worker_id=1, datacenter_id=-1)

        gen = SnowflakeIDGenerator(worker_id=1, datacenter_id=1)

        # 时钟回拨分支
        gen.last_timestamp = 2000
        monkeypatch.setattr(gen, "_current_millis", lambda: 1000)
        with pytest.raises(RuntimeError):
            gen.generate()

        # 同毫秒 sequence 溢出分支 -> wait next millis
        gen.last_timestamp = 1000
        gen.sequence = gen.MAX_SEQUENCE
        ticks = iter([1000, 1000, 1001])
        monkeypatch.setattr(gen, "_current_millis", lambda: next(ticks))
        out = gen.generate()
        assert isinstance(out, int)

    def test_snowflake_singleton_and_convenience(self):
        gen_mod._snowflake_generator = None
        g1 = get_snowflake_generator(worker_id=2, datacenter_id=3)
        g2 = get_snowflake_generator(worker_id=9, datacenter_id=9)
        assert g1 is g2
        assert isinstance(generate_snowflake_id(), int)
        gen_mod._snowflake_generator = None

    def test_primary_key_generator_retry_and_query_error(self, monkeypatch):
        generator = PrimaryKeyGenerator(max_retries=3)

        # 查询抛错时直接返回
        model_err = type("ModelErr", (), {"__name__": "ModelErr", "query": QueryLike(raise_on_query=True)})
        assert generator.generate_with_retry(model_err, lambda: "X") == "X"

        # 冲突后成功
        model = type("ModelOK", (), {"__name__": "ModelOK", "query": QueryLike(existing_ids={"A"})})
        seq = iter(["A", "A", "B"])
        assert generator.generate_with_retry(model, lambda: next(seq)) == "B"

        # 一直冲突失败
        with pytest.raises(RuntimeError):
            generator.generate_with_retry(model, lambda: "A", max_retries=2)

    def test_dedup_query_runs_inside_savepoint_when_session_present(self):
        """有 session 时，去重检测查询须包在 begin_nested() SAVEPOINT 内。"""
        generator = PrimaryKeyGenerator(max_retries=3)
        sess = SavepointSession()
        model = type(
            "ModelSP",
            (),
            {"__name__": "ModelSP", "query": QueryWithSession(sess, existing_ids={"A"})},
        )
        seq = iter(["A", "B"])
        assert generator.generate_with_retry(model, lambda: next(seq)) == "B"
        # 两次检测各进一次 SAVEPOINT；成功路径不回滚
        assert sess.entered == 2
        assert sess.rolled_back == 0

    def test_dedup_query_failure_rolls_back_savepoint_and_returns_id(self):
        """检测查询失败：回滚 SAVEPOINT（不污染外层事务）后返回 ID，由 INSERT 兜底暴露真错。"""
        generator = PrimaryKeyGenerator(max_retries=3)
        sess = SavepointSession()
        model = type(
            "ModelSPErr",
            (),
            {"__name__": "ModelSPErr", "query": QueryWithSession(sess, raise_on_query=True)},
        )
        assert generator.generate_with_retry(model, lambda: "Z") == "Z"
        assert sess.entered == 1
        assert sess.rolled_back == 1  # 查询异常触发 SAVEPOINT 回滚
