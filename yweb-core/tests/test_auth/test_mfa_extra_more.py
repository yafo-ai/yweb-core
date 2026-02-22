"""MFA manager/otp 额外分支测试（新文件）"""

from datetime import datetime, timedelta, timezone

from yweb.auth.mfa.base import MFAProvider, MFASetupData, MFAType, MFAVerifyResult
from yweb.auth.mfa.manager import MFAManager
from yweb.auth.mfa.otp import EmailProvider, OTPCode, OTPProvider, SMSProvider, generate_alphanumeric_code


class DummyProvider(MFAProvider):
    def __init__(self, ok: bool = True):
        self._ok = ok
        self.disabled_users = []

    @property
    def mfa_type(self) -> MFAType:
        return MFAType.SMS

    def setup(self, user_id, **kwargs):
        _ = kwargs
        return MFASetupData(mfa_type=self.mfa_type, extra={"uid": user_id})

    def verify(self, user_id, code: str, **kwargs):
        _ = (user_id, code, kwargs)
        return MFAVerifyResult.ok("ok") if self._ok else MFAVerifyResult.fail("bad")

    def disable(self, user_id):
        self.disabled_users.append(user_id)
        return True


class TestMfaManagerExtra:
    def test_config_store_getter_and_unregister(self):
        saved = {}
        manager = MFAManager().set_user_config_stores(
            store=lambda uid, cfg: saved.update({uid: cfg}) or True,
            getter=lambda uid: saved.get(uid),
        )
        provider = DummyProvider(ok=True)
        manager.register_provider("sms", provider)
        assert manager.get_provider("sms") is provider
        assert "sms" in manager.list_providers()

        setup_data = manager.setup(user_id=1, provider_name="sms")
        assert setup_data is not None
        assert saved[1]["enabled_providers"] == ["sms"]

        # 再次 setup 不应重复追加 provider
        manager.setup(user_id=1, provider_name="sms")
        assert saved[1]["enabled_providers"] == ["sms"]

        assert manager.unregister_provider("sms") is manager
        assert manager.get_provider("sms") is None
        # 不存在也不报错
        assert manager.unregister_provider("sms") is manager

    def test_verify_and_verify_any_branches(self):
        manager = MFAManager()
        # provider 不存在
        result = manager.verify(user_id=1, provider_name="none", code="123")
        assert result.success is False

        # verify_any 无启用
        none_result = manager.verify_any(user_id=1, code="123")
        assert none_result.success is False

        # verify_any 尝试多个，前失败后成功
        p_fail = DummyProvider(ok=False)
        p_ok = DummyProvider(ok=True)
        manager.register_provider("a", p_fail).register_provider("b", p_ok)
        manager._save_user_config(1, {"enabled_providers": ["a", "b"]})
        any_result = manager.verify_any(user_id=1, code="123")
        assert any_result.success is True

        # 全失败
        manager.register_provider("b", DummyProvider(ok=False))
        any_fail = manager.verify_any(user_id=1, code="123")
        assert any_fail.success is False
        assert manager.is_enabled(1) is True
        assert manager.is_enabled(999) is False

    def test_disable_disable_all_and_primary(self):
        manager = MFAManager()
        p1 = DummyProvider(ok=True)
        p2 = DummyProvider(ok=True)
        manager.register_provider("p1", p1).register_provider("p2", p2)
        manager._save_user_config(10, {"enabled_providers": ["p1", "p2"]})

        assert manager.disable(user_id=10, provider_name="p1") is True
        assert "p1" not in manager.get_enabled_providers(10)
        assert 10 in p1.disabled_users

        # disable 未注册 provider 也返回 True
        assert manager.disable(user_id=10, provider_name="unknown") is True

        # disable_all 时若某个 provider 缺失，不应报错
        manager.unregister_provider("p2")
        assert manager.disable_all(user_id=10) is True
        assert manager.get_enabled_providers(10) == []

        # 可用 provider 列表与 enabled 标记
        manager.register_provider("p1", p1).register_provider("p3", DummyProvider(ok=True))
        manager._save_user_config(10, {"enabled_providers": ["p1"]})
        available = manager.get_available_providers(10)
        names = {x["name"]: x["enabled"] for x in available}
        assert names["p1"] is True and names["p3"] is False

        # primary provider 分支
        assert manager.set_primary_provider(10, "notfound") is False
        assert manager.set_primary_provider(10, "p1") is True
        assert manager.get_primary_provider(10) == "p1"

        manager._save_user_config(10, {"enabled_providers": ["p3"], "primary_provider": "p1"})
        assert manager.get_primary_provider(10) == "p3"
        assert manager.get_primary_provider(999) is None


