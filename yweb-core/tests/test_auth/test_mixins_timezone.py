"""mixins.py 时区比较 bug 回归测试

背景：
    ``LockableMixin.check_lock_expired()`` 和 ``PasswordMixin.is_password_expired``
    过去直接用 ``datetime.now(timezone.utc)`` 和 ``self.locked_until`` /
    ``self.password_changed_at`` 做比较。

    列声明为 ``DateTime(timezone=True)``，但该类型在 SQLite / MySQL 上是 no-op：
    驱动读回的是 **naive** datetime。naive vs aware 直接比较会抛：

        TypeError: can't compare offset-naive and offset-aware datetimes

修复：``_as_utc(dt)`` 把 naive 视为 UTC 挂上 tzinfo。本测试复现 DB 读回 naive
的场景（直接赋值 ``datetime.utcnow()``），验证修复后不再抛异常且语义正确。

另外再补一个通过真实 SQLite 落库 + 重新查询的集成测试，兜底 SA 版本变化
后行为漂移。
"""

from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker, scoped_session

from yweb.auth.mixins import FullUserMixin, _as_utc
from yweb.orm import BaseModel, CoreModel


# ==================== _as_utc 辅助函数单测 ====================

class TestAsUtcHelper:
    """_as_utc 辅助函数：bug 修复的最小承载单元。"""

    def test_none_passthrough(self):
        assert _as_utc(None) is None

    def test_naive_is_treated_as_utc(self):
        naive = datetime(2026, 4, 20, 10, 0, 0)
        aware = _as_utc(naive)
        assert aware is not None
        assert aware.tzinfo is timezone.utc
        assert aware.year == 2026 and aware.hour == 10

    def test_aware_passthrough(self):
        aware_in = datetime(2026, 4, 20, 10, 0, 0, tzinfo=timezone.utc)
        aware_out = _as_utc(aware_in)
        assert aware_out is aware_in


# ==================== 直接模拟 DB 读回 naive 的单测 ====================

class _NaiveLockableUser(FullUserMixin):
    """模拟 DB 读回 naive datetime 的用户对象。

    不走 ORM，只靠字段赋值；等价于 SQLite/MySQL 在 ``DateTime(timezone=True)``
    列上读回 naive 的效果。
    """

    def __init__(self):
        self.is_active = True
        self.is_locked = False
        self.locked_at = None
        self.locked_until = None
        self.lock_reason = None
        self.failed_login_attempts = 0
        self.last_failed_login_at = None
        self.password_hash = ""
        self.password_changed_at = None
        self.password_expires_days = 0
        self.must_change_password = False
        self.last_login_at = None
        self.last_login_ip = None
        self.last_login_user_agent = None

    def update(self, commit: bool = True):
        pass


class TestCheckLockExpiredWithNaiveDatetime:
    """模拟 SQLite/MySQL 场景下 locked_until 为 naive 时的比较。"""

    def test_expired_lock_with_naive_datetime(self):
        """locked_until 是 naive 的过去时间 → 已过期，不抛 TypeError。"""
        user = _NaiveLockableUser()
        user.is_locked = True
        user.locked_until = datetime.utcnow() - timedelta(minutes=1)

        assert user.locked_until.tzinfo is None, "前置条件：模拟 DB 读回 naive"
        assert user.check_lock_expired() is True

    def test_not_expired_lock_with_naive_datetime(self):
        """locked_until 是 naive 的未来时间 → 未过期，不抛 TypeError。"""
        user = _NaiveLockableUser()
        user.is_locked = True
        user.locked_until = datetime.utcnow() + timedelta(hours=1)

        assert user.locked_until.tzinfo is None
        assert user.check_lock_expired() is False

    def test_aware_datetime_still_works(self):
        """aware 路径不回归：locked_until 是 aware 过去时间 → 已过期。"""
        user = _NaiveLockableUser()
        user.is_locked = True
        user.locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)

        assert user.check_lock_expired() is True


class TestIsPasswordExpiredWithNaiveDatetime:
    """模拟 SQLite/MySQL 场景下 password_changed_at 为 naive 时的比较。"""

    def test_expired_password_with_naive_datetime(self):
        user = _NaiveLockableUser()
        user.password_expires_days = 30
        user.password_changed_at = datetime.utcnow() - timedelta(days=60)

        assert user.password_changed_at.tzinfo is None
        assert user.is_password_expired is True

    def test_not_expired_password_with_naive_datetime(self):
        user = _NaiveLockableUser()
        user.password_expires_days = 30
        user.password_changed_at = datetime.utcnow() - timedelta(days=1)

        assert user.password_changed_at.tzinfo is None
        assert user.is_password_expired is False


# ==================== 真实 SQLite 落库 + 重查回归 ====================

class _LockableTestUser(FullUserMixin, BaseModel):
    """走真实 ORM 的测试模型。"""

    __tablename__ = "test_mixins_tz_users"
    __table_args__ = {'extend_existing': True}

    username: Mapped[str] = mapped_column(String(64), unique=True)


class TestCheckLockExpiredRoundTrip:
    """走真实 SQLite round-trip：保证 SA 版本变化后也有兜底。

    即使 SA 未来在 SQLite 上把 ``DateTime(timezone=True)`` 的返回值改回 aware，
    本测试仍成立（aware 路径也被 ``_as_utc`` 原样透传）。
    """

    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=memory_engine
        )
        session_scope = scoped_session(SessionLocal)
        CoreModel.query = session_scope.query_property()
        self._session_scope = session_scope
        yield
        session_scope.remove()

    def test_roundtrip_expired_lock(self):
        user = _LockableTestUser(username="alice", password_hash="x")
        user.is_locked = True
        user.locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)

        session = self._session_scope()
        session.add(user)
        session.commit()
        session.expire_all()

        refetched = _LockableTestUser.query.filter_by(username="alice").one()
        assert refetched.check_lock_expired() is True

    def test_roundtrip_not_expired_lock(self):
        user = _LockableTestUser(username="bob", password_hash="x")
        user.is_locked = True
        user.locked_until = datetime.now(timezone.utc) + timedelta(hours=1)

        session = self._session_scope()
        session.add(user)
        session.commit()
        session.expire_all()

        refetched = _LockableTestUser.query.filter_by(username="bob").one()
        assert refetched.check_lock_expired() is False

    def test_roundtrip_password_expired(self):
        user = _LockableTestUser(username="carol", password_hash="x")
        user.password_expires_days = 30
        user.password_changed_at = datetime.now(timezone.utc) - timedelta(days=60)

        session = self._session_scope()
        session.add(user)
        session.commit()
        session.expire_all()

        refetched = _LockableTestUser.query.filter_by(username="carol").one()
        assert refetched.is_password_expired is True
