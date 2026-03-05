"""验证约束模块

提供类似 .NET MVC 特性验证风格的约束，可直接在 Pydantic 模型字段上使用。

推荐使用示例（Typed 快捷类）:
    from pydantic import BaseModel
    from yweb import Typed

    class UserCreate(BaseModel):
        phone: Typed.Phone          # 必填手机号
        email: Typed.Email          # 必填邮箱
        website: Typed.Url | None = None  # 可选 URL
        id_card: Typed.IdCard       # 身份证

传统使用示例（Annotated 方式）:
    from pydantic import BaseModel
    from typing import Annotated
    from yweb import StringLength, Phone, Email, Range

    class UserCreate(BaseModel):
        username: Annotated[str, StringLength(min_length=3, max_length=20)]
        phone: Annotated[str, Phone]
        email: Annotated[str, Email]
        age: Annotated[int, Range(ge=1, le=150)]
"""

from .constraints import (
    # ===== 推荐使用 =====
    Typed,                      # 验证类型快捷类
    
    # ===== 约束函数（Annotated 方式） =====
    StringLength,
    RegularExpression,
    Range,
    
    # ===== 验证器（高级用法） =====
    Phone,
    Email,
    Url,
    IdCard,
    CreditCard,
    OptionalPhone,
    OptionalEmail,
    OptionalUrl,
    OptionalIdCard,
    
    # ===== 底层纯验证函数（供 Service 层使用） =====
    is_valid_phone,
    is_valid_email,
    get_supported_phone_regions,
    register_phone_region,
)

__all__ = [
    # ===== 推荐使用 =====
    "Typed",                    # 验证类型快捷类：Typed.Phone, Typed.Email 等
    
    # ===== 约束函数 =====
    "StringLength",
    "RegularExpression",
    "Range",
    
    # ===== 验证器（高级用法） =====
    "Phone",
    "Email",
    "Url",
    "IdCard",
    "CreditCard",
    "OptionalPhone",
    "OptionalEmail",
    "OptionalUrl",
    "OptionalIdCard",
    
    # ===== 底层纯验证函数 =====
    "is_valid_phone",
    "is_valid_email",
    "get_supported_phone_regions",
    "register_phone_region",
]
