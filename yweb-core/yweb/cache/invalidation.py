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


def _extract_entities(result: Any, model_classes: Set[Type]) -> List[tuple]:
    """从缓存结果中提取 ORM 实体实例

    扫描单对象、列表、分页对象等结构，返回 [(model_class, entity_id), ...] 列表。
    只提取 model_classes 中注册过的模型类型。
    """
    entities = []

    def _check(obj):
        obj_type = type(obj)
        for mc in model_classes:
            if obj_type is mc or (isinstance(obj, type) is False and isinstance(obj, mc)):
                eid = getattr(obj, "id", None)
                if eid is not None:
                    entities.append((mc, eid))
                return

    if result is None:
        return entities

    if isinstance(result, (list, tuple, set, frozenset)):
        for item in result:
            _check(item)
    elif hasattr(result, "items") and isinstance(result.items, (list, tuple)):
        for item in result.items:
            _check(item)
    else:
        _check(result)

    return entities


class CacheInvalidator:
    """缓存自动失效管理器
    
    监听 SQLAlchemy 模型事件，自动失效相关缓存。
    
    支持两种失效策略：
    
    1. **key_extractor 精确失效**（默认）：从变更实体提取缓存键参数，
       调用 ``func.invalidate(key)``。适用于 ``get_user(user_id)`` 等
       参数就是实体 ID 的场景。
    
    2. **依赖追踪失效**（自动启用）：缓存写入时扫描结果中包含的实体，
       建立反向索引 ``(Model, entity_id) → {cache_keys}``。实体变更时
       精确失效包含该实体的所有缓存条目。适用于列表查询等参数不是实体 ID
       的场景，无需额外配置。
    
    使用示例:
        # 单实体查询 — key_extractor 直接命中
        cache_invalidator.register(User, get_user_by_id)
        
        # 列表查询 — 依赖追踪自动处理
        cache_invalidator.register(Order, get_orders)
        # Order 变更时，自动失效所有包含该 Order 的缓存条目
    """
    
    def __init__(self):
        self._registrations: Dict[Type, List[dict]] = {}
        self._listened_events: Dict[Type, Set[str]] = {}
        self._watched_relationships: Set[str] = set()
        self._lock = threading.RLock()
        self._enabled = True
        # 反向索引: (model_class, entity_id) → set of (cached_func_id, raw_cache_key)
        self._dep_index: Dict[tuple, Set[tuple]] = {}
        # func id → CachedFunction 引用
        self._tracked_funcs: Dict[int, Any] = {}
    
    def register(
        self,
        model: Type,
        cached_func: Any,
        key_extractor: Optional[Callable[[Any], Any]] = None,
        events: tuple = ("after_update", "after_delete"),
        watch_relationships: bool = True,
    ) -> "CacheInvalidator":
        """注册模型与缓存函数的关联
        
        Args:
            model: SQLAlchemy 模型类
            cached_func: 被 @cached 装饰的函数（CachedFunction 实例）
            key_extractor: 从模型实例提取缓存键的函数，默认提取 id
            events: 要监听的事件元组，默认 ("after_update", "after_delete")
            watch_relationships: 是否监听 ManyToMany 集合变更（append/remove），默认 True。
                自动检测模型上的 ManyToMany 关系，集合增删时触发缓存失效。
                例如 user.roles.append(role) 会自动失效该 user 的缓存。
                模型无 ManyToMany 关系时无额外开销。设为 False 可关闭。
        
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
            
            # 监听 ManyToMany 集合变更
            if watch_relationships:
                self._setup_relationship_listeners(model)
            
            logger.debug(
                f"Registered cache invalidation: "
                f"{model.__name__} -> {cached_func.__name__}"
                f"{' (watching relationships)' if watch_relationships else ''}"
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
    
    def _setup_relationship_listeners(self, model: Type):
        """监听模型上所有 ManyToMany 集合的 append/remove 事件
        
        当 user.roles.append(role) 或 user.roles.remove(role) 时，
        自动失效该 user 的缓存。仅监听有 secondary 中间表的关系
        （即 ManyToMany），不监听 OneToMany。
        """
        try:
            from sqlalchemy import event, inspect as sa_inspect
        except ImportError:
            return
        
        try:
            mapper = sa_inspect(model)
        except Exception:
            return
        
        for rel in mapper.relationships:
            if rel.secondary is None:
                continue
            
            watch_key = f"{model.__name__}.{rel.key}"
            if watch_key in self._watched_relationships:
                continue
            self._watched_relationships.add(watch_key)
            
            rel_attr = getattr(model, rel.key)
            
            def _make_collection_handler(rel_key):
                def handler(target, value, initiator):
                    if not self._enabled:
                        return
                    self._invalidate_for_target(
                        model, target, "collection_change"
                    )
                    logger.debug(
                        f"Collection change on {model.__name__}.{rel_key}: "
                        f"invalidated cache for id={getattr(target, 'id', '?')}"
                    )
                return handler
            
            handler = _make_collection_handler(rel.key)
            event.listen(rel_attr, "append", handler)
            event.listen(rel_attr, "remove", handler)
            
            logger.debug(
                f"Watching M2M collection: {watch_key} (append/remove)"
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
        
        双路径失效：
        1. key_extractor 精确失效（参数即 ID 的场景）
        2. 反向索引失效（列表查询等依赖追踪场景）
        """
        if not self._enabled:
            return
        
        entity_id = getattr(target, "id", None)
        
        # 路径 1: key_extractor 精确失效
        if model in self._registrations:
            for reg in self._registrations[model]:
                if event_name != "collection_change":
                    if event_name not in reg.get("events", ()):
                        continue
                
                try:
                    keys = reg["key_extractor"](target)
                    func = reg["func"]
                    
                    if isinstance(keys, (list, tuple)):
                        for key in keys:
                            func.invalidate(key)
                    else:
                        func.invalidate(keys)
                    logger.debug(
                        f"Auto-invalidated cache: "
                        f"{func.__name__}({keys}) on {event_name}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to invalidate cache for {model.__name__}: {e}"
                    )
        
        # 路径 2: 反向索引失效（依赖追踪）
        if entity_id is not None:
            self._invalidate_by_dep(model, entity_id)
    
    def track_dependencies(
        self, cached_func: Any, cache_key: str, result: Any
    ) -> None:
        """扫描缓存结果，建立 (Model, entity_id) → cache_key 的反向索引
        
        由 CachedFunction.__call__ 在缓存写入后调用。
        """
        if not self._registrations:
            return
        
        registered_models = set(self._registrations.keys())
        entities = _extract_entities(result, registered_models)
        if not entities:
            return
        
        func_id = id(cached_func)
        self._tracked_funcs[func_id] = cached_func
        
        with self._lock:
            for model_cls, entity_id in entities:
                dep_key = (model_cls, entity_id)
                if dep_key not in self._dep_index:
                    self._dep_index[dep_key] = set()
                self._dep_index[dep_key].add((func_id, cache_key))
    
    def _invalidate_by_dep(self, model: Type, entity_id: Any) -> None:
        """通过反向索引失效所有包含指定实体的缓存条目"""
        dep_key = (model, entity_id)
        
        with self._lock:
            entries = self._dep_index.pop(dep_key, None)
        
        if not entries:
            return
        
        for func_id, cache_key in entries:
            func = self._tracked_funcs.get(func_id)
            if func is None:
                continue
            try:
                func._backend.delete(cache_key)
                logger.debug(
                    f"Dep-invalidated: {func.__name__} key={cache_key} "
                    f"(dep={model.__name__}#{entity_id})"
                )
            except Exception as e:
                logger.warning(f"Dep-invalidation failed: {e}")
    
    def remove_dep_entries(self, cache_key: str) -> None:
        """清理反向索引中指定 cache_key 的条目（缓存条目被淘汰时调用）"""
        with self._lock:
            empty_keys = []
            for dep_key, entries in self._dep_index.items():
                entries.discard(cache_key)
                if not entries:
                    empty_keys.append(dep_key)
            for dk in empty_keys:
                del self._dep_index[dk]
    
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
            self._watched_relationships.clear()
            self._dep_index.clear()
            self._tracked_funcs.clear()
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
