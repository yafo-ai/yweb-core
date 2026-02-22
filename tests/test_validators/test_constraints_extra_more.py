"""validators.constraints 模块补充测试。"""

from typing import Annotated, Optional

import pytest
from pydantic import BaseModel, ValidationError

import yweb.validators.constraints as cst


class ConstraintDemoModel(BaseModel):
    phone: cst.Typed.Phone
    email: cst.Typed.Email
    website: Optional[cst.Typed.Url] = None
    id_card: cst.Typed.IdCard
    card: cst.Typed.CreditCard
    nickname: Annotated[str, cst.StringLength(min_length=2, max_length=10)]
    score: Annotated[int, cst.Range(ge=1, le=100)]
    account: Annotated[str, cst.RegularExpression(r"^[a-zA-Z0-9_]{3,10}$")]


class OptionalConstraintDemoModel(BaseModel):
    phone: cst.Typed.OptionalPhone = None
    email: cst.Typed.OptionalEmail = None
    website: cst.Typed.OptionalUrl = None
    id_card: cst.Typed.OptionalIdCard = None


class TestConstraintsExtraMore:
    """constraints.py 低覆盖分支补测。"""

    def test_is_valid_phone_email_and_region_register(self):
        assert cst.is_valid_phone("13812345678", region="CN") is True
        assert cst.is_valid_phone(" 13812345678 ", region="cn") is True
        assert cst.is_valid_phone("2125551234", region="US") is True
        assert cst.is_valid_phone("09012345678", region="JP") is True
        assert cst.is_valid_phone("51234567", region="HK") is True
        assert cst.is_valid_phone("0912345678", region="TW") is True
        assert cst.is_valid_phone("123", region="CN") is False
        assert cst.is_valid_phone("", region="CN") is False
        assert cst.is_valid_phone("13812345678", region="XX") is False

        assert cst.is_valid_email("a.b+1@test.com") is True
        assert cst.is_valid_email("bad-email") is False
        assert cst.is_valid_email("") is False

        cst.register_phone_region("ZZ", r"^\d{6}$")
        assert "ZZ" in cst.get_supported_phone_regions()
        assert cst.is_valid_phone("123456", region="zz") is True

    def test_plain_validators_success_and_failures(self):
        assert cst._validate_phone(" 13812345678 ") == "13812345678"
        with pytest.raises(Exception, match="手机号格式不正确"):
            cst._validate_phone("100")

        assert cst._validate_email("  a@b.com ") == "a@b.com"
        with pytest.raises(Exception, match="邮箱格式不正确"):
            cst._validate_email("a@b")

        assert cst._validate_url(" https://example.com ") == "https://example.com"
        with pytest.raises(Exception, match="URL 格式不正确"):
            cst._validate_url("ftp://example.com")

        # 常用公开示例身份证号，校验码有效
        assert cst._validate_id_card("11010519491231002X") == "11010519491231002X"
        assert cst._validate_id_card("11010519491231002x") == "11010519491231002X"
        with pytest.raises(Exception, match="身份证号格式不正确"):
            cst._validate_id_card("123")
        with pytest.raises(Exception, match="身份证号校验码不正确"):
            cst._validate_id_card("110105194912310021")

        assert cst._validate_credit_card("4111 1111 1111 1111") == "4111111111111111"
        with pytest.raises(Exception, match="长度不正确"):
            cst._validate_credit_card("123")
        with pytest.raises(Exception, match="校验失败"):
            cst._validate_credit_card("4111111111111112")

    def test_optional_validators(self):
        assert cst._validate_optional_phone(None) is None
        assert cst._validate_optional_phone("") is None
        assert cst._validate_optional_phone("13812345678") == "13812345678"

        assert cst._validate_optional_email(None) is None
        assert cst._validate_optional_email("") is None
        assert cst._validate_optional_email("x@y.com") == "x@y.com"

        assert cst._validate_optional_url(None) is None
        assert cst._validate_optional_url("") is None
        assert cst._validate_optional_url("https://x.com") == "https://x.com"

        assert cst._validate_optional_id_card(None) is None
        assert cst._validate_optional_id_card("") is None
        assert cst._validate_optional_id_card("11010519491231002X") == "11010519491231002X"
        with pytest.raises(Exception, match="手机号格式不正确"):
            cst._validate_optional_phone("   ")

    def test_constraint_builders(self):
        string_length = cst.StringLength(min_length=2, max_length=5)
        assert string_length.min_length == 2
        assert string_length.max_length == 5

        regex = cst.RegularExpression(r"^[a-z]+$")
        assert regex.pattern == r"^[a-z]+$"

        rng = cst.Range(gt=1, lt=10)
        assert any(getattr(meta, "gt", None) == 1 for meta in rng.metadata)
        assert any(getattr(meta, "lt", None) == 10 for meta in rng.metadata)

    def test_pydantic_types_and_typed_aliases(self):
        m = ConstraintDemoModel(
            phone="13812345678",
            email="valid@test.com",
            website="https://example.com/a?b=1",
            id_card="11010519491231002X",
            card="4111111111111111",
            nickname="abc",
            score=88,
            account="user_01",
        )
        assert m.phone == "13812345678"
        assert m.email == "valid@test.com"
        assert m.score == 88

        with pytest.raises(ValidationError):
            ConstraintDemoModel(
                phone="123",
                email="bad",
                website="x",
                id_card="110105194912310021",
                card="111",
                nickname="a",
                score=101,
                account="**",
            )

        om = OptionalConstraintDemoModel(phone="", email="", website="", id_card="")
        assert om.phone is None
        assert om.email is None
        assert om.website is None
        assert om.id_card is None
