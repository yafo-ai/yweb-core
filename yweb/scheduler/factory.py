"""定时任务模块 - 模型工厂

提供 create_scheduler_models() 函数，用于快速创建定时任务所有模型。
简化使用方式，同时保留自定义扩展能力。

使用方式：
=========

级别1：零配置快速启用（推荐）
-------------------
    from yweb.scheduler import create_scheduler_models
    
    # 一行创建所有模型
    scheduler = create_scheduler_models(table_prefix="sys_")
    
    # 使用模型
    SchedulerJob = scheduler.SchedulerJob
    SchedulerJobHistory = scheduler.SchedulerJobHistory
    SchedulerJobStats = scheduler.SchedulerJobStats

级别2：轻量自定义（通过 Mixin）
---------------------------
    from yweb.scheduler import create_scheduler_models
    from sqlalchemy import String
    from sqlalchemy.orm import Mapped, mapped_column
    
    class JobTenantMixin:
        '''多租户支持'''
        tenant_id: Mapped[str] = mapped_column(String(50), index=True, comment="租户ID")
    
    scheduler = create_scheduler_models(
        table_prefix="sys_",
        job_mixin=JobTenantMixin,
    )

级别3：完全自定义（继承抽象类）
------------------------
    from yweb.scheduler.models import AbstractSchedulerJob
    
    class SchedulerJob(AbstractSchedulerJob):
        __tablename__ = "my_scheduler_job"
        # 完全自定义...

级别4：一站式设置（含 API 路由）
------------------------
    from yweb.scheduler import setup_scheduler
    
    scheduler = setup_scheduler(
        app=app,
        table_prefix="sys_",
        api_prefix="/api/v1/scheduler",
        dependencies=[Depends(get_current_user)],
    )
"""

from dataclasses import dataclass, field
from typing import Type, Optional, Callable, Any
import uuid

from sqlalchemy import UniqueConstraint

from .models import (
    AbstractSchedulerJob,
    AbstractSchedulerJobHistory,
    AbstractSchedulerJobStats,
)


def _generate_tablename(base_name: str, prefix: str = "") -> str:
    """生成表名
    
    Args:
        base_name: 基础表名（如 'scheduler_job'）
        prefix: 表名前缀（如 'sys_'）
    
    Returns:
        完整表名（如 'sys_scheduler_job'）
    """
    return f"{prefix}{base_name}" if prefix else base_name


def _create_model_class(
    name: str,
    base_class: Type,
    tablename: str,
    extra_attrs: dict = None,
    mixin: Type = None,
    table_args: tuple = None,
) -> Type:
    """动态创建模型类
    
    Args:
        name: 类名
        base_class: 基类（抽象模型）
        tablename: 表名
        extra_attrs: 额外的类属性
        mixin: 可选的 Mixin 类
        table_args: SQLAlchemy 表参数（如约束）
    
    Returns:
        新创建的模型类
    """
    # 确定基类列表
    if mixin:
        bases = (mixin, base_class)
    else:
        bases = (base_class,)
    
    # 生成唯一的类名，使用 UUID 避免 SQLAlchemy registry 冲突
    # 例如：SchedulerJob -> SchedulerJob_a1b2c3d4
    unique_suffix = uuid.uuid4().hex[:8]
    unique_name = f"{name}_{unique_suffix}"
    
    # 类属性（显式设置 __abstract__ = False，覆盖基类的 True）
    attrs = {
        "__tablename__": tablename,
        "__abstract__": False,
        "__table_args__": {"extend_existing": True},
    }
    
    # 合并表参数（如唯一约束）
    if table_args:
        existing_args = attrs.get("__table_args__", {})
        if isinstance(existing_args, dict):
            attrs["__table_args__"] = table_args + (existing_args,)
        else:
            attrs["__table_args__"] = table_args
    
    # 合并额外属性
    if extra_attrs:
        attrs.update(extra_attrs)
    
    # 动态创建类（使用唯一名称避免 registry 冲突）
    return type(unique_name, bases, attrs)


