"""登录审计模块测试"""

from datetime import datetime, timezone

from yweb.auth.audit import LoginAttempt, LoginAuditService, LoginFailureReason, LoginStatus


class FieldExpr:
    """简化版字段表达式对象，用于验证查询条件。"""

    def __init__(self, op: str, field: str, value):
        self.op = op
        self.field = field
        self.value = value


class FakeField:
    """模拟 ORM 字段，支持比较与排序表达式。"""

    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other):
        return FieldExpr("eq", self.name, other)

    def __ge__(self, other):
        return FieldExpr("ge", self.name, other)

    def __lt__(self, other):
        return FieldExpr("lt", self.name, other)

    def desc(self):
        return ("desc", self.name)


class FakeQuery:
    """链式查询桩，记录调用轨迹并返回可控结果。"""

    def __init__(self):
        self.filters = []
        self.order_by_expr = None
        self.offset_value = 0
        self.limit_value = None
        self.group_by_exprs = ()
        self.entities = ()
        self._all_result = []
        self._first_result = None
        self._count_result = 0
        self.deleted = False

    def filter(self, *exprs):
        self.filters.extend(exprs)
        return self

    def order_by(self, expr):
        self.order_by_expr = expr
        return self

    def offset(self, value: int):
        self.offset_value = value
        return self

    def limit(self, value: int):
        self.limit_value = value
        return self

    def with_entities(self, *entities):
        self.entities = entities
        return self

    def group_by(self, *exprs):
        self.group_by_exprs = exprs
        return self

    def all(self):
        return self._all_result

    def first(self):
        return self._first_result

    def count(self):
        return self._count_result

    def delete(self):
        self.deleted = True
        return self


class FakeLoginRecord:
    """模拟登录记录模型。"""

    user_id = FakeField("user_id")
    username = FakeField("username")
    ip_address = FakeField("ip_address")
    status = FakeField("status")
    login_at = FakeField("login_at")
    id = FakeField("id")
    query = FakeQuery()

    def __init__(self, **kwargs):
        self.add_called_with = None
        for key, value in kwargs.items():
            setattr(self, key, value)

    def add(self, commit: bool):
        self.add_called_with = commit


class TestAuditEnums:
    """枚举契约测试。"""

    def test_login_status_contains_required_values(self):
        """状态枚举包含关键契约值。"""
        statuses = {item.value for item in LoginStatus}
        assert {"success", "failed", "locked", "disabled", "expired", "mfa_required", "mfa_failed"}.issubset(statuses)

    def test_login_failure_reason_contains_required_values(self):
        """失败原因枚举包含关键契约值。"""
        reasons = {item.value for item in LoginFailureReason}
        assert {"invalid_username", "invalid_password", "account_locked", "too_many_attempts", "unknown"}.issubset(reasons)


class TestLoginAttempt:
    """登录尝试数据类行为测试。"""

    def test_default_status_is_success(self):
        """默认状态应为 success。"""
        attempt = LoginAttempt(username="user", ip_address="127.0.0.1")
        assert attempt.status == "success"
        assert attempt.failure_reason is None

    def test_failed_attempt_keeps_failure_reason(self):
        """失败登录应保留失败原因。"""
        attempt = LoginAttempt(
            username="baduser",
            ip_address="192.168.1.100",
            status="failed",
            failure_reason="invalid_password",
        )
        assert attempt.status == "failed"
        assert attempt.failure_reason == "invalid_password"


