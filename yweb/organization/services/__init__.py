"""
组织管理模块 - 服务层

按聚合拆分的服务类：
- BaseOrganizationService: 组织管理
- BaseDepartmentService: 部门管理 + 负责人
- BaseEmployeeService: 员工管理 + 关联管理
"""

from .org_service import BaseOrganizationService
from .dept_service import BaseDepartmentService
from .emp_service import BaseEmployeeService
from .sync_service import BaseSyncService, SyncResult

__all__ = [
    # 核心服务
    "BaseOrganizationService",
    "BaseDepartmentService",
    "BaseEmployeeService",
    # 同步服务
    "BaseSyncService",
    "SyncResult",
]
