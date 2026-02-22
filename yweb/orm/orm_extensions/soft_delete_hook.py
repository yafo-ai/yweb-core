"""软删除事件钩子"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import inspect
from sqlalchemy.event import listens_for
from sqlalchemy.orm import Session

from .soft_delete_ignored_table import IgnoredTable
from .soft_delete_rewriter import SoftDeleteRewriter


# 全局重写器实例
global_rewriter: Optional[SoftDeleteRewriter] = None


def activate_soft_delete_hook(
    deleted_field_name: str = "deleted_at",
    disable_soft_delete_option_name: str = "include_deleted",
    ignored_tables: List[IgnoredTable] = None
):
    """激活软删除钩子
    
    此函数会注册SQLAlchemy事件监听器，自动：
    - 重写SELECT查询，过滤已软删除的记录
    - 重写DELETE操作，转为软删除
    - 设置created_at, updated_at, deleted_at时间戳
    
    Args:
        deleted_field_name: 软删除字段名，默认"deleted_at"
        disable_soft_delete_option_name: 禁用软删除的option名称，默认"include_deleted"
        ignored_tables: 忽略软删除的表列表
    
    使用示例:
        from yweb.orm.orm_extensions import activate_soft_delete_hook, IgnoredTable
        
        # 在应用启动时激活
        activate_soft_delete_hook(
            deleted_field_name="deleted_at",
            ignored_tables=[
                IgnoredTable(name="audit_log")
            ]
        )
        
        # 之后所有查询自动过滤已删除记录
        users = User.query.all()  # 只返回未删除的用户
        
        # 如需包含已删除记录
        all_users = User.query.execution_options(include_deleted=True).all()
    """
    global global_rewriter
    
    if ignored_tables is None:
        ignored_tables = []
    
    global_rewriter = SoftDeleteRewriter(
        deleted_field_name=deleted_field_name,
        disable_soft_delete_option_name=disable_soft_delete_option_name,
        ignored_tables=ignored_tables,
    )
    
    # 注册do_orm_execute事件监听器
    # 用于拦截和重写SELECT/DELETE/UPDATE查询
    @listens_for(Session, "do_orm_execute")
    def _do_orm_execute(orm_execute_state):
        if (
            orm_execute_state.is_select or orm_execute_state.is_delete and
            not orm_execute_state.is_column_load and
            not orm_execute_state.is_relationship_load
        ):
            # 重写语句
            adapted = global_rewriter.rewrite_statement(orm_execute_state.statement)
            orm_execute_state.statement = adapted
    
    # 注册before_flush事件监听器
    # 用于自动设置时间戳和处理删除
    @listens_for(Session, "before_flush")
    def _before_flush(session, flush_context, instances):
        # 处理新增对象
        for instance in session.new:
            # 检查是否有cascade.delete_orphan配置
            _check_delete_orphan(instance)
            # 设置创建时间
            if hasattr(instance, 'created_at'):
                instance.created_at = datetime.now()
        
        # 处理更新对象
        for instance in session.dirty:
            _check_delete_orphan(instance)
            # 设置更新时间 - 只有在有实际列属性变更时才设置
            # 注意：对象可能仅因 ManyToMany back_populates 被标记为 dirty，
            # 此时没有列属性变更，不应设置 updated_at，否则会导致
            # event_before_flush 误判并 expunge 该对象，破坏关联表操作
            if hasattr(instance, 'updated_at'):
                if session.is_modified(instance, include_collections=False):
                    instance.updated_at = datetime.now()
        
        # 处理删除对象（转为软删除）
        deleted_instances = list(session.deleted)
        for instance in deleted_instances:
            _check_delete_orphan(instance)
            # 设置删除时间（软删除）
            if hasattr(instance, deleted_field_name):
                # 先尝试执行级联软删除
                from .cascade_soft_delete import get_cascade_manager
                manager = get_cascade_manager()
                if manager:
                    # 使用级联管理器处理（会自动设置 deleted_at 并处理子对象）
                    deleted_objects = manager.soft_delete_with_cascade(
                        instance, session, datetime.now()
                    )
                    # 将所有软删除的对象加入 session
                    for obj in deleted_objects:
                        if obj not in session:
                            session.add(obj)
                else:
                    # 没有级联管理器，只设置当前对象的 deleted_at
                    setattr(instance, deleted_field_name, datetime.now())
                
                # 将对象从deleted集合移到dirty集合
                session.expunge(instance)
                session.add(instance)


def _check_delete_orphan(instance):
    """检查关系配置是否包含delete_orphan
    
    delete_orphan在软删除模式下可能导致问题，因此禁止使用
    """
    try:
        for rel_name, rel in inspect(instance.__class__).relationships.items():
            if rel.cascade.delete_orphan:
                raise Exception(
                    f"{instance.__class__.__name__} 类的relationship配置有误，"
                    f"软删除模式下暂不支持delete_orphan"
                )
    except Exception:
        pass  # 忽略检查失败


def deactivate_soft_delete_hook():
    """停用软删除钩子
    
    注意：SQLAlchemy的事件监听器一旦注册就无法移除，
    此函数只是将全局重写器设为None，使其不再生效
    """
    global global_rewriter
    global_rewriter = None


def is_soft_delete_active() -> bool:
    """检查软删除钩子是否激活"""
    return global_rewriter is not None

