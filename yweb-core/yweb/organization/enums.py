"""
组织管理模块 - 枚举定义

提供组织管理相关的枚举类型
"""

from enum import Enum, IntEnum


class ExternalSource(str, Enum):
    """外部系统来源
    
    标识组织数据从哪个外部系统同步而来。
    一个组织只能从一个外部系统同步。
    """
    
    # 本地创建，非外部同步
    NONE = "none"
    
    # 企业微信
    WECHAT_WORK = "wechat_work"
    
    # 飞书
    FEISHU = "feishu"
    
    # 钉钉
    DINGTALK = "dingtalk"
    
    # 自定义外部系统
    CUSTOM = "custom"


class EmployeeStatus(IntEnum):
    """员工状态（按入职生命周期排列）
    
    员工在组织中的状态。数值按时间线/语义分段设计：
    - 负数：已结束（终态）
    - 零：冻结/暂停
    - 正数 1→2→3：入职生命周期正向推进
    
    便捷判断：
    - status >= 0  → 未离职
    - status > 0   → 活跃状态（待入职/试用/在职）
    - status >= 2  → 正式员工（试用期+在职）
    """
    
    # 离职（已结束，终态）
    RESIGNED = -1
    
    # 停职（冻结态）
    SUSPENDED = 0
    
    # 待入职（生命周期起点）
    PENDING = 1
    
    # 试用期（过渡阶段）
    PROBATION = 2
    
    # 在职（正式员工）
    ACTIVE = 3


class AccountStatus(IntEnum):
    """账号状态常量（用于 API 参数描述和前端展示）
    
    注意：此枚举仅作为常量定义，不再对应员工表中的存储字段。
    账号状态从关联的 User.is_active 动态推导：
    - user_id IS NULL → NOT_ACTIVATED (0)
    - user.is_active == True → ACTIVATED (1)
    - user.is_active == False → DISABLED (-1)
    """
    
    # 已禁用（user.is_active = False）
    DISABLED = -1
    
    # 未激活（无关联用户）
    NOT_ACTIVATED = 0
    
    # 已激活（user.is_active = True）
    ACTIVATED = 1


class Gender(IntEnum):
    """性别"""
    
    # 未知
    UNKNOWN = 0
    
    # 男
    MALE = 1
    
    # 女
    FEMALE = 2


class SyncStatus(str, Enum):
    """同步状态"""
    
    # 未同步
    NONE = "none"
    
    # 同步中
    SYNCING = "syncing"
    
    # 同步成功
    SUCCESS = "success"
    
    # 同步失败
    FAILED = "failed"


__all__ = [
    "ExternalSource",
    "EmployeeStatus",
    "AccountStatus",
    "Gender",
    "SyncStatus",
]