class TestLoginAuditService:
    """登录审计服务行为测试（无数据库）。"""

    def setup_method(self):
        """每个测试重置 query 桩，避免状态污染。"""
        FakeLoginRecord.query = FakeQuery()

    def test_record_login_sets_login_time_and_add_commit(self):
        """记录登录时应写入时区时间并调用 add(commit)。"""
        service = LoginAuditService(FakeLoginRecord)
        record = service.record_login(
            username="testuser",
            ip_address="192.168.1.1",
            status=LoginStatus.SUCCESS.value,
            commit=False,
        )
        assert record.username == "testuser"
        assert record.ip_address == "192.168.1.1"
        assert record.add_called_with is False
        assert isinstance(record.login_at, datetime)
        assert record.login_at.tzinfo is not None

    def test_record_success_uses_success_status(self):
        """record_success 应强制使用 success 状态。"""
        service = LoginAuditService(FakeLoginRecord)
        record = service.record_success(user_id=1, username="ok", ip_address="1.1.1.1")
        assert record.user_id == 1
        assert record.status == LoginStatus.SUCCESS.value

    def test_record_failure_uses_failed_status_and_reason(self):
        """record_failure 应强制写 failed 且保留原因。"""
        service = LoginAuditService(FakeLoginRecord)
        record = service.record_failure(
            username="bad",
            ip_address="2.2.2.2",
            failure_reason=LoginFailureReason.INVALID_PASSWORD.value,
        )
        assert record.status == LoginStatus.FAILED.value
        assert record.failure_reason == LoginFailureReason.INVALID_PASSWORD.value

    def test_get_recent_failures_with_ip_applies_ip_filter(self):
        """查询最近失败登录时应附加用户名、失败状态、时间与 IP 过滤。"""
        FakeLoginRecord.query._count_result = 3
        service = LoginAuditService(FakeLoginRecord)
        count = service.get_recent_failures("alice", minutes=30, ip_address="3.3.3.3")
        assert count == 3

        filters = FakeLoginRecord.query.filters
        assert any(expr.op == "eq" and expr.field == "username" and expr.value == "alice" for expr in filters)
        assert any(expr.op == "eq" and expr.field == "status" and expr.value == LoginStatus.FAILED.value for expr in filters)
        assert any(expr.op == "eq" and expr.field == "ip_address" and expr.value == "3.3.3.3" for expr in filters)
        time_expr = next(expr for expr in filters if expr.op == "ge" and expr.field == "login_at")
        assert isinstance(time_expr.value, datetime)
        assert time_expr.value.tzinfo is not None

    def test_get_user_login_history_applies_status_offset_limit_and_order(self):
        """用户历史查询应应用过滤、分页和倒序。"""
        expected = [object(), object()]
        FakeLoginRecord.query._all_result = expected
        service = LoginAuditService(FakeLoginRecord)

        result = service.get_user_login_history(
            user_id=7,
            status=LoginStatus.FAILED.value,
            limit=5,
            offset=10,
        )
        assert result == expected
        assert FakeLoginRecord.query.order_by_expr == ("desc", "login_at")
        assert FakeLoginRecord.query.offset_value == 10
        assert FakeLoginRecord.query.limit_value == 5
        assert any(expr.op == "eq" and expr.field == "user_id" and expr.value == 7 for expr in FakeLoginRecord.query.filters)
        assert any(expr.op == "eq" and expr.field == "status" and expr.value == LoginStatus.FAILED.value for expr in FakeLoginRecord.query.filters)

    def test_count_logins_by_status_returns_mapping(self):
        """状态统计应将查询结果转为字典。"""
        FakeLoginRecord.query._all_result = [("success", 9), ("failed", 2)]
        service = LoginAuditService(FakeLoginRecord)
        result = service.count_logins_by_status(user_id=1, days=15)
        assert result == {"success": 9, "failed": 2}
        assert FakeLoginRecord.query.group_by_exprs == (FakeLoginRecord.status,)
        assert any(expr.op == "eq" and expr.field == "user_id" and expr.value == 1 for expr in FakeLoginRecord.query.filters)
        assert any(expr.op == "ge" and expr.field == "login_at" for expr in FakeLoginRecord.query.filters)

    def test_cleanup_old_records_keep_failures_only_deletes_success(self):
        """保留失败记录时，只应删除旧 success 记录。"""
        FakeLoginRecord.query._count_result = 4
        service = LoginAuditService(FakeLoginRecord)
        deleted_count = service.cleanup_old_records(days=90, keep_failures=True)
        assert deleted_count == 4
        assert FakeLoginRecord.query.deleted is True
        assert any(expr.op == "lt" and expr.field == "login_at" for expr in FakeLoginRecord.query.filters)
        assert any(expr.op == "eq" and expr.field == "status" and expr.value == LoginStatus.SUCCESS.value for expr in FakeLoginRecord.query.filters)