@dataclass
class SchedulerModels:
    """Scheduler 模型容器
    
    包含所有定时任务相关的模型类，支持点号访问。
    
    属性:
        SchedulerJob: 任务定义模型
        SchedulerJobHistory: 执行历史模型
        SchedulerJobStats: 执行统计模型
    
    使用示例:
        scheduler = create_scheduler_models(table_prefix="sys_")
        
        # 访问模型
        job = scheduler.SchedulerJob(code="TEST", name="测试任务", ...)
        
        # 获取历史管理器
        history_manager = scheduler.get_history_manager()
    """
    # 模型
    SchedulerJob: Type
    SchedulerJobHistory: Type
    SchedulerJobStats: Type
    
    # 私有：单例实例
    _history_manager: Any = field(default=None, repr=False)
    _orm_store: Any = field(default=None, repr=False)
    
    def as_dict(self) -> dict:
        """返回模型字典，方便传递给其他函数"""
        return {
            "job_model": self.SchedulerJob,
            "history_model": self.SchedulerJobHistory,
            "stats_model": self.SchedulerJobStats,
        }
    
    def get_history_manager(self, enabled: bool = True, retention_days: int = 30):
        """获取历史管理器单例
        
        Args:
            enabled: 是否启用历史记录
            retention_days: 历史记录保留天数
        
        Returns:
            HistoryManager 实例（单例模式）
        
        使用示例:
            scheduler = create_scheduler_models(table_prefix="sys_")
            history_manager = scheduler.get_history_manager()
        """
        if self._history_manager is None:
            from .history import HistoryManager
            
            # 创建绑定了具体模型的 HistoryManager
            manager = HistoryManager(
                enabled=enabled,
                retention_days=retention_days,
                job_model=self.SchedulerJob,
                history_model=self.SchedulerJobHistory,
                stats_model=self.SchedulerJobStats,
            )
            object.__setattr__(self, '_history_manager', manager)
        
        return self._history_manager
    
    def get_orm_store(self, scheduler=None):
        """获取 ORM 存储单例
        
        Args:
            scheduler: Scheduler 实例（可选）
        
        Returns:
            ORMJobStore 实例（单例模式）
        """
        if self._orm_store is None:
            from .stores import ORMJobStore
            
            store = ORMJobStore(
                scheduler=scheduler,
                job_model=self.SchedulerJob,
            )
            object.__setattr__(self, '_orm_store', store)
        
        return self._orm_store
    
    def mount_routes(
        self,
        app,
        scheduler,
        prefix: str = "/api/scheduler",
        tags: list = None,
        dependencies: list = None,
    ):
        """挂载调度器管理路由到 FastAPI 应用
        
        与 auth.mount_routes() 风格一致的路由挂载方法。
        
        Args:
            app: FastAPI 应用实例
            scheduler: Scheduler 实例
            prefix: API 路由前缀（默认 "/api/scheduler"）
            tags: OpenAPI 标签
            dependencies: 路由依赖（如权限检查）
        
        使用示例:
            scheduler_models = create_scheduler_models(table_prefix="sys_")
            scheduler_models.mount_routes(
                app,
                scheduler=scheduler,
                prefix="/api/v1/scheduler",
                dependencies=[Depends(get_current_user)],
            )
        """
        from .api import create_scheduler_router
        
        router = create_scheduler_router(
            scheduler=scheduler,
            history_model=self.SchedulerJobHistory,
            prefix="",
            tags=tags or ["定时任务"],
            dependencies=dependencies,
        )
        app.include_router(router, prefix=prefix)


def create_scheduler_models(
    table_prefix: str = "",
    # 自定义表名（可选）
    job_tablename: str = None,
    history_tablename: str = None,
    stats_tablename: str = None,
    # Mixin 扩展（可选）
    job_mixin: Type = None,
    history_mixin: Type = None,
    stats_mixin: Type = None,
    # 回调自定义（可选）
    job_customizer: Callable[[Type], None] = None,
    history_customizer: Callable[[Type], None] = None,
    stats_customizer: Callable[[Type], None] = None,
) -> SchedulerModels:
    """创建定时任务所有模型
    
    一站式创建任务定义、执行历史、统计等模型类。
    支持通过 Mixin 或回调函数自定义扩展。
    
    Args:
        table_prefix: 表名前缀（如 "sys_"），应用于所有表
        
        job_tablename: 任务表名（默认根据 prefix 生成）
        history_tablename: 历史表名
        stats_tablename: 统计表名
        
        job_mixin: 任务模型的 Mixin 类（如添加租户字段）
        history_mixin: 历史模型的 Mixin 类
        stats_mixin: 统计模型的 Mixin 类
        
        job_customizer: 任务模型的回调自定义函数
        history_customizer: 历史模型的回调自定义函数
        stats_customizer: 统计模型的回调自定义函数
    
    Returns:
        SchedulerModels 对象，包含所有模型类
    
    使用示例:
        # 级别1：零配置
        scheduler = create_scheduler_models(table_prefix="sys_")
        
        # 级别2：添加自定义字段
        from sqlalchemy import String
        from sqlalchemy.orm import Mapped, mapped_column
        
        class JobTenantMixin:
            tenant_id: Mapped[str] = mapped_column(String(50), index=True)
        
        scheduler = create_scheduler_models(
            table_prefix="sys_",
            job_mixin=JobTenantMixin,
        )
        
        # 使用模型
        SchedulerJob = scheduler.SchedulerJob
        job = SchedulerJob(code="TEST", name="测试", ...)
    """
    # 1. 生成表名
    job_table = job_tablename or _generate_tablename("scheduler_job", table_prefix)
    history_table = history_tablename or _generate_tablename("scheduler_job_history", table_prefix)
    stats_table = stats_tablename or _generate_tablename("scheduler_job_stats", table_prefix)
    
    # 2. 创建 SchedulerJob 模型
    SchedulerJob = _create_model_class(
        name="SchedulerJob",
        base_class=AbstractSchedulerJob,
        tablename=job_table,
        mixin=job_mixin,
    )
    
    # 3. 创建 SchedulerJobHistory 模型
    SchedulerJobHistory = _create_model_class(
        name="SchedulerJobHistory",
        base_class=AbstractSchedulerJobHistory,
        tablename=history_table,
        mixin=history_mixin,
    )
    
    # 4. 创建 SchedulerJobStats 模型（带唯一约束）
    # 动态生成约束名称，避免多次创建时冲突
    constraint_name = f"uix_{stats_table.replace('.', '_')}"
    stats_table_args = (
        UniqueConstraint('job_code', 'stat_date', 'stat_hour', name=constraint_name),
    )
    
    SchedulerJobStats = _create_model_class(
        name="SchedulerJobStats",
        base_class=AbstractSchedulerJobStats,
        tablename=stats_table,
        mixin=stats_mixin,
        table_args=stats_table_args,
    )
    
    # 5. 应用自定义回调
    if job_customizer:
        job_customizer(SchedulerJob)
    if history_customizer:
        history_customizer(SchedulerJobHistory)
    if stats_customizer:
        stats_customizer(SchedulerJobStats)
    
    # 6. 返回模型容器
    return SchedulerModels(
        SchedulerJob=SchedulerJob,
        SchedulerJobHistory=SchedulerJobHistory,
        SchedulerJobStats=SchedulerJobStats,
    )


