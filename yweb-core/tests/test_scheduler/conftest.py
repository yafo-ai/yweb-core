"""调度器测试配置

提供调度器测试所需的公共 fixtures，包括内存数据库支持。
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import StaticPool

from yweb.orm import CoreModel, BaseModel
from yweb.scheduler import create_scheduler_models


# 创建测试用的 scheduler 模型（全局，避免重复创建）
_scheduler_models = None


def get_scheduler_models():
    """获取或创建 scheduler 模型"""
    global _scheduler_models
    if _scheduler_models is None:
        _scheduler_models = create_scheduler_models(table_prefix="test_")
    return _scheduler_models


@pytest.fixture(scope="function")
def scheduler_engine():
    """创建调度器测试用内存数据库引擎
    
    使用 StaticPool 确保所有操作使用同一个连接，
    避免 SQLite 内存数据库不同连接看不到数据的问题。
    """
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def scheduler_models():
    """获取 scheduler 模型容器"""
    return get_scheduler_models()


@pytest.fixture(autouse=False)
def scheduler_db_session(scheduler_engine, scheduler_models):
    """初始化调度器数据库会话
    
    创建所有调度器相关的表，并设置 CoreModel.query。
    """
    # 创建所有表（包括 scheduler 模型的表）
    BaseModel.metadata.create_all(bind=scheduler_engine)
    
    # 创建会话工厂
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=scheduler_engine)
    
    # 使用固定 scopefunc 避免线程问题
    # scopefunc 返回固定值，确保所有调用共享同一 session
    session_scope = scoped_session(SessionLocal, scopefunc=lambda: 0)
    
    # 设置 CoreModel.query
    CoreModel.query = session_scope.query_property()
    
    yield session_scope()
    
    # 清理 - 忽略可能的线程错误
    try:
        session_scope.remove()
    except Exception:
        pass


@pytest.fixture
def scheduler_with_db(scheduler_db_session, scheduler_models):
    """创建带数据库支持的调度器"""
    from yweb.scheduler import Scheduler
    from yweb.config import SchedulerSettings
    
    settings = SchedulerSettings(
        enabled=True,
        store="memory",  # 仍使用内存存储任务，但历史记录可以写入数据库
        enable_history=True,
    )
    
    scheduler = Scheduler(settings=settings)
    
    # 注入模型到 history manager
    if scheduler._history_manager is None:
        scheduler._get_history_manager()
    if scheduler._history_manager:
        scheduler._history_manager._job_model = scheduler_models.SchedulerJob
        scheduler._history_manager._history_model = scheduler_models.SchedulerJobHistory
        scheduler._history_manager._stats_model = scheduler_models.SchedulerJobStats
    
    yield scheduler


@pytest.fixture
def scheduler_orm_store(scheduler_db_session, scheduler_models):
    """创建使用 ORM 存储的调度器"""
    from yweb.scheduler import Scheduler
    from yweb.config import SchedulerSettings
    
    settings = SchedulerSettings(
        enabled=True,
        store="orm",
        enable_history=True,
    )
    
    scheduler = Scheduler(settings=settings)
    
    # 注入模型
    if scheduler._history_manager is None:
        scheduler._get_history_manager()
    if scheduler._history_manager:
        scheduler._history_manager._job_model = scheduler_models.SchedulerJob
        scheduler._history_manager._history_model = scheduler_models.SchedulerJobHistory
        scheduler._history_manager._stats_model = scheduler_models.SchedulerJobStats
    
    yield scheduler
