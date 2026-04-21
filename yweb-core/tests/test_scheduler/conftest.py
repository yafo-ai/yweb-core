"""调度器测试配置

提供调度器测试所需的公共 fixtures，包括内存数据库支持。
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import StaticPool

from yweb.orm import CoreModel, BaseModel
from yweb.orm.hybrid_query import HybridQueryProperty
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
    
    # 设置 CoreModel.query —— 对齐生产路径：用 HybridQueryProperty 包装
    # Phase 5B.1 之后生效：scheduler.py 的 async _execute_job 已把
    # history_manager.record_* 全部改成 run_in_threadpool 包装，
    # 不会再触发"_HybridTerminal 当成 Model 实例"的 bug
    #
    # 注意：读取原 query 必须走 __dict__，不能用 getattr()。
    # 因为上游可能已把 CoreModel.query 设为 query_property/HybridQueryProperty，
    # getattr 会触发 descriptor.__get__(None, CoreModel)，对抽象基类发起
    # session.query(CoreModel) → ArgumentError。
    _SENTINEL = object()
    previous_query = CoreModel.__dict__.get("query", _SENTINEL)
    CoreModel.query = HybridQueryProperty(session_scope.query_property())
    
    try:
        yield session_scope()
    finally:
        # 关键：无论测试结果如何，都要恢复 CoreModel.query，避免跨模块测试污染
        # （详见 23 号清单 Phase 5B.1 验收项）
        if previous_query is _SENTINEL:
            try:
                del CoreModel.query
            except AttributeError:
                pass
        else:
            CoreModel.query = previous_query
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
