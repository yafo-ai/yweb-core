"""Django 风格的关系字段定义

提供类似 Django ORM 的字段定义方式，简化 SQLAlchemy 的关系配置。

使用示例:
    from yweb.orm import fields
    from yweb.orm.fields import HasMany, HasOne
    
    class UserProfile(BaseModel):
        # 一对一
        user = fields.OneToOne(User, on_delete=fields.DELETE)
    
    class Employee(BaseModel):
        # 多对一（外键）
        department = fields.ManyToOne(Department, on_delete=fields.SET_NULL)
    
    class User(BaseModel):
        # 多对多
        roles = fields.ManyToMany(Role, on_delete=fields.UNLINK)

类型标记（用于 IDE 提示）:
    from __future__ import annotations
    
    class OrderModel(BaseModel):
        # 一对多类型标记，提供 IDE 完整提示
        items: HasMany[OrderItemModel]
    
    class OrderItemModel(BaseModel):
        # 自动探测 OrderModel.items，使用 "items" 作为 backref 名称
        order = fields.ManyToOne(OrderModel, on_delete=fields.DELETE)

on_delete 常量:
    - fields.DELETE: 级联删除子记录
    - fields.SET_NULL: 设置外键为空
    - fields.PROTECT: 保护（有子记录时禁止删除）
    - fields.UNLINK: 解除关联（多对多）
    - fields.DO_NOTHING: 不做任何处理
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Optional, Type, Union, TYPE_CHECKING, Generic, TypeVar, get_type_hints, get_origin, get_args

from sqlalchemy import Table, Column, Integer, BigInteger, String, ForeignKey
from sqlalchemy.orm import relationship, backref as sa_backref, Mapped, mapped_column

if TYPE_CHECKING:
    from .core_model import CoreModel

# 泛型类型变量
T = TypeVar('T', bound='CoreModel')


# ==================== on_delete 常量 ====================

class OnDelete(str, Enum):
    """软删除级联行为枚举
    
    定义父记录软删除时，子记录的处理方式
    """
    
    # 级联删除：父表删除时，子记录也被软删除
    # 适用场景：订单-订单项，删除订单时订单项也删除
    DELETE = "delete"
    
    # 设置为空：父表删除时，子记录的外键设为 NULL
    # 适用场景：部门-员工，删除部门时员工的 dept_id 设为空
    SET_NULL = "set_null"
    
    # 保护：有子记录时禁止删除父表
    # 适用场景：需要先手动处理子记录
    PROTECT = "protect"
    
    # 解除关联：仅解除多对多关联关系
    # 适用场景：用户-角色，删除用户时解除与角色的关联
    UNLINK = "unlink"
    
    # 不处理：不对子记录做任何操作
    DO_NOTHING = "do_nothing"


# 便捷常量导出（可直接使用 fields.DELETE）
DELETE = OnDelete.DELETE
SET_NULL = OnDelete.SET_NULL
PROTECT = OnDelete.PROTECT
UNLINK = OnDelete.UNLINK
DO_NOTHING = OnDelete.DO_NOTHING

# 软删除级联配置的 info key
SOFT_DELETE_CASCADE_KEY = "soft_delete_cascade"


# ==================== 字段配置类 ====================

class _OneToOneConfig:
    """一对一字段配置"""
    
    def __init__(
        self,
        target_model: Type["CoreModel"],
        on_delete: OnDelete = DO_NOTHING,
        backref: Union[bool, str] = True,
        nullable: bool = False,
        fk_column_name: Optional[str] = None,
        **kwargs
    ):
        self.target_model = target_model
        self.on_delete = on_delete
        self.backref = backref
        self.nullable = nullable
        self.fk_column_name = fk_column_name
        self.kwargs = kwargs


class _ManyToOneConfig:
    """多对一（外键）字段配置"""
    
    def __init__(
        self,
        target_model: Type["CoreModel"],
        on_delete: OnDelete = DO_NOTHING,
        backref: Union[bool, str] = True,
        nullable: bool = True,
        fk_column_name: Optional[str] = None,
        **kwargs
    ):
        self.target_model = target_model
        self.on_delete = on_delete
        self.backref = backref
        self.nullable = nullable
        self.fk_column_name = fk_column_name
        self.kwargs = kwargs


class _ManyToManyConfig:
    """多对多字段配置"""
    
    def __init__(
        self,
        target_model: Type["CoreModel"],
        on_delete: OnDelete = UNLINK,
        backref: Union[bool, str] = True,
        table_name: Optional[str] = None,
        related_name: Optional[str] = None,
        **kwargs
    ):
        self.target_model = target_model
        self.on_delete = on_delete
        self.backref = backref
        self.table_name = table_name
        self.related_name = related_name
        self.kwargs = kwargs


# ==================== 类型标记类（用于 IDE 提示）====================

class HasMany(Generic[T]):
    """一对多类型标记
    
    纯类型注解，不创建实际的 relationship。
    当子类使用 ManyToOne 时，框架会自动探测并使用此属性名作为 backref。
    
    关系示意图：
    
        ┌─────────────┐  1     N  ┌─────────────┐
        │   Order     │◄──────────│  OrderItem  │
        │─────────────│           │─────────────│
        │ id (PK)     │           │ order_id(FK)│
        │ items ──────┼───────────┤ order ──────│
        │ (HasMany)   │           │ (ManyToOne) │
        └─────────────┘           └─────────────┘
    
    使用示例:
        from __future__ import annotations
        from yweb.orm.fields import HasMany
        
        class OrderModel(BaseModel):
            name: Mapped[str] = mapped_column(String(50))
            
            # 一对多类型标记，提供 IDE 完整提示
            items: HasMany[OrderItemModel]
        
        class OrderItemModel(BaseModel):
            name: Mapped[str] = mapped_column(String(50))
            
            # 自动探测 OrderModel.items，使用 "items" 作为 backref 名称
            order = fields.ManyToOne(OrderModel, on_delete=fields.DELETE)
        
        # 使用时 IDE 有完整提示
        order = OrderModel(name="订单1")
        order.items.append(OrderItemModel(name="商品A"))  # ✓ IDE 提示 items
        order.items[0].order  # ✓ IDE 提示 order
    
    注意:
        - 需要配合 `from __future__ import annotations` 使用
        - 跨文件时使用 TYPE_CHECKING 导入目标类
    """
    
    def __class_getitem__(cls, item: Type[T]):
        """支持 HasMany[Model] 泛型语法"""
        return super().__class_getitem__(item)


class HasOne(Generic[T]):
    """一对一类型标记
    
    纯类型注解，不创建实际的 relationship。
    当子类使用 OneToOne 时，框架会自动探测并使用此属性名作为 backref。
    
    关系示意图：
    
        ┌─────────────┐  1     1  ┌─────────────┐
        │    User     │◄──────────│ UserProfile │
        │─────────────│           │─────────────│
        │ id (PK)     │           │ user_id(FK) │
        │ profile ────┼───────────┤ user ───────│
        │ (HasOne)    │           │ (OneToOne)  │
        └─────────────┘           └─────────────┘
    
    使用示例:
        from __future__ import annotations
        from yweb.orm.fields import HasOne
        
        class User(BaseModel):
            username: Mapped[str] = mapped_column(String(50))
            
            # 一对一类型标记
            profile: HasOne[UserProfile]
        
        class UserProfile(BaseModel):
            bio: Mapped[str] = mapped_column(String(500))
            
            # 自动探测 User.profile，使用 "profile" 作为 backref 名称
            user = fields.OneToOne(User, on_delete=fields.DELETE)
    """
    
    def __class_getitem__(cls, item: Type[T]):
        """支持 HasOne[Model] 泛型语法"""
        return super().__class_getitem__(item)


# ==================== 字段定义函数 ====================

def OneToOne(
    target_model: Type["CoreModel"],
    on_delete: OnDelete = DO_NOTHING,
    backref: Union[bool, str] = True,
    nullable: bool = False,
    fk_column_name: Optional[str] = None,
    **kwargs
) -> _OneToOneConfig:
    """一对一关系字段
    
    关系示意图：
    
        ┌─────────────┐  1     1  ┌─────────────┐
        │    User     │◄──────────│ UserProfile │
        │─────────────│           │─────────────│
        │ id (PK)     │           │ user_id(FK) │ ← 自动创建
        │ profile ────┼───────────┤ user ───────│ ← relationship
        │ (单个对象)  │           │ bio         │
        └─────────────┘           └─────────────┘
    
    Args:
        target_model: 关联的模型类（父表）
        on_delete: 父表软删除时的行为
            - DELETE: 级联删除子记录
            - SET_NULL: 设置外键为空
            - PROTECT: 有子记录时禁止删除
            - DO_NOTHING: 不处理（默认）
        backref: 在父表上创建的反向引用
            - True: 自动生成单数名称（如 UserProfile → user_profile）
            - str: 使用指定名称（如 "profile"）
            - False: 不创建反向引用
        nullable: 外键是否可为空，默认 False（一对一通常必填）
        fk_column_name: 外键列名（None 自动生成，如 user_id）
        **kwargs: 传递给 relationship 的其他参数
    
    使用示例:
        class User(BaseModel):
            username: Mapped[str] = mapped_column(String(50))
            # profile 由 backref 自动创建（单个对象）
        
        class UserProfile(BaseModel):
            bio: Mapped[str] = mapped_column(String(500))
            
            # 一对一关系
            user = fields.OneToOne(User, on_delete=fields.DELETE)
            # 自动创建：user_id 列 + user relationship + User.user_profile backref
        
        # 使用
        profile.user = user          # 设置关联
        user.user_profile            # 反向访问（单个对象）
    """
    return _OneToOneConfig(
        target_model=target_model,
        on_delete=on_delete,
        backref=backref,
        nullable=nullable,
        fk_column_name=fk_column_name,
        **kwargs
    )


def ManyToOne(
    target_model: Type["CoreModel"],
    on_delete: OnDelete = DO_NOTHING,
    backref: Union[bool, str] = True,
    nullable: bool = True,
    fk_column_name: Optional[str] = None,
    **kwargs
) -> _ManyToOneConfig:
    """多对一（外键）关系字段
    
    关系示意图：
    
        ┌─────────────┐  1     N  ┌─────────────┐
        │ Department  │◄──────────│  Employee   │
        │─────────────│           │─────────────│
        │ id (PK)     │           │ dept_id(FK) │ ← 自动创建
        │ employees ──┼───────────┤ department ─│ ← relationship
        │   (列表)    │           │ name        │
        └─────────────┘           └─────────────┘
    
    Args:
        target_model: 关联的模型类（父表）
        on_delete: 父表软删除时的行为
            - DELETE: 级联删除子记录
            - SET_NULL: 设置外键为空（推荐）
            - PROTECT: 有子记录时禁止删除
            - DO_NOTHING: 不处理（默认）
        backref: 在父表上创建的反向引用
            - True: 自动生成复数名称（如 Employee → employees）
            - str: 使用指定名称（如 "staff"）
            - False: 不创建反向引用
        nullable: 外键是否可为空，默认 True
        fk_column_name: 外键列名（None 自动生成，如 department_id）
        **kwargs: 传递给 relationship 的其他参数
    
    使用示例:
        class Department(BaseModel):
            name: Mapped[str] = mapped_column(String(100))
            # employees 由 backref 自动创建（列表）
        
        class Employee(BaseModel):
            name: Mapped[str] = mapped_column(String(50))
            
            # 多对一关系
            department = fields.ManyToOne(Department, on_delete=fields.SET_NULL)
            # 自动创建：department_id 列 + department relationship + Department.employees backref
        
        # 使用
        emp.department = dept        # 设置关联
        dept.employees               # 反向访问（列表）
    """
    return _ManyToOneConfig(
        target_model=target_model,
        on_delete=on_delete,
        backref=backref,
        nullable=nullable,
        fk_column_name=fk_column_name,
        **kwargs
    )


def ManyToMany(
    target_model: Type["CoreModel"],
    on_delete: OnDelete = UNLINK,
    backref: Union[bool, str] = True,
    table_name: Optional[str] = None,
    related_name: Optional[str] = None,
    **kwargs
) -> _ManyToManyConfig:
    """多对多关系字段（自动创建中间表）
    
    关系示意图：
    
        ┌─────────────┐          ┌─────────────┐          ┌─────────────┐
        │    User     │    N     │ user_roles  │    M     │    Role     │
        │─────────────│◄─────────│ (自动创建)  │─────────►│─────────────│
        │ id (PK)     │          │ user_id(FK) │          │ id (PK)     │
        │ username    │          │ role_id(FK) │          │ name        │
        │             │          └─────────────┘          │             │
        │ roles ──────┼──────────────────────────────────►│ users ──────│
        │   (列表)    │                                   │  (backref)  │
        └─────────────┘                                   └─────────────┘
    
    Args:
        target_model: 关联的模型类
        on_delete: 软删除时的行为
            - UNLINK: 解除关联（默认，推荐）
            - DO_NOTHING: 不处理
        backref: 在目标模型上创建的反向引用
            - True: 自动生成复数名称（如 User → users）
            - str: 使用指定名称（如 "members"）
            - False: 不创建反向引用
        table_name: 中间表名（None 自动生成，如 user_roles）
        related_name: Django 风格反向引用（等同于 backref）
        **kwargs: 传递给 relationship 的其他参数
    
    使用示例:
        class Role(BaseModel):
            name: Mapped[str] = mapped_column(String(50))
            # users 由 backref 自动创建（列表）
        
        class User(BaseModel):
            username: Mapped[str] = mapped_column(String(50))
            
            # 多对多关系
            roles = fields.ManyToMany(Role, on_delete=fields.UNLINK)
            # 自动创建：user_roles 中间表 + roles relationship + Role.users backref
        
        # 使用
        user.roles.append(role)      # 添加关联
        user.roles.remove(role)      # 移除关联
        role.users                   # 反向访问（列表）
    
    注意:
        - 中间表只需在一侧定义，另一侧通过 backref 访问
        - 如果需要中间表有额外字段，请手动创建中间表模型
    """
    # related_name 是 Django 风格的参数，等同于 backref
    if related_name is not None and backref is True:
        backref = related_name
    
    return _ManyToManyConfig(
        target_model=target_model,
        on_delete=on_delete,
        backref=backref,
        table_name=table_name,
        related_name=related_name,
        **kwargs
    )


# ==================== 字段处理函数 ====================

# 导入工具函数
from .utils import to_snake_case, pluralize, singularize


def _get_on_delete_enum(on_delete) -> OnDelete:
    """统一转换为 OnDelete 枚举"""
    if isinstance(on_delete, OnDelete):
        return on_delete
    if isinstance(on_delete, str):
        mapping = {
            "delete": OnDelete.DELETE,
            "set_null": OnDelete.SET_NULL,
            "protect": OnDelete.PROTECT,
            "unlink": OnDelete.UNLINK,
            "do_nothing": OnDelete.DO_NOTHING,
        }
        return mapping.get(on_delete.lower(), OnDelete.DO_NOTHING)
    return OnDelete.DO_NOTHING


def _get_fk_column_type(target_model):
    """根据目标模型的主键类型，返回匹配的外键列类型
    
    Args:
        target_model: 目标模型类
        
    Returns:
        SQLAlchemy 列类型（Integer, String, BigInteger 等）
    """
    from yweb.orm.primary_key_config import IdType, PrimaryKeyConfig
    
    # 获取目标模型的主键策略
    id_type = getattr(target_model, '__pk_strategy__', None)
    if id_type is None:
        id_type = PrimaryKeyConfig.get_strategy()
    
    # 根据主键类型返回匹配的列类型
    if id_type == IdType.AUTO_INCREMENT:
        return Integer
    elif id_type == IdType.UUID:
        return String(36)
    elif id_type == IdType.SHORT_UUID:
        length = PrimaryKeyConfig.get_short_uuid_length()
        return String(length + 2)
    elif id_type == IdType.SNOWFLAKE:
        return BigInteger
    elif id_type == IdType.CUSTOM:
        return String(64)
    else:
        # 默认使用 Integer
        return Integer


def _find_has_many_backref_name(target_model: Type, source_model: Type) -> Optional[str]:
    """在目标模型（父类）中查找指向源模型（子类）的 HasMany 类型注解
    
    Args:
        target_model: 父模型类（如 OrderModel）
        source_model: 子模型类（如 OrderItemModel）
    
    Returns:
        找到的属性名（如 "items"），未找到返回 None
    """
    source_name = source_model.__name__
    
    # 方法1：尝试使用 get_type_hints（支持完整类型解析）
    try:
        # 构建本地命名空间，包含源模型
        localns = {source_name: source_model}
        hints = get_type_hints(target_model, localns=localns)
        
        for attr_name, hint in hints.items():
            if attr_name.startswith('_'):
                continue
            
            origin = get_origin(hint)
            if origin is HasMany:
                args = get_args(hint)
                if args:
                    target_type = args[0]
                    if target_type is source_model:
                        return attr_name
                    elif isinstance(target_type, str) and target_type == source_name:
                        return attr_name
                    elif hasattr(target_type, '__name__') and target_type.__name__ == source_name:
                        return attr_name
    except Exception:
        pass
    
    # 方法2：直接检查 __annotations__（处理前向引用）
    try:
        annotations = getattr(target_model, '__annotations__', {})
        for attr_name, annotation in annotations.items():
            if attr_name.startswith('_'):
                continue
            
            # 检查字符串形式的注解，如 "HasMany[OrderItemModel]"
            if isinstance(annotation, str):
                if 'HasMany' in annotation and source_name in annotation:
                    return attr_name
            else:
                # 检查类型对象
                origin = get_origin(annotation)
                if origin is HasMany:
                    args = get_args(annotation)
                    if args:
                        target_type = args[0]
                        if target_type is source_model:
                            return attr_name
                        elif isinstance(target_type, str) and target_type == source_name:
                            return attr_name
                        elif hasattr(target_type, '__name__') and target_type.__name__ == source_name:
                            return attr_name
    except Exception:
        pass
    
    return None


def _find_has_one_backref_name(target_model: Type, source_model: Type) -> Optional[str]:
    """在目标模型（父类）中查找指向源模型（子类）的 HasOne 类型注解
    
    Args:
        target_model: 父模型类（如 User）
        source_model: 子模型类（如 UserProfile）
    
    Returns:
        找到的属性名（如 "profile"），未找到返回 None
    """
    source_name = source_model.__name__
    
    # 方法1：尝试使用 get_type_hints（支持完整类型解析）
    try:
        localns = {source_name: source_model}
        hints = get_type_hints(target_model, localns=localns)
        
        for attr_name, hint in hints.items():
            if attr_name.startswith('_'):
                continue
            
            origin = get_origin(hint)
            if origin is HasOne:
                args = get_args(hint)
                if args:
                    target_type = args[0]
                    if target_type is source_model:
                        return attr_name
                    elif isinstance(target_type, str) and target_type == source_name:
                        return attr_name
                    elif hasattr(target_type, '__name__') and target_type.__name__ == source_name:
                        return attr_name
    except Exception:
        pass
    
    # 方法2：直接检查 __annotations__（处理前向引用）
    try:
        annotations = getattr(target_model, '__annotations__', {})
        for attr_name, annotation in annotations.items():
            if attr_name.startswith('_'):
                continue
            
            if isinstance(annotation, str):
                if 'HasOne' in annotation and source_name in annotation:
                    return attr_name
            else:
                origin = get_origin(annotation)
                if origin is HasOne:
                    args = get_args(annotation)
                    if args:
                        target_type = args[0]
                        if target_type is source_model:
                            return attr_name
                        elif isinstance(target_type, str) and target_type == source_name:
                            return attr_name
                        elif hasattr(target_type, '__name__') and target_type.__name__ == source_name:
                            return attr_name
    except Exception:
        pass
    
    return None


def process_relationship_fields(cls):
    """处理模型类中的关系字段定义
    
    在 CoreModel.__init_subclass__ 中调用，自动处理：
    - OneToOne: 创建外键列 + relationship（uselist=False）
    - ManyToOne: 创建外键列 + relationship
    - ManyToMany: 创建中间表 + relationship
    
    扫描范围：类自身 + Mixin / abstract 基类（跳过已有 __tablename__ 的具体模型基类）
    """
    from yweb.orm.id_model import Base
    
    processed_names = set()
    
    for klass in cls.__mro__:
        if klass is object:
            continue
        # 跳过具体模型基类（它们创建时已处理过自己的字段，子类通过 SQLAlchemy 继承）
        if klass is not cls and '__tablename__' in klass.__dict__:
            continue
        
        for attr_name, config in list(vars(klass).items()):
            if attr_name in processed_names:
                continue
            if isinstance(config, _OneToOneConfig):
                _process_one_to_one(cls, attr_name, config)
                processed_names.add(attr_name)
            elif isinstance(config, _ManyToOneConfig):
                _process_many_to_one(cls, attr_name, config)
                processed_names.add(attr_name)
            elif isinstance(config, _ManyToManyConfig):
                _process_many_to_many(cls, attr_name, config, Base)
                processed_names.add(attr_name)


def _process_one_to_one(cls, attr_name: str, config: _OneToOneConfig):
    """处理一对一字段"""
    target_model = config.target_model
    target_tablename = target_model.__tablename__
    
    # 1. 生成外键列名（基于目标表名）
    if config.fk_column_name:
        fk_column_name = config.fk_column_name
    else:
        # 表名去复数化 + _id，如 users → user_id, fk_test_orders → fk_test_order_id
        fk_column_name = f"{singularize(target_tablename)}_id"
    
    # 2. 创建外键列（动态匹配目标模型主键类型）
    fk_column_type = _get_fk_column_type(target_model)
    fk_column = mapped_column(
        fk_column_type,
        ForeignKey(f"{target_tablename}.id"),
        nullable=config.nullable,
        unique=True,  # 一对一需要唯一约束
    )
    setattr(cls, fk_column_name, fk_column)
    
    # 3. 准备 relationship 参数
    rel_kwargs = dict(config.kwargs)
    rel_kwargs['foreign_keys'] = f"[{cls.__name__}.{fk_column_name}]"
    rel_kwargs['uselist'] = False  # 一对一
    
    # 4. 处理 backref（智能探测 HasOne 类型标记）
    on_delete = _get_on_delete_enum(config.on_delete)
    
    if config.backref is True:
        # 尝试在父类中查找 HasOne[当前类] 的类型注解
        backref_name = _find_has_one_backref_name(target_model, cls)
        
        if backref_name is None:
            # 未找到 HasOne 声明，使用默认命名规则
            backref_name = to_snake_case(cls.__name__, remove_model_suffix=True)
        
        backref_info = {SOFT_DELETE_CASCADE_KEY: on_delete} if on_delete != OnDelete.DO_NOTHING else {}
        rel_kwargs['backref'] = sa_backref(backref_name, info=backref_info, uselist=False)
    elif config.backref and config.backref is not False:
        backref_info = {SOFT_DELETE_CASCADE_KEY: on_delete} if on_delete != OnDelete.DO_NOTHING else {}
        rel_kwargs['backref'] = sa_backref(config.backref, info=backref_info, uselist=False)
    
    # 5. 创建 relationship
    rel = relationship(target_model, **rel_kwargs)
    setattr(cls, attr_name, rel)


def _process_many_to_one(cls, attr_name: str, config: _ManyToOneConfig):
    """处理多对一字段"""
    target_model = config.target_model
    target_tablename = target_model.__tablename__
    
    # 1. 生成外键列名（基于目标表名）
    if config.fk_column_name:
        fk_column_name = config.fk_column_name
    else:
        # 表名去复数化 + _id，如 departments → department_id, demo_orders → demo_order_id
        fk_column_name = f"{singularize(target_tablename)}_id"
    
    # 2. 创建外键列（动态匹配目标模型主键类型）
    fk_column_type = _get_fk_column_type(target_model)
    fk_column = mapped_column(
        fk_column_type,
        ForeignKey(f"{target_tablename}.id"),
        nullable=config.nullable,
    )
    setattr(cls, fk_column_name, fk_column)
    
    # 3. 准备 relationship 参数
    rel_kwargs = dict(config.kwargs)
    rel_kwargs['foreign_keys'] = f"[{cls.__name__}.{fk_column_name}]"
    
    # 4. 处理 backref（智能探测 HasMany 类型标记）
    on_delete = _get_on_delete_enum(config.on_delete)
    
    if config.backref is True:
        # 尝试在父类中查找 HasMany[当前类] 的类型注解
        backref_name = _find_has_many_backref_name(target_model, cls)
        
        if backref_name is None:
            # 未找到 HasMany 声明，使用默认命名规则
            backref_name = pluralize(to_snake_case(cls.__name__, remove_model_suffix=True))
        
        backref_info = {SOFT_DELETE_CASCADE_KEY: on_delete} if on_delete != OnDelete.DO_NOTHING else {}
        rel_kwargs['backref'] = sa_backref(backref_name, info=backref_info)
    elif config.backref and config.backref is not False:
        backref_info = {SOFT_DELETE_CASCADE_KEY: on_delete} if on_delete != OnDelete.DO_NOTHING else {}
        rel_kwargs['backref'] = sa_backref(config.backref, info=backref_info)
    
    # 5. 创建 relationship
    rel = relationship(target_model, **rel_kwargs)
    setattr(cls, attr_name, rel)


def _process_many_to_many(cls, attr_name: str, config: _ManyToManyConfig, Base):
    """处理多对多字段"""
    target_model = config.target_model
    
    # 1. 生成中间表名
    if config.table_name:
        table_name = config.table_name
    else:
        table_name = f"{cls.__tablename__}_{attr_name}"
    
    # 2. 创建中间表（如果不存在）
    if table_name not in Base.metadata.tables:
        target_tablename = target_model.__tablename__
        
        # 动态匹配两端模型的主键类型
        source_fk_type = _get_fk_column_type(cls)
        target_fk_type = _get_fk_column_type(target_model)
        
        association_table = Table(
            table_name,
            Base.metadata,
            Column(
                f"{cls.__tablename__}_id",
                source_fk_type,
                ForeignKey(f"{cls.__tablename__}.id", ondelete="CASCADE"),
                primary_key=True
            ),
            Column(
                f"{target_tablename}_id",
                target_fk_type,
                ForeignKey(f"{target_tablename}.id", ondelete="CASCADE"),
                primary_key=True
            ),
        )
    else:
        association_table = Base.metadata.tables[table_name]
    
    # 3. 准备 relationship 参数
    rel_kwargs = dict(config.kwargs)
    rel_kwargs['secondary'] = association_table
    rel_kwargs.setdefault('lazy', 'selectin')
    
    # 4. 处理 backref
    on_delete = _get_on_delete_enum(config.on_delete)
    
    if config.backref is True:
        # 自动生成复数名称
        backref_name = pluralize(to_snake_case(cls.__name__, remove_model_suffix=True))
        backref_info = {SOFT_DELETE_CASCADE_KEY: on_delete} if on_delete != OnDelete.DO_NOTHING else {}
        rel_kwargs['backref'] = sa_backref(backref_name, info=backref_info)
    elif config.backref and config.backref is not False:
        backref_info = {SOFT_DELETE_CASCADE_KEY: on_delete} if on_delete != OnDelete.DO_NOTHING else {}
        rel_kwargs['backref'] = sa_backref(config.backref, info=backref_info)
    
    # 5. 创建 relationship
    rel = relationship(target_model, **rel_kwargs)
    setattr(cls, attr_name, rel)


# ==================== 导出 ====================

__all__ = [
    # 字段类型
    "OneToOne",
    "ManyToOne", 
    "ManyToMany",
    # 类型标记（用于 IDE 提示）
    "HasMany",
    "HasOne",
    # on_delete 常量
    "OnDelete",
    "DELETE",
    "SET_NULL",
    "PROTECT",
    "UNLINK",
    "DO_NOTHING",
    # 处理函数（内部使用）
    "process_relationship_fields",
    # 配置类（内部使用）
    "_OneToOneConfig",
    "_ManyToOneConfig",
    "_ManyToManyConfig",
    # 常量
    "SOFT_DELETE_CASCADE_KEY",
]