def setup_scheduler(
    app,  # FastAPI 实例
    table_prefix: str = "",
    api_prefix: str = "/scheduler",
    tags: list = None,
    dependencies: list = None,
    # Mixin 扩展（可选）
    job_mixin: Type = None,
    history_mixin: Type = None,
    stats_mixin: Type = None,
    # 回调自定义（可选）
    job_customizer: Callable[[Type], None] = None,
    history_customizer: Callable[[Type], None] = None,
    stats_customizer: Callable[[Type], None] = None,
    # 自定义表名（可选）
    job_tablename: str = None,
    history_tablename: str = None,
    stats_tablename: str = None,
    # Scheduler 配置
    scheduler_instance = None,
) -> SchedulerModels:
    """一站式设置定时任务模块
    
    最简洁的使用方式：一个函数完成模型创建、路由创建、路由挂载。
    
    Args:
        app: FastAPI 应用实例
        table_prefix: 表名前缀（如 "sys_"）
        api_prefix: API 路由前缀（如 "/api/v1/scheduler"）
        tags: OpenAPI 标签
        dependencies: 路由依赖（如权限检查）
        
        job_mixin: 任务模型的 Mixin 类
        history_mixin: 历史模型的 Mixin 类
        stats_mixin: 统计模型的 Mixin 类
        
        job_customizer: 任务模型的回调自定义函数
        history_customizer: 历史模型的回调自定义函数
        stats_customizer: 统计模型的回调自定义函数
        
        job_tablename: 自定义任务表名
        history_tablename: 自定义历史表名
        stats_tablename: 自定义统计表名
        
        scheduler_instance: 可选的 Scheduler 实例，不传则不注册任务管理 API
    
    Returns:
        SchedulerModels 对象，包含所有模型类
    
    使用示例:
        from fastapi import FastAPI, Depends
        from yweb.scheduler import setup_scheduler, Scheduler
        
        app = FastAPI()
        scheduler = Scheduler()
        
        # 一行完成所有设置
        scheduler_models = setup_scheduler(
            app=app,
            table_prefix="sys_",
            api_prefix="/api/v1/scheduler",
            dependencies=[Depends(get_current_user)],
            scheduler_instance=scheduler,
        )
        
        # 使用模型
        SchedulerJob = scheduler_models.SchedulerJob
        
        # 带自定义字段的使用
        from sqlalchemy import String
        from sqlalchemy.orm import Mapped, mapped_column
        
        class JobTenantMixin:
            tenant_id: Mapped[str] = mapped_column(String(50), index=True)
        
        scheduler_models = setup_scheduler(
            app=app,
            table_prefix="sys_",
            api_prefix="/api/v1/scheduler",
            job_mixin=JobTenantMixin,
            dependencies=[Depends(get_current_user)],
        )
    """
    from .api import create_scheduler_router
    
    # 1. 创建所有模型
    scheduler_models = create_scheduler_models(
        table_prefix=table_prefix,
        job_tablename=job_tablename,
        history_tablename=history_tablename,
        stats_tablename=stats_tablename,
        job_mixin=job_mixin,
        history_mixin=history_mixin,
        stats_mixin=stats_mixin,
        job_customizer=job_customizer,
        history_customizer=history_customizer,
        stats_customizer=stats_customizer,
    )
    
    # 2. 创建路由
    router = create_scheduler_router(
        scheduler=scheduler_instance,
        history_model=scheduler_models.SchedulerJobHistory,
        prefix="",  # 前缀在 include_router 时设置
        tags=tags or ["定时任务"],
        dependencies=dependencies,
    )
    
    # 3. 挂载路由到应用
    app.include_router(router, prefix=api_prefix)
    
    return scheduler_models


__all__ = [
    "create_scheduler_models",
    "setup_scheduler",
    "SchedulerModels",
]
