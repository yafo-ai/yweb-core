"""
数据库会话管理模块

提供数据库引擎创建、会话管理等功能。

公开 API:
- db_manager: 数据库管理器单例
- init_database(): 初始化数据库连接
- get_engine(): 获取数据库引擎
- get_db(): FastAPI 依赖注入用的上下文管理器
- db_session_scope(): 非 HTTP 场景的上下文管理器
- with_db_session(): 装饰器方式管理 session
- on_request_end(): 请求结束清理

内部 API（不建议外部使用）:
- db_manager.get_session(): 获取 scoped session（低级）
- db_manager._set_request_id(): 设置请求ID
- db_manager._get_request_id(): 获取请求ID
"""

from typing import Optional, Callable, Any, TypeVar, Generator
from uuid import uuid4
import logging
import asyncio
from contextlib import contextmanager
from functools import wraps

from sqlalchemy.orm import sessionmaker, scoped_session, Session
from sqlalchemy import create_engine, event
from contextvars import ContextVar

from yweb.log import get_logger

_logger = get_logger("yweb.orm.session")

# 类型变量
T = TypeVar('T')

# 公开导出列表
__all__ = [
    # 管理器单例
    'db_manager',
    # 公开函数
    'init_database',
    'get_engine',
    'get_db',
    'db_session_scope',
    'with_db_session',
    'on_request_end',
]


