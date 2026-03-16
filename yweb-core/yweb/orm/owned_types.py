"""值对象拥有关系（OwnsOne）类型定义

提供 OwnedType 基类和 owned_field 工厂函数，用于定义可嵌入父模型的值对象。

使用示例:
    from yweb.orm.owned_types import OwnedType, owned_field
    from sqlalchemy import String

    class Address(OwnedType):
        street = owned_field(String(200), comment="街道")
        city = owned_field(String(100), comment="城市")
        province = owned_field(String(100), comment="省份")
        zip_code = owned_field(String(20), comment="邮编", nullable=True)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from sqlalchemy.ext.mutable import MutableComposite


# ==================== 字段元信息 ====================

@dataclass
class OwnedField:
    """值对象字段元信息

    保存字段的列类型、nullable、comment 等配置，
    由 _process_owns_one() 在模型初始化时转换为真正的 mapped_column。
    """
    column_type: Any
    nullable: bool = True
    comment: Optional[str] = None
    default: Any = None
    kwargs: Optional[dict] = field(default=None)


def owned_field(column_type, nullable=True, comment=None, default=None, **kwargs) -> OwnedField:
    """创建值对象字段

    Args:
        column_type: SQLAlchemy 列类型，如 String(200)、Integer
        nullable: 是否允许为空，默认 True
        comment: 数据库列注释
        default: 默认值
        **kwargs: 传递给 mapped_column 的其他参数

    Returns:
        OwnedField 元信息实例
    """
    return OwnedField(
        column_type=column_type,
        nullable=nullable,
        comment=comment,
        default=default,
        kwargs=kwargs or None,
    )


# ==================== 元数据 ====================

@dataclass
class OwnedMeta:
    """OwnsOne 在模型类上注册的元数据

    存储在 cls.__owned_composites__ 中，供 to_dict() 等扩展点使用。
    """
    owned_type: type
    prefix: str
    field_to_column: Dict[str, str]


# ==================== 值对象基类 ====================

class OwnedType(MutableComposite):
    """值对象基类

    继承 MutableComposite 实现原地修改的变更追踪。
    子类通过 owned_field() 声明字段，由 fields.OwnsOne 展开到父模型表中。

    使用示例:
        class Address(OwnedType):
            street = owned_field(String(200), comment="街道")
            city = owned_field(String(100), comment="城市")

    运行时行为:
        - 实例访问: order.shipping_address.city → "上海"
        - 修改追踪: order.shipping_address.city = "北京" → 自动通知 ORM
        - 类访问:   Order.shipping_address.city → 返回列引用（供查询使用）
    """

    __owned_fields__: Dict[str, OwnedField] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        parent_fields = getattr(cls, '__owned_fields__', {})
        own_fields = {
            k: v for k, v in vars(cls).items()
            if isinstance(v, OwnedField)
        }
        if own_fields or parent_fields:
            cls.__owned_fields__ = {**parent_fields, **own_fields}

    def __init__(self, *args, **kwargs):
        field_names = list(self.__owned_fields__.keys())
        for i, name in enumerate(field_names):
            if i < len(args):
                object.__setattr__(self, name, args[i])
            elif name in kwargs:
                object.__setattr__(self, name, kwargs[name])
            else:
                object.__setattr__(self, name, None)

    def __setattr__(self, key, value):
        object.__setattr__(self, key, value)
        if key in self.__owned_fields__:
            self.changed()

    def __composite_values__(self):
        return tuple(getattr(self, name) for name in self.__owned_fields__)

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.__composite_values__() == other.__composite_values__()

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __bool__(self):
        """全部字段为 None 时返回 False，用于判断值对象是否为空"""
        return any(getattr(self, name) is not None for name in self.__owned_fields__)

    def __repr__(self):
        fields = ", ".join(
            f"{k}={getattr(self, k)!r}" for k in self.__owned_fields__
        )
        return f"{self.__class__.__name__}({fields})"

    @classmethod
    def coerce(cls, key, value):
        """类型强制转换，支持 None 和 dict 赋值"""
        if value is None:
            return None
        if isinstance(value, dict):
            return cls(**value)
        if isinstance(value, cls):
            return value
        return value

    def to_dict(self) -> dict:
        """值对象序列化为字典"""
        return {name: getattr(self, name) for name in self.__owned_fields__}

    @property
    def is_empty(self) -> bool:
        """是否所有字段都为 None"""
        return not bool(self)


# ==================== 导出 ====================

__all__ = [
    "OwnedField",
    "owned_field",
    "OwnedMeta",
    "OwnedType",
]
