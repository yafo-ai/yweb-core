"""任务存储模块

提供不同的任务存储实现：
- MemoryStore: 内存存储（默认）
- ORMJobStore: YWeb ORM 存储（持久化）
"""

from .base import BaseStore
from .memory import MemoryStore
from .orm import ORMJobStore

__all__ = [
    "BaseStore",
    "MemoryStore",
    "ORMJobStore",
]
