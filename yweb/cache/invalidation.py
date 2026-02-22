"""缓存自动失效模块

提供 SQLAlchemy 模型变更时自动失效缓存的功能。

使用示例:
    from yweb.cache import cached, cache_invalidator
    
    # 1. 定义带缓存的函数
    @cached(ttl=60)
    def get_user_by_id(user_id: int):
        return User.get_by_id(user_id)
    
    # 2. 注册自动失效
    cache_invalidator.register(User, get_user_by_id)
    
    # 3. 之后 User 更新/删除时，缓存自动失效
    user.name = "新名字"
    user.update()  # 自动触发 get_user_by_id.invalidate(user.id)
"""

from typing import Callable, Dict, List, Type, Any, Optional, Set, Union
from weakref import WeakSet
import threading

from yweb.log import get_logger

logger = get_logger("yweb.cache.invalidation")


class CacheInvalidator:
    """缓存自动失效管理器
    
    监听 SQLAlchemy 模型事件，自动失效相关缓存。
    
    支持的事件:
        - after_update: 模型更新后
        - after_delete: 模型删除后
        - after_insert: 模型插入后（可选）
    
    使用示例:
        # 基本用法
        cache_invalidator.register(User, get_user_by_id)
        
        # 自定义 key 提取器
        cache_invalidator.register(
            User, 
            get_user_by_username,
            key_extractor=lambda user: user.username
        )
        
        # 监听特定事件
        cache_invalidator.register(
            User, 
            get_user_by_id,
            events=("after_update",)  # 只在更新时失效
        )
        
        # 注册多个缓存函数
        cache_invalidator.register(User, get_user_by_id)
        cache_invalidator.register(User, get_user_by_username, 
                                   key_extractor=lambda u: u.username)
    """
    
    def __init__(self):
        self._registrations: Dict[Type, List[dict]] = {}
        self._listened_events: Dict[Type, Set[str]] = {}  # model -> 已注册监听的事件名集合
        self._lock = threading.RLock()
        self._enabled = True
    
    def register(
        self,
        model: Type,
        cached_func: Any,
        key_extractor: Optional[Callable[[Any], Any]] = None,
        events: tuple = ("after_update", "after_delete"),
    ) -> "CacheInvalidator":
        """注册模型与缓存函数的关联
        
        Args:
            model: SQLAlchemy 模型类
            cached_func: 被 @cached 装饰的函数（CachedFunction 实例）
            key_extractor: 从模型实例提取缓存键的函数，默认提取 id
            events: 要监听的事件元组，默认 ("after_update", "after_delete")
        
        Returns:
            self，支持链式调用
        
        Raises:
            ValueError: 如果 cached_func 不是 CachedFunction 实例
        """
        # 验证 cached_func
        if not hasattr(cached_func, 'invalidate'):
            raise ValueError(
                f"cached_func 必须是被 @cached 装饰的函数，"
                f"但收到的是 {type(cached_func).__name__}"
            )
        
        # 默认 key 提取器：获取 id 属性
        if key_extractor is None:
            key_extractor = lambda obj: obj.id
        
        with self._lock:
            # 初始化模型的注册列表
            if model not in self._registrations:
                self._registrations[model] = []
            
            # 添加注册信息
            self._registrations[model].append({
                "func": cached_func,
                "key_extractor": key_extractor,
                "events": events,
            })
            
            # 设置 SQLAlchemy 事件监听（按事件粒度，支持增量注册）
            if model not in self._listened_events:
                self._listened_events[model] = set()
            
            new_events = set(events) - self._listened_events[model]
            if new_events:
                self._setup_listeners_for_events(model, new_events)
                self._listened_events[model].update(new_events)
            
            logger.debug(
                f"Registered cache invalidation: "
                f"{model.__name__} -> {cached_func.__name__}"
            )
        
        return self
    
    def _setup_listeners_for_events(self, model: Type, event_names: Set[str]):
        """为指定的事件类型设置 SQLAlchemy 监听器
        
        Args:
            model: SQLAlchemy 模型类
            event_names: 需要新增监听的事件名集合
        """
        try:
            from sqlalchemy import event
        except ImportError:
            logger.warning(
                "SQLAlchemy 未安装，无法使用自动缓存失效功能"
            )
            return
        
        for event_name in event_names:
            if event_name in ("after_update", "after_delete", "after_insert"):
                event.listen(
                    model, 
                    event_name, 
                    self._create_handler(model, event_name),
                    propagate=True
                )
                logger.debug(
                    f"Set up {event_name} listener for {model.__name__}"
                )
    
    def _create_handler(self, model: Type, event_name: str):
        """创建事件处理器"""
        def handler(mapper, connection, target):
            if not self._enabled:
                return
            
            self._invalidate_for_target(model, target, event_name)
        
        return handler
    
    def _invalidate_for_target(
        self, 
        model: Type, 
        target: Any, 
        event_name: str
    ):
        """为目标对象执行缓存失效
        
        支持 key_extractor 返回单个值或列表：
        - 单个值：失效单个缓存
        - 列表：批量失效多个缓存（用于关联模型场景）
        """
        if not self._enabled:
            return
        
        if model not in self._registrations:
            return
        
        for reg in self._registrations[model]:
            # 检查是否监听此事件
            if event_name not in reg.get("events", ()):
                continue
            
            try:
                # 提取缓存键（可能是单个值或列表）
                keys = reg["key_extractor"](target)
                func = reg["func"]
                
                # 支持返回列表（批量失效）
                if isinstance(keys, (list, tuple)):
                    for key in keys:
                        func.invalidate(key)
                    logger.debug(
                        f"Auto-invalidated cache (batch): "
                        f"{func.__name__}({len(keys)} keys) on {event_name}"
                    )
                else:
                    # 单个值
                    func.invalidate(keys)
                    logger.debug(
                        f"Auto-invalidated cache: "
                        f"{func.__name__}({keys}) on {event_name}"
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to invalidate cache for {model.__name__}: {e}"
                )
    
    def unregister(
        self, 
        model: Type, 
        cached_func: Optional[Any] = None
    ) -> bool:
        """取消注册
        
        Args:
            model: 模型类
            cached_func: 可选，指定要取消的缓存函数。
                        如果不指定，取消该模型的所有注册。
        
        Returns:
            是否成功取消
        """
        with self._lock:
            if model not in self._registrations:
                return False
            
            if cached_func is None:
                # 取消该模型的所有注册
                del self._registrations[model]
                return True
            else:
                # 只取消特定函数的注册
                original_len = len(self._registrations[model])
                self._registrations[model] = [
                    reg for reg in self._registrations[model]
                    if reg["func"] is not cached_func
                ]
                return len(self._registrations[model]) < original_len
    
    def disable(self):
        """临时禁用自动失效"""
        self._enabled = False
        logger.debug("Cache auto-invalidation disabled")
    
    def enable(self):
        """启用自动失效"""
        self._enabled = True
        logger.debug("Cache auto-invalidation enabled")
    
    @property
    def is_enabled(self) -> bool:
        """是否启用"""
        return self._enabled
    
    def get_registrations(self, model: Optional[Type] = None) -> dict:
        """获取注册信息
        
        Args:
            model: 可选，指定模型。不指定则返回所有。
        
        Returns:
            注册信息字典
        """
        if model is not None:
            regs = self._registrations.get(model, [])
            return {
                model.__name__: [
                    {
                        "func": reg["func"].__name__,
                        "events": reg["events"],
                    }
                    for reg in regs
                ]
            }
        
        return {
            m.__name__: [
                {
                    "func": reg["func"].__name__,
                    "events": reg["events"],
                }
                for reg in regs
            ]
            for m, regs in self._registrations.items()
        }
    
    def clear(self):
        """清空所有注册"""
        with self._lock:
            self._registrations.clear()
            # 注意：SQLAlchemy 事件监听器不会被移除
            # 但由于 _registrations 为空，handler 不会执行任何操作
            logger.debug("All cache invalidation registrations cleared")


# 全局实例
cache_invalidator = CacheInvalidator()


class InvalidationContext:
    """缓存失效控制上下文
    
    用于临时禁用自动失效，例如批量导入时。
    
    使用示例:
        # 批量导入时临时禁用
        with no_auto_invalidation():
            for data in bulk_data:
                User.create(data)
        
        # 导入完成后手动失效
        get_user_list.clear()
    """
    
    def __init__(self, invalidator: CacheInvalidator):
        self._invalidator = invalidator
        self._was_enabled = True
    
    def __enter__(self):
        self._was_enabled = self._invalidator.is_enabled
        self._invalidator.disable()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._was_enabled:
            self._invalidator.enable()
        return False


def no_auto_invalidation() -> InvalidationContext:
    """创建禁用自动失效的上下文
    
    使用示例:
        with no_auto_invalidation():
            # 这里的数据库操作不会触发缓存失效
            bulk_update_users(data)
    """
    return InvalidationContext(cache_invalidator)


__all__ = [
    "CacheInvalidator",
    "cache_invalidator",
    "InvalidationContext",
    "no_auto_invalidation",
]
