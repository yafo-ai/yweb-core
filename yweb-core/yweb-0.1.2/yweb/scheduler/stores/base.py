"""任务存储抽象基类

定义任务存储的接口规范。
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Any
from datetime import datetime


class BaseStore(ABC):
    """任务存储抽象基类
    
    定义任务存储的标准接口，所有存储实现都应继承此类。
    """
    
    @abstractmethod
    def add_job(self, job: Any) -> None:
        """添加任务
        
        Args:
            job: 任务对象
        """
        pass
    
    @abstractmethod
    def update_job(self, job: Any) -> None:
        """更新任务
        
        Args:
            job: 任务对象
        """
        pass
    
    @abstractmethod
    def remove_job(self, job_id: str) -> None:
        """删除任务
        
        Args:
            job_id: 任务 ID
        """
        pass
    
    @abstractmethod
    def lookup_job(self, job_id: str) -> Optional[Any]:
        """查找任务
        
        Args:
            job_id: 任务 ID
        
        Returns:
            任务对象或 None
        """
        pass
    
    @abstractmethod
    def get_all_jobs(self) -> List[Any]:
        """获取所有任务
        
        Returns:
            任务列表
        """
        pass
    
    @abstractmethod
    def get_due_jobs(self, now: datetime) -> List[Any]:
        """获取到期的任务
        
        Args:
            now: 当前时间
        
        Returns:
            到期任务列表
        """
        pass
    
    @abstractmethod
    def get_next_run_time(self) -> Optional[datetime]:
        """获取下次执行时间
        
        Returns:
            最近的下次执行时间
        """
        pass
