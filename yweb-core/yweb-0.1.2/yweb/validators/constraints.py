"""验证约束定义

提供类似 .NET MVC 特性验证风格的约束，支持：
- StringLength: 字符串长度验证
- RegularExpression: 正则表达式验证
- Range: 数值范围验证
- Phone: 手机号验证
- Email: 邮箱验证
- Url: URL 验证
- IdCard: 身份证验证
- CreditCard: 信用卡验证

使用示例:
    from typing import Annotated
    from pydantic import BaseModel
    from yweb.validators import StringLength, Phone, Email, Range

    class UserCreate(BaseModel):
        username: Annotated[str, StringLength(min_length=3, max_length=20)]
        phone: Annotated[str, Phone]
        email: Annotated[str, Email]
        age: Annotated[int, Range(ge=1, le=150)]
"""

from typing import Annotated, Optional
from pydantic import Field, StringConstraints
from pydantic.functional_validators import BeforeValidator
from pydantic_core import PydanticCustomError
import re


# ==================== 约束函数（类似 .NET 特性） ====================

def StringLength(min_length: int = None, max_length: int = None):
    """字符串长度约束（类似 .NET [StringLength] / [MinLength] / [MaxLength]）
    
    Args:
        min_length: 最小长度
        max_length: 最大长度
        
    Example:
        username: Annotated[str, StringLength(min_length=3, max_length=20)]
    """
    return StringConstraints(min_length=min_length, max_length=max_length)


def RegularExpression(pattern: str):
    """正则表达式约束（类似 .NET [RegularExpression]）
    
    Args:
        pattern: 正则表达式模式
        
    Example:
        password: Annotated[str, RegularExpression(r"^[a-zA-Z0-9_]{8,30}$")]
    """
    return StringConstraints(pattern=pattern)


def Range(ge: int = None, le: int = None, gt: int = None, lt: int = None):
    """数值范围约束（类似 .NET [Range]）
    
    Args:
        ge: 大于或等于
        le: 小于或等于
        gt: 大于
        lt: 小于
        
    Example:
        age: Annotated[int, Range(ge=1, le=150)]
        score: Annotated[float, Range(ge=0, le=100)]
    """
    return Field(ge=ge, le=le, gt=gt, lt=lt)


# ==================== 底层纯验证函数（无框架依赖） ====================
# 这些函数是验证逻辑的唯一来源，供 Pydantic 约束和 Service 层共同使用

# 各地区手机号正则
_PHONE_PATTERNS = {
    "CN": re.compile(r"^1[3-9]\d{9}$"),          # 中国大陆
    "US": re.compile(r"^\d{10}$"),                 # 美国（10位）
    "JP": re.compile(r"^0[789]0\d{8}$"),           # 日本
    "HK": re.compile(r"^[5-9]\d{7}$"),             # 香港
    "TW": re.compile(r"^09\d{8}$"),                # 台湾
}

_EMAIL_PATTERN = re.compile(
    r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
)


def is_valid_phone(phone: str, region: str = "CN") -> bool:
    """验证手机号格式（纯函数，无副作用）
    
    Args:
        phone: 手机号
        region: 地区代码（CN/US/JP/HK/TW）
        
    Returns:
        是否格式正确
    """
    if not phone:
        return False
    pattern = _PHONE_PATTERNS.get(region.upper())
    if pattern is None:
        return False
    return bool(pattern.match(phone.strip()))


def is_valid_email(email: str) -> bool:
    """验证邮箱格式（纯函数，无副作用）
    
    Args:
        email: 邮箱地址
        
    Returns:
        是否格式正确
    """
    if not email:
        return False
    return bool(_EMAIL_PATTERN.match(email.strip()))


def get_supported_phone_regions() -> list:
    """获取支持的手机号地区列表"""
    return list(_PHONE_PATTERNS.keys())


def register_phone_region(region: str, pattern: str) -> None:
    """注册新的地区手机号格式
    
    Args:
        region: 地区代码
        pattern: 正则表达式字符串
    """
    _PHONE_PATTERNS[region.upper()] = re.compile(pattern)


# ==================== Pydantic 验证函数（包装底层函数） ====================

def _validate_phone(v: str) -> str:
    """验证中国大陆手机号（Pydantic 包装）"""
    if v is None:
        return v
    v = str(v).strip()
    if not is_valid_phone(v, region="CN"):
        raise PydanticCustomError(
            "value_error.phone",
            "手机号格式不正确，请输入11位有效手机号"
        )
    return v


def _validate_email(v: str) -> str:
    """验证邮箱格式（Pydantic 包装）"""
    if v is None:
        return v
    v = str(v).strip()
    if not is_valid_email(v):
        raise PydanticCustomError(
            "value_error.email",
            "邮箱格式不正确"
        )
    return v


def _validate_url(v: str) -> str:
    """验证 URL 格式"""
    if v is None:
        return v
    v = str(v).strip()
    if not re.match(r"^https?://[^\s/$.?#].[^\s]*$", v):
        raise PydanticCustomError(
            "value_error.url",
            "URL 格式不正确，需要以 http:// 或 https:// 开头"
        )
    return v