class TestOtpExtra:
    def test_otpcode_validity_and_generator(self):
        now = datetime.now(timezone.utc)
        code = OTPCode(
            code="ABC123",
            user_id=1,
            created_at=now,
            expires_at=now + timedelta(minutes=1),
            attempts=0,
            max_attempts=2,
        )
        assert code.is_valid() is True
        code.attempts = 2
        assert code.is_valid() is False
        assert len(generate_alphanumeric_code(8)) == 8

    def test_otp_provider_store_getter_consumer_and_verify_branches(self):
        mem = {}
        consumed = set()

        def store(uid, otp):
            mem[uid] = otp
            return True

        def getter(uid):
            return mem.get(uid)

        def consumer(uid):
            consumed.add(uid)
            return True

        provider = OTPProvider(
            mfa_type=MFAType.EMAIL,
            code_length=6,
            expire_minutes=5,
            max_attempts=2,
            numeric_only=False,
            rate_limit_minutes=1,
        ).set_stores(store=store, getter=getter, consumer=consumer)

        assert provider.mfa_type == MFAType.EMAIL
        setup_data = provider.setup(user_id=1)
        assert setup_data.extra["code_length"] == 6

        first = provider.generate_code(user_id=1, target="a@b.com")
        assert first is not None
        # 频率限制触发（同一用户立即二次发送）
        second = provider.generate_code(user_id=1, target="a@b.com")
        assert second is None

        # 无 code
        none_provider = OTPProvider(mfa_type=MFAType.SMS)
        assert none_provider.verify(user_id=999, code="1").success is False

        # 已使用
        used = OTPCode(
            code="AAAAAA",
            user_id=2,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
            is_used=True,
        )
        mem[2] = used
        assert provider.verify(user_id=2, code="AAAAAA").success is False

        # 过期
        expired = OTPCode(
            code="BBBBBB",
            user_id=3,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        mem[3] = expired
        assert provider.verify(user_id=3, code="BBBBBB").success is False

        # 错误码达到最大尝试，触发 consume
        mem[4] = OTPCode(
            code="CCCCCC",
            user_id=4,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=2),
            max_attempts=1,
        )
        result = provider.verify(user_id=4, code="WRONG")
        assert result.success is False
        assert 4 in consumed

        # 正确码（大小写不敏感）
        mem[5] = OTPCode(
            code="AB12CD",
            user_id=5,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=2),
            max_attempts=3,
        )
        ok = provider.verify(user_id=5, code="ab12cd")
        assert ok.success is True
        assert 5 in consumed

        # 错误码但未达到最大尝试次数时，应返回 remaining_attempts
        mem[6] = OTPCode(
            code="ZXCVBN",
            user_id=6,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=2),
            max_attempts=3,
            attempts=0,
        )
        bad = provider.verify(user_id=6, code="xxxxxx")
        assert bad.success is False
        assert bad.remaining_attempts == 2

    def test_sms_and_email_sender_branches(self):
        sms = SMSProvider(rate_limit_minutes=0)
        email = EmailProvider(rate_limit_minutes=0)

        # dev mode
        s1 = sms.send_code(user_id=1, phone="+8613800138000")
        e1 = email.send_code(user_id=1, email="u@test.com")
        assert s1[0] is True and e1[0] is True

        # sender success/fail/exception + setter 覆盖
        sms.set_sms_sender(lambda _p, _c: True)
        assert sms.send_code(user_id=2, phone="+8613800138000")[0] is True
        sms.set_sms_sender(lambda _p, _c: False)
        assert sms.send_code(user_id=3, phone="+8613800138000")[0] is False
        sms.set_sms_sender(lambda _p, _c: (_ for _ in ()).throw(RuntimeError("sms error")))
        assert sms.send_code(user_id=4, phone="+8613800138000")[0] is False

        email.set_email_sender(lambda _e, _c: True)
        assert email.send_code(user_id=12, email="a@b.com")[0] is True
        email.set_email_sender(lambda _e, _c: False)
        assert email.send_code(user_id=13, email="a@b.com")[0] is False
        email.set_email_sender(lambda _e, _c: (_ for _ in ()).throw(RuntimeError("mail error")))
        assert email.send_code(user_id=14, email="a@b.com")[0] is False

        # 触发 rate-limit 返回分支
        sms_rl = SMSProvider(rate_limit_minutes=1)
        assert sms_rl.send_code(user_id=99, phone="+8613800138000")[0] is True
        assert sms_rl.send_code(user_id=99, phone="+8613800138000")[0] is False

        email_rl = EmailProvider(rate_limit_minutes=1)
        assert email_rl.send_code(user_id=98, email="u@test.com")[0] is True
        assert email_rl.send_code(user_id=98, email="u@test.com")[0] is False
