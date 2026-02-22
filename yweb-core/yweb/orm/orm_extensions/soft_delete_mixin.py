"""软删除Mixin类生成器"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Optional, Type, List, TYPE_CHECKING

from sqlalchemy import Column, DateTime
from sqlalchemy.sql.type_api import TypeEngine

from .soft_delete_hook import activate_soft_delete_hook
from .soft_delete_ignored_table import IgnoredTable


def generate_soft_delete_mixin_class(
    deleted_field_name: str = "deleted_at",
    ignored_tables: List[IgnoredTable] = None,
    class_name: str = "_SoftDeleteMixin",
    deleted_field_type: TypeEngine = DateTime(timezone=True),
    disable_soft_delete_filtering_option_name: str = "include_deleted",
    generate_delete_method: bool = True,
    delete_method_name: str = "soft_delete",
    delete_method_default_value: Callable[[], Any] = lambda: datetime.now(),
    generate_undelete_method: bool = True,
    undelete_method_name: str = "undelete",
) -> Type:
    """生成软删除Mixin类
    
    此函数动态生成一个Mixin类，添加软删除功能到你的模型中。
    
    功能：
    - 添加软删除字段（如deleted_at）
    - 自动激活软删除钩子
    - 提供delete()和undelete()方法
    - 查询时自动过滤已删除记录
    
    Args:
        deleted_field_name: 软删除字段名，默认"deleted_at"
        ignored_tables: 忽略软删除的表列表
        class_name: 生成的类名
        deleted_field_type: 软删除字段类型
        disable_soft_delete_filtering_option_name: 禁用软删除过滤的option名称
        generate_delete_method: 是否生成delete方法
        delete_method_name: delete方法名
        delete_method_default_value: 软删除时的默认值
        generate_undelete_method: 是否生成undelete方法
        undelete_method_name: undelete方法名
    
    Returns:
        动态生成的Mixin类
    
    使用示例:
        from yweb.orm.orm_extensions import generate_soft_delete_mixin_class, IgnoredTable
        
        # 生成软删除Mixin
        SoftDeleteMixin = generate_soft_delete_mixin_class(
            ignored_tables=[
                IgnoredTable(name='audit_log')
            ]
        )
        
        # 在模型中使用
        class User(Base, SoftDeleteMixin):
            __tablename__ = 'user'
            id = Column(Integer, primary_key=True)
            name = Column(String(50))
        
        # 软删除
        user = session.query(User).first()
        user.delete()
        session.commit()
        
        
        # 查询（自动过滤已删除）
        users = session.query(User).all()  # 不包含已删除
        
        # 包含已删除记录
        all_users = session.query(User).execution_options(include_deleted=True).all()
    """
    if ignored_tables is None:
        ignored_tables = []

    # 类属性
    class_attributes = {}
    
    # 软删除字段（如果指定了类型）
    # 如果 deleted_field_type 为 None，则不添加字段（使用外部定义的字段）
    if deleted_field_type is not None:
        class_attributes[deleted_field_name] = Column(deleted_field_name, deleted_field_type)

    # 添加delete方法
    if generate_delete_method:
        def delete_method(_self, v: Optional[Any] = None):
            """软删除当前对象"""
            setattr(_self, deleted_field_name, v or delete_method_default_value())
        
        class_attributes[delete_method_name] = delete_method

    # 添加undelete方法
    if generate_undelete_method:
        def undelete_method(_self):
            """恢复软删除的对象"""
            setattr(_self, deleted_field_name, None)
        
        class_attributes[undelete_method_name] = undelete_method

    # 激活软删除钩子
    activate_soft_delete_hook(
        deleted_field_name,
        disable_soft_delete_filtering_option_name,
        ignored_tables
    )

    # 动态生成类
    generated_class = type(class_name, tuple(), class_attributes)

    return generated_class


# 生成简单的软删除Mixin
# 注意：deleted_field_type=None，因为 CoreModel 已经定义了 deleted_at 字段
# 只提供 soft_delete/undelete 方法和激活钩子
_SimpleSoftDeleteMixinBase = generate_soft_delete_mixin_class(
    delete_method_default_value=lambda: datetime.now(),  # 使用 datetime 对象
    deleted_field_type=None,  # 不生成字段，使用 CoreModel 的 deleted_at
    ignored_tables=[
        IgnoredTable(name='transaction')  # 版本历史记录表不软删除
    ],
)


class SimpleSoftDeleteMixin(_SimpleSoftDeleteMixinBase):
    """简单的软删除Mixin
    
    一个预配置的软删除Mixin，使用 generate_soft_delete_mixin_class 自动生成。
    
    功能：
    - 自动激活软删除钩子（拦截 session.delete()）
    - 查询时自动过滤已删除记录
    
    提供方法：
    - soft_delete(v=None): 软删除对象，设置 deleted_at 为当前时间或指定值
    - undelete(): 恢复软删除的对象，将 deleted_at 设置为 None
    - is_deleted: 属性，检查对象是否已被软删除
    
    使用示例:
        from yweb.orm.orm_extensions import SimpleSoftDeleteMixin
        
        # 在模型中使用
        class User(Base, SimpleSoftDeleteMixin):
            __tablename__ = 'user'
            id = Column(Integer, primary_key=True)
            name = Column(String(50))

        
        # 查询（自动过滤已删除）
        users = session.query(User).all()
        
        # 包含已删除记录
        all_users = session.query(User).execution_options(include_deleted=True).all()
        
        # 软删除
        user.soft_delete()
        session.commit()
        
        # 恢复
        user.undelete()
        session.commit()
    """
    # 类型标注（用于 IDE 提示）
    deleted_at: Optional[datetime]
    
    # 动态生成方法的类型存根（实际实现由 _SimpleSoftDeleteMixinBase 提供）
    if TYPE_CHECKING:
        def soft_delete(self, v: Optional[datetime] = None) -> None:
            """软删除当前对象
            
            Args:
                v: 可选，指定删除时间。默认使用当前时间。
            """
            ...
        
        def undelete(self) -> None:
            """恢复软删除的对象，将 deleted_at 设置为 None"""
            ...
    
    @property
    def is_deleted(self) -> bool:
        """检查对象是否已被软删除"""
        return self.deleted_at is not None