def _validate_id_card(v: str) -> str:
    """验证中国大陆身份证号（18位）"""
    if v is None:
        return v
    v = str(v).strip().upper()
    
    # 基本格式校验
    if not re.match(r"^\d{17}[\dX]$", v):
        raise PydanticCustomError(
            "value_error.id_card",
            "身份证号格式不正确，需要18位"
        )
    
    # 校验码验证
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    check_codes = "10X98765432"
    total = sum(int(v[i]) * weights[i] for i in range(17))
    expected_check = check_codes[total % 11]
    
    if v[17] != expected_check:
        raise PydanticCustomError(
            "value_error.id_card",
            "身份证号校验码不正确"
        )
    
    return v


def _validate_credit_card(v: str) -> str:
    """验证信用卡号（Luhn 算法）"""
    if v is None:
        return v
    
    # 只保留数字
    digits = re.sub(r"\D", "", str(v))
    
    if len(digits) < 13 or len(digits) > 19:
        raise PydanticCustomError(
            "value_error.credit_card",
            "信用卡号长度不正确（应为13-19位数字）"
        )
    
    # Luhn 算法校验
    def luhn_check(card_number: str) -> bool:
        digits = [int(d) for d in card_number]
        odd_digits = digits[-1::-2]
        even_digits = digits[-2::-2]
        total = sum(odd_digits)
        for d in even_digits:
            d = d * 2
            if d > 9:
                d = d - 9
            total += d
        return total % 10 == 0
    
    if not luhn_check(digits):
        raise PydanticCustomError(
            "value_error.credit_card",
            "信用卡号校验失败"
        )
    
    return digits


def _validate_optional_phone(v: Optional[str]) -> Optional[str]:
    """验证可选的手机号"""
    if v is None or v == "":
        return None
    return _validate_phone(v)


def _validate_optional_email(v: Optional[str]) -> Optional[str]:
    """验证可选的邮箱"""
    if v is None or v == "":
        return None
    return _validate_email(v)


def _validate_optional_url(v: Optional[str]) -> Optional[str]:
    """验证可选的 URL"""
    if v is None or v == "":
        return None
    return _validate_url(v)


def _validate_optional_id_card(v: Optional[str]) -> Optional[str]:
    """验证可选的身份证号"""
    if v is None or v == "":
        return None
    return _validate_id_card(v)


# ==================== 预定义验证类型（类似 .NET 内置特性） ====================

# [Phone] 手机号验证
Phone = BeforeValidator(_validate_phone)

# [EmailAddress] 邮箱验证
Email = BeforeValidator(_validate_email)

# [Url] URL 验证
Url = BeforeValidator(_validate_url)

# [IdCard] 身份证验证（中国大陆）
IdCard = BeforeValidator(_validate_id_card)

# [CreditCard] 信用卡验证
CreditCard = BeforeValidator(_validate_credit_card)

# 可选的验证类型（允许 None 或空字符串）
OptionalPhone = BeforeValidator(_validate_optional_phone)
OptionalEmail = BeforeValidator(_validate_optional_email)
OptionalUrl = BeforeValidator(_validate_optional_url)
OptionalIdCard = BeforeValidator(_validate_optional_id_card)


# ==================== 预组合类型（开箱即用） ====================

# 直接作为类型使用，无需 Annotated
PhoneStr = Annotated[str, Phone]
EmailStr = Annotated[str, Email]
UrlStr = Annotated[str, Url]
IdCardStr = Annotated[str, IdCard]
CreditCardStr = Annotated[str, CreditCard]

# 可选类型
OptionalPhoneStr = Annotated[Optional[str], OptionalPhone]
OptionalEmailStr = Annotated[Optional[str], OptionalEmail]
OptionalUrlStr = Annotated[Optional[str], OptionalUrl]
OptionalIdCardStr = Annotated[Optional[str], OptionalIdCard]


# ==================== 验证类型快捷类（推荐） ====================

class Typed:
    """验证类型快捷类
    
    只需导入一个类，IDE 自动补全所有验证类型。
    
    使用示例:
        from yweb import Typed
        
        class UserCreate(BaseModel):
            phone: Typed.Phone          # 必填手机号
            email: Typed.Email          # 必填邮箱
            website: Typed.Url | None = None  # 可选 URL
            id_card: Typed.IdCard       # 身份证
            
        class UserUpdate(BaseModel):
            # 可选类型（允许 None 或空字符串）
            phone: Typed.OptionalPhone = None
            email: Typed.OptionalEmail = None
    """
    
    # ===== 必填类型 =====
    Phone: type = PhoneStr
    """手机号（中国大陆11位）"""
    
    Email: type = EmailStr
    """邮箱地址"""
    
    Url: type = UrlStr
    """URL（http/https）"""
    
    IdCard: type = IdCardStr
    """身份证号（中国大陆18位，含校验）"""
    
    CreditCard: type = CreditCardStr
    """信用卡号（Luhn算法校验）"""
    
    # ===== 可选类型（允许 None 或空字符串） =====
    OptionalPhone: type = OptionalPhoneStr
    """可选手机号"""
    
    OptionalEmail: type = OptionalEmailStr
    """可选邮箱"""
    
    OptionalUrl: type = OptionalUrlStr
    """可选URL"""
    
    OptionalIdCard: type = OptionalIdCardStr
    """可选身份证号"""