class DatabaseManager:
    """数据库管理器（单例）
    
    封装数据库连接状态和会话管理，提供统一的访问接口。
    所有内部状态都通过私有属性保护，外部只能通过方法访问。
    
    使用示例:
        from yweb.orm import db_manager
        
        # 初始化
        db_manager.init(database_url="sqlite:///./test.db")
        
        # 获取引擎（只读）
        engine = db_manager.engine
        
        # 获取 session（内部使用）
        session = db_manager.get_session()
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # 私有状态
        self._engine = None
        self._session_scope = None
        self._session_maker = None
        self._request_id_var: ContextVar[str] = ContextVar('request_id', default='')
        # 标记 request_id 是否已锁定（防止覆盖导致 session 泄漏）
        # 锁定时机：_set_request_id() 调用后 或 get_session() 创建 session 后
        self._request_id_explicit: ContextVar[bool] = ContextVar('request_id_explicit', default=False)
        self._initialized = True
    
    # ==================== 属性访问 ====================
    
    @property
    def engine(self):
        """获取数据库引擎（只读）
        
        Raises:
            RuntimeError: 数据库未初始化时
        """
        if self._engine is None:
            raise RuntimeError("数据库未初始化，请先调用 init_database()")
        return self._engine
    
    @property
    def session_scope(self):
        """获取 scoped session（只读，内部使用）
        
        ⚠️ 警告：这是内部属性，请优先使用：
        - FastAPI 路由：使用 get_db() 依赖
        - 脚本/测试：使用 db_session_scope() 上下文管理器
        
        Raises:
            RuntimeError: 数据库未初始化时
        """
        if self._session_scope is None:
            raise RuntimeError("数据库未初始化，请先调用 init_database()")
        return self._session_scope
    
    @property
    def is_initialized(self) -> bool:
        """检查数据库是否已初始化"""
        return self._engine is not None and self._session_scope is not None
    
    # ==================== 核心方法 ====================
    
    def init(
        self,
        database_url: str = None,
        echo: bool = False,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_timeout: int = 30,
        pool_recycle: int = 3600,
        pool_pre_ping: bool = True,
        sql_log_enabled: bool = False,
        logger: logging.Logger = None,
        scopefunc: Callable = None,
        config: Any = None,
        logging_config: Any = None,
        auto_setup_query: bool = True
    ):
        """初始化数据库连接
        
        Args:
            database_url: 数据库连接URL（如果提供 config 则忽略）
            echo: 是否输出SQL语句（如果提供 config 则忽略）
            pool_size: 连接池大小（如果提供 config 则忽略）
            max_overflow: 最大溢出连接数（如果提供 config 则忽略）
            pool_timeout: 连接超时时间（如果提供 config 则忽略）
            pool_recycle: 连接回收时间（如果提供 config 则忽略）
            pool_pre_ping: 连接前是否ping（如果提供 config 则忽略）
            sql_log_enabled: 是否启用SQL日志（如果提供 logging_config 则忽略）
            logger: 日志记录器
            scopefunc: session作用域函数，默认使用 _get_request_id
            config: 数据库配置对象（DatabaseSettings），提供后自动提取配置
            logging_config: 日志配置对象（LoggingSettings），提供后自动提取 sql_log_enabled
            auto_setup_query: 是否自动设置 CoreModel.query 属性，默认 True
        
        Returns:
            tuple: (engine, session_scope)
            
        使用示例:
            from yweb.orm import init_database, get_db, db_session_scope
            
            # 方式1：传统参数方式
            engine, session = init_database(
                database_url="sqlite:///./test.db",
                echo=False
            )
            
            # 方式2：配置对象方式（推荐）
            engine, session = init_database(
                config=settings.database,
                logging_config=settings.logging,
                logger=logger
            )
            
            # 在FastAPI中使用
            app = FastAPI()
            
            @app.on_event("startup")
            def startup():
                init_database(config=settings.database)
            
            # 在路由中使用（推荐）
            @app.get("/users")
            def get_users(db: Session = Depends(get_db)):
                return db.query(User).all()
            
            # 在脚本中使用
            with db_session_scope() as session:
                users = session.query(User).all()
        """
        # 如果提供了 config，从中提取数据库配置
        if config is not None:
            database_url = getattr(config, "url", database_url)
            echo = getattr(config, "echo", echo)
            pool_size = getattr(config, "pool_size", pool_size)
            max_overflow = getattr(config, "max_overflow", max_overflow)
            pool_timeout = getattr(config, "pool_timeout", pool_timeout)
            pool_recycle = getattr(config, "pool_recycle", pool_recycle)
            pool_pre_ping = getattr(config, "pool_pre_ping", pool_pre_ping)
        
        # 如果提供了 logging_config，从中提取 SQL 日志配置
        if logging_config is not None:
            sql_log_enabled = getattr(logging_config, "sql_log_enabled", sql_log_enabled)
        
        # 验证必要参数
        if not database_url:
            raise ValueError("database_url 是必需的，请通过参数或 config 提供")
        
        if logger is None:
            logger = get_logger()
        
        # 日志输出
        logger.info(f"数据库配置URL: {database_url}")
        
        # 根据SQL日志配置决定是否启用echo
        engine_echo = "debug" if sql_log_enabled else echo
        
        # 检查SQLite数据库
        if database_url.startswith("sqlite:///"):
            import os
            from sqlalchemy.pool import QueuePool, StaticPool
            
            db_path = database_url[len("sqlite:///"):]
            is_memory_db = db_path == ":memory:" or db_path == ""
            
            if not is_memory_db:
                abs_db_path = os.path.abspath(db_path)
                logger.info(f"SQLite文件数据库路径: {abs_db_path}")
            else:
                logger.info("SQLite内存数据库")
            
            # 创建SQLite引擎
            try:
                if is_memory_db:
                    # 内存数据库：使用 StaticPool（单连接）
                    self._engine = create_engine(
                        database_url,
                        echo=engine_echo,
                        connect_args={
                            "check_same_thread": False,
                        },
                        poolclass=StaticPool,
                    )
                    logger.info("SQLite内存数据库引擎创建成功（StaticPool）")
                else:
                    # 文件数据库：使用 QueuePool 支持多连接
                    self._engine = create_engine(
                        database_url,
                        echo=engine_echo,
                        connect_args={
                            "check_same_thread": False,
                            "timeout": pool_timeout
                        },
                        poolclass=QueuePool,
                        pool_size=pool_size,
                        max_overflow=max_overflow,
                        pool_timeout=pool_timeout,
                        pool_pre_ping=pool_pre_ping,
                        pool_recycle=pool_recycle
                    )
                    logger.info(f"SQLite文件数据库引擎创建成功（QueuePool, pool_size={pool_size}, max_overflow={max_overflow}）")
            except Exception as e:
                logger.error(f"创建SQLite数据库引擎失败: {str(e)}")
                raise
        else:
            # 创建其他数据库引擎
            try:
                self._engine = create_engine(
                    database_url,
                    echo=engine_echo,
                    pool_pre_ping=pool_pre_ping,
                    pool_size=pool_size,
                    max_overflow=max_overflow,
                    pool_timeout=pool_timeout,
                    pool_recycle=pool_recycle
                )
                logger.info("数据库引擎创建成功")
            except Exception as e:
                logger.error(f"创建数据库引擎失败: {str(e)}")
                raise
        
        # SQL执行时间记录
        if sql_log_enabled:
            import time
            sql_logger = logging.getLogger("sqlalchemy.engine")
            
            @event.listens_for(self._engine, "before_cursor_execute")
            def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
                conn.info.setdefault('query_start_time', []).append(time.time())
            
            @event.listens_for(self._engine, "after_cursor_execute")
            def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
                total_time = time.time() - conn.info['query_start_time'].pop()
                sql_logger.debug(f"[执行耗时: {total_time*1000:.2f}ms]")
            
            logger.info("SQL执行时间记录已启用")
        
        # 创建SessionMaker
        self._session_maker = sessionmaker(
            autocommit=False,
            autoflush=True,
            bind=self._engine,
            # expire_on_commit=False 是不安全的，在长链接 有可能造成脏数据，导致更新出问题，尤其是多对多关系
        )
        
        # 创建scoped_session
        if scopefunc is None:
            scopefunc = self._get_request_id
        
        self._session_scope = scoped_session(self._session_maker, scopefunc=scopefunc)
        
        # 自动设置 ORM query 属性（延迟导入避免循环依赖）
        if auto_setup_query:
            from .core_model import CoreModel
            CoreModel.query = self._session_scope.query_property()
            logger.info("CoreModel.query 属性已自动设置")
        
        logger.info("数据库session创建成功")
        
        return self._engine, self._session_scope
    
    def get_session(self) -> Session:
        """获取 scoped session（低级 API）
        
        ⚠️ 警告：这是低级 API，请优先使用以下安全方式：
        - FastAPI 路由：使用 get_db() 依赖
        - 脚本/测试：使用 db_session_scope() 上下文管理器
        - 定时任务：使用 @with_db_session 装饰器
        
        直接使用此函数需要自行管理异常处理和 session 清理，
        否则可能导致连接池溢出。
        
        Returns:
            Session 对象
        
        示例（不推荐）:
            session = db_manager.get_session()
            try:
                # 操作...
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                on_request_end()  # 必须手动清理！
        
        推荐方式:
            with db_session_scope() as session:
                # 操作...
            # 自动提交、回滚、清理
        """
        if self._session_scope is None:
            raise RuntimeError("数据库未初始化，请先调用 init_database()")
        
        session = self._session_scope()
        
        # 一旦创建了 session，就锁定 request_id
        # 防止后续 _set_request_id() 覆盖导致 session 泄漏
        if not self._request_id_explicit.get():
            self._request_id_explicit.set(True)
            _logger.debug(f"[request_id={self._request_id_var.get()}] session 已创建，request_id 已锁定")
        
        return session
    
    def cleanup(self):
        """请求结束时自动提交并清理 session（幂等，多次调用安全）
        
        功能：
        1. 检测 session 中是否有未提交的更改（dirty/new/deleted）
        2. 有则自动提交，失败则回滚
        3. 最后清理 session，归还连接到连接池
        4. 重置 request_id 状态，为下一个请求做准备
        
        这使得 get_db() 和 RequestIDMiddleware 可以同时调用此函数而不会冲突。
        """
        request_id = self._get_request_id()
        
        if self._session_scope and self._session_scope.registry.has():
            session = self._session_scope()
            
            # 有未提交的更改时自动提交
            if session.dirty or session.new or session.deleted:
                try:
                    session.commit()
                    _logger.debug(f"[request_id={request_id}] 自动提交成功")
                except Exception as e:
                    _logger.warning(f"[request_id={request_id}] 自动提交失败，回滚: {e}")
                    try:
                        session.rollback()
                    except Exception as rb_err:
                        _logger.error(f"[request_id={request_id}] 回滚失败注意排查数据库连接问题: {rb_err}")
            
            self._session_scope.remove()
            _logger.debug(f"[request_id={request_id}] session_scope 移除完成")
        else:
            _logger.debug(f"[request_id={request_id}] 无活跃 session，跳过清理")
        
        # 重置 request_id 状态，为下一个请求做准备
        self._request_id_var.set('')
        self._request_id_explicit.set(False)
    
    # ==================== 请求ID管理（内部使用） ====================
    
    def _set_request_id(self, request_id: str = None) -> str:
        """设置当前请求ID（内部使用）
        
        request_id 一旦锁定就不能被覆盖。锁定发生在以下情况：
        1. 调用 _set_request_id() 设置后
        2. 调用 get_session() 创建 session 后
        
        这确保了同一请求内所有数据库操作使用相同的 request_id，
        防止因 request_id 变化导致的 session 泄漏。
        
        Args:
            request_id: 请求ID，不传则自动生成
            
        Returns:
            设置后的请求ID（如果已锁定，返回已有的值）
        """
        # 如果已锁定，拒绝覆盖
        if self._request_id_explicit.get():
            existing = self._request_id_var.get()
            _logger.debug(f"request_id 已锁定为 {existing}，忽略设置 {request_id}")
            return existing
        
        if not request_id:
            request_id = uuid4().hex[:8]
        
        self._request_id_var.set(request_id)
        self._request_id_explicit.set(True)  # 锁定
        return request_id
    
    def _get_request_id(self) -> str:
        """获取当前请求ID（内部使用）
        
        Returns:
            请求ID字符串
        """
        value = self._request_id_var.get()
        if not value:
            value = uuid4().hex[:8]
            self._request_id_var.set(value)
            _logger.debug(f"request_id 未设置，自动生成: {value}")
        return value


# ==================== 全局单例 ====================

db_manager = DatabaseManager()


# ==================== 公开 API 函数 ====================

def init_database(
    database_url: str = None,
    echo: bool = False,
    pool_size: int = 5,
    max_overflow: int = 10,
    pool_timeout: int = 30,
    pool_recycle: int = 3600,
    pool_pre_ping: bool = True,
    sql_log_enabled: bool = False,
    logger: logging.Logger = None,
    scopefunc: Callable = None,
    config: Any = None,
    logging_config: Any = None,
    auto_setup_query: bool = True
):
    """初始化数据库连接
    
    这是 db_manager.init() 的便捷包装函数。
    详细参数说明请参考 DatabaseManager.init()。
    
    Returns:
        tuple: (engine, session_scope)
    """
    return db_manager.init(
        database_url=database_url,
        echo=echo,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=pool_recycle,
        pool_pre_ping=pool_pre_ping,
        sql_log_enabled=sql_log_enabled,
        logger=logger,
        scopefunc=scopefunc,
        config=config,
        logging_config=logging_config,
        auto_setup_query=auto_setup_query
    )


def get_engine():
    """获取数据库引擎
    
    Returns:
        SQLAlchemy Engine 对象
        
    Raises:
        RuntimeError: 数据库未初始化时
    """
    return db_manager.engine


def on_request_end():
    """请求结束时自动提交并清理 session
    
    这是 db_manager.cleanup() 的便捷包装函数。
    幂等操作，多次调用安全。
    """
    db_manager.cleanup()


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """获取数据库 session（FastAPI 依赖注入）
    
    使用示例:
        from yweb.orm import get_db
        
        @app.get("/users")
        def get_users(db: Session = Depends(get_db)):
            users = User.query.all()
            return users
    """
    with db_session_scope() as session:
        yield session


@contextmanager
def db_session_scope(
    request_id: str = None,
    auto_commit: bool = True
) -> Generator[Session, None, None]:
    """非 HTTP 场景的 session 上下文管理器
    
    自动管理 session 生命周期，包括：
    - 设置请求ID（用于日志追踪）
    - 自动提交或回滚
    - 自动清理 session
    
    Args:
        request_id: 请求ID，用于日志追踪，不传则自动生成
        auto_commit: 是否自动提交，默认 True
    
    Yields:
        Session 对象
    
    使用示例:
        # 脚本中
        from yweb.orm import db_session_scope
        
        with db_session_scope() as session:
            user = User(name="test")
            session.add(user)
        # 自动提交并清理，无需手动调用
        
        # 手动控制提交
        with db_session_scope(auto_commit=False) as session:
            user = session.query(User).first()
            user.name = "updated"
            session.commit()  # 手动提交
        
        # 带请求ID（便于日志追踪）
        with db_session_scope(request_id="daily-report") as session:
            # 业务逻辑...
            pass
    """
    # 设置请求ID
    db_manager._set_request_id(request_id)
    session = db_manager.get_session()
    try:
        yield session
        if auto_commit:
            session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        on_request_end()


def with_db_session(
    request_id: str = None,
    auto_commit: bool = True
):
    """数据库 session 装饰器
    
    自动为函数注入 session 参数，并管理 session 生命周期。
    支持同步和异步函数。
    
    Args:
        request_id: 请求ID，用于日志追踪。
                   不传则使用 "{函数名}-{随机ID}" 格式自动生成
        auto_commit: 是否自动提交，默认 True
    
    使用示例:
        from yweb.orm import with_db_session
        
        # 基本用法 - session 作为第一个参数注入
        @with_db_session()
        def import_data(session):
            users = session.query(User).all()
            for user in users:
                # 处理逻辑...
                pass
        
        import_data()  # 调用时不需要传 session
        
        # 带其他参数
        @with_db_session()
        def create_user(session, name, email):
            user = User(name=name, email=email)
            session.add(user)
            return user
        
        user = create_user(name="Tom", email="tom@example.com")
        
        # 手动控制提交
        @with_db_session(auto_commit=False)
        def batch_update(session, user_ids):
            for uid in user_ids:
                user = session.query(User).get(uid)
                user.status = "updated"
            session.commit()  # 手动提交
        
        # 定时任务
        @scheduler.scheduled_job('cron', hour=2)
        @with_db_session(request_id="nightly-cleanup")
        def nightly_cleanup(session):
            session.query(ExpiredToken).delete()
        
        # 异步函数
        @with_db_session()
        async def async_task(session):
            users = session.query(User).all()
            await some_async_operation(users)
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        # 生成请求ID
        func_request_id = request_id or f"{func.__name__}-{{rand}}"
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            # 替换 {rand} 占位符
            actual_request_id = func_request_id.replace("{rand}", uuid4().hex[:6])
            db_manager._set_request_id(actual_request_id)
            
            session = db_manager.get_session()
            try:
                result = func(session, *args, **kwargs)
                if auto_commit:
                    session.commit()
                return result
            except Exception:
                session.rollback()
                raise
            finally:
                on_request_end()
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            # 替换 {rand} 占位符
            actual_request_id = func_request_id.replace("{rand}", uuid4().hex[:6])
            db_manager._set_request_id(actual_request_id)
            
            session = db_manager.get_session()
            try:
                result = await func(session, *args, **kwargs)
                if auto_commit:
                    session.commit()
                return result
            except Exception:
                session.rollback()
                raise
            finally:
                on_request_end()
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator
