"""级联软删除模块

提供软删除场景下的级联操作功能。

级联类型（使用 fields.OnDelete）:
- DELETE: 级联软删除子记录（如：订单→订单项）
- SET_NULL: 设置外键为空（如：部门→员工，员工可调岗）
- DO_NOTHING: 不处理（如：用户→角色，角色是共享的）
- PROTECT: 有子记录时禁止删除（保护性删除）
- UNLINK: 解除多对多关联

推荐使用 fields.* 定义关系:
    from yweb.orm import BaseModel, fields
    
    class OrderItem(BaseModel):
        # 多对一：订单项 → 订单
        order = fields.ManyToOne(Order, on_delete=fields.DELETE)
    
    class Employee(BaseModel):
        # 多对一：员工 → 部门
        department = fields.ManyToOne(Department, on_delete=fields.SET_NULL)
    
    class User(BaseModel):
        # 多对多：用户 → 角色
        roles = fields.ManyToMany(Role, on_delete=fields.UNLINK)

高级用法（直接使用 relationship）:
    from sqlalchemy.orm import relationship
    from yweb.orm.fields import OnDelete, SOFT_DELETE_CASCADE_KEY
    
    class Order(BaseModel):
        items = relationship(
            "OrderItem", 
            back_populates="order",
            info={SOFT_DELETE_CASCADE_KEY: OnDelete.DELETE}
        )
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional, Set, Type, Union, TYPE_CHECKING

from sqlalchemy import inspect, update
from sqlalchemy.orm import Session, RelationshipProperty
from sqlalchemy.orm.attributes import get_history

if TYPE_CHECKING:
    from sqlalchemy.orm import DeclarativeBase


# 从 fields 模块导入统一的级联类型
from yweb.orm.fields import (
    OnDelete,
    DELETE, SET_NULL, PROTECT, UNLINK, DO_NOTHING,
    SOFT_DELETE_CASCADE_KEY,
)


class CascadeSoftDeleteManager:
    """级联软删除管理器
    
    管理软删除时的级联操作
    """
    
    def __init__(self, deleted_field_name: str = "deleted_at"):
        self.deleted_field_name = deleted_field_name
        self._processed_objects: Set[int] = set()
    
    def soft_delete_with_cascade(
        self,
        instance: Any,
        session: Session,
        deleted_value: Any = None,
        processed: Optional[Set[int]] = None
    ) -> List[Any]:
        """执行带级联的软删除
        
        Args:
            instance: 要删除的实例
            session: 数据库会话
            deleted_value: 删除时间值，默认使用当前时间
            processed: 已处理的对象集合（避免循环引用）
            
        Returns:
            被软删除的所有对象列表
        """
        if processed is None:
            processed = set()
        
        # 避免重复处理
        instance_id = id(instance)
        if instance_id in processed:
            return []
        processed.add(instance_id)
        
        deleted_objects = []
        
        # 设置删除时间
        if deleted_value is None:
            deleted_value = datetime.now()
        
        if hasattr(instance, self.deleted_field_name):
            setattr(instance, self.deleted_field_name, deleted_value)
            deleted_objects.append(instance)
        
        # 处理关联关系
        mapper = inspect(instance.__class__)
        for rel_name, rel in mapper.relationships.items():
            cascade_type = self._get_cascade_type(rel)
            
            if cascade_type == OnDelete.DELETE:
                # 级联软删除
                deleted_objects.extend(
                    self._cascade_delete(instance, rel_name, session, deleted_value, processed)
                )
            elif cascade_type == OnDelete.SET_NULL:
                # 设置外键为空
                self._set_foreign_key_null(instance, rel, session)
            elif cascade_type == OnDelete.PROTECT:
                # 检查是否有子记录
                self._check_restrict(instance, rel_name)
            elif cascade_type == OnDelete.UNLINK:
                # 解除多对多关联
                self._unlink_association(instance, rel, session)
            # OnDelete.DO_NOTHING: 不做任何处理
        
        return deleted_objects
    
    def _get_cascade_type(self, rel: RelationshipProperty) -> OnDelete:
        """获取关系的级联类型"""
        # 从 relationship 的 info 属性获取配置
        info = getattr(rel, 'info', {}) or {}
        cascade_type = info.get(SOFT_DELETE_CASCADE_KEY)
        
        if cascade_type is not None:
            # 已经是 OnDelete 枚举
            if isinstance(cascade_type, OnDelete):
                return cascade_type
            # 字符串形式，需要映射
            if isinstance(cascade_type, str):
                mapping = {
                    "delete": OnDelete.DELETE,
                    "set_null": OnDelete.SET_NULL,
                    "protect": OnDelete.PROTECT,
                    "unlink": OnDelete.UNLINK,
                    "do_nothing": OnDelete.DO_NOTHING,
                }
                return mapping.get(cascade_type.lower(), OnDelete.DO_NOTHING)
            return cascade_type
        
        # 默认策略：
        # - 多对多关系：UNLINK
        # - 一对多关系：DELETE（如果配置了 cascade='all'）
        # - 其他：DO_NOTHING
        if rel.secondary is not None:
            return OnDelete.UNLINK
        
        if rel.cascade and rel.cascade.delete:
            return OnDelete.DELETE
        
        return OnDelete.DO_NOTHING
    
    def _cascade_delete(
        self,
        instance: Any,
        rel_name: str,
        session: Session,
        deleted_value: Any,
        processed: Set[int]
    ) -> List[Any]:
        """级联软删除子记录"""
        deleted_objects = []
        
        related_objects = getattr(instance, rel_name, None)
        if related_objects is None:
            return deleted_objects
        
        # 处理一对多关系
        if isinstance(related_objects, list):
            for obj in related_objects:
                deleted_objects.extend(
                    self.soft_delete_with_cascade(obj, session, deleted_value, processed)
                )
        else:
            # 处理一对一关系
            deleted_objects.extend(
                self.soft_delete_with_cascade(related_objects, session, deleted_value, processed)
            )
        
        return deleted_objects
    
    def _set_foreign_key_null(self, instance: Any, rel: RelationshipProperty, session: Session):
        """设置子记录的外键为空
        
        使用批量 UPDATE 设置外键为 NULL，然后让受影响的对象在 session 中过期，
        确保下次访问时从数据库重新加载最新状态。
        """
        # 先获取受影响的子对象（在执行 UPDATE 前获取，确保能访问到）
        related_objects = getattr(instance, rel.key, None)
        
        # 获取子模型类
        child_class = rel.mapper.class_
        
        # 获取外键列
        for local_col, remote_col in rel.local_remote_pairs:
            if remote_col.table == child_class.__table__:
                # 批量更新外键为空
                fk_column = remote_col.name
                parent_id = getattr(instance, local_col.name)
                
                stmt = update(child_class).where(
                    getattr(child_class, fk_column) == parent_id
                ).values(**{fk_column: None})
                
                session.execute(stmt)
        
        # 让受影响的子对象在 session 中过期，强制下次访问时从数据库重新加载
        if related_objects:
            if isinstance(related_objects, list):
                for obj in related_objects:
                    if obj in session:
                        session.expire(obj)
            else:
                if related_objects in session:
                    session.expire(related_objects)
    
    def _check_restrict(self, instance: Any, rel_name: str):
        """检查是否有子记录（PROTECT模式）"""
        related_objects = getattr(instance, rel_name, None)
        
        has_children = False
        if isinstance(related_objects, list):
            has_children = len(related_objects) > 0
        else:
            has_children = related_objects is not None
        
        if has_children:
            raise ValueError(
                f"无法删除 {instance.__class__.__name__}，"
                f"存在关联的 {rel_name} 记录。请先删除或转移子记录。"
            )
    
    def _unlink_association(self, instance: Any, rel: RelationshipProperty, session: Session):
        """解除多对多关联
        
        通过直接操作中间表删除关联记录，避免 SQLAlchemy collection 的 session 状态问题。
        
        Args:
            instance: 要删除的实例
            rel: relationship 属性
            session: 数据库会话
        """
        # 只处理多对多关系（有中间表）
        if rel.secondary is None:
            return
        
        # 获取中间表
        secondary_table = rel.secondary
        
        # 获取本端的外键列名（关联到当前实例的列）
        # local_columns 是本端模型的主键列，需要找到中间表中对应的外键列
        local_pk_col = list(rel.local_columns)[0]
        
        # 在中间表中找到引用本端主键的外键列
        local_fk_col = None
        for fk in secondary_table.foreign_keys:
            if fk.column.table == instance.__class__.__table__:
                local_fk_col = fk.parent
                break
        
        if local_fk_col is None:
            return
        
        # 直接删除中间表记录
        from sqlalchemy import delete
        stmt = delete(secondary_table).where(
            local_fk_col == getattr(instance, 'id')
        )
        session.execute(stmt)


# 全局管理器实例
_cascade_manager: Optional[CascadeSoftDeleteManager] = None


def configure_cascade_soft_delete(deleted_field_name: str = "deleted_at"):
    """配置级联软删除功能
    
    在应用启动时调用此函数来启用级联软删除支持。
    级联逻辑已集成到 soft_delete_hook 的 before_flush 事件中，
    此函数只需初始化 CascadeSoftDeleteManager 即可。
    
    Args:
        deleted_field_name: 软删除字段名
    
    使用示例:
        from yweb.orm import configure_cascade_soft_delete
        
        # 在应用启动时配置
        configure_cascade_soft_delete(deleted_field_name="deleted_at")
    """
    global _cascade_manager
    _cascade_manager = CascadeSoftDeleteManager(deleted_field_name)


def get_cascade_manager() -> Optional[CascadeSoftDeleteManager]:
    """获取级联软删除管理器"""
    return _cascade_manager


# 导出
__all__ = [
    # 级联软删除管理器
    "CascadeSoftDeleteManager",
    "configure_cascade_soft_delete",
    "get_cascade_manager",
    "SoftDeleteMixin",
    # 从 fields 模块导入的类型（方便向后兼容）
    "OnDelete",
    "DELETE", "SET_NULL", "PROTECT", "UNLINK", "DO_NOTHING",
    "SOFT_DELETE_CASCADE_KEY",
]



