"""
组织管理模块 - 抽象模型

提供组织管理的抽象模型类，应用层通过继承这些抽象类来创建具体的模型。
"""

from .organization import AbstractOrganization
from .department import AbstractDepartment
from .employee import AbstractEmployee
from .emp_org_rel import AbstractEmployeeOrgRel
from .emp_dept_rel import AbstractEmployeeDeptRel
from .dept_leader import AbstractDepartmentLeader

__all__ = [
    "AbstractOrganization",
    "AbstractDepartment",
    "AbstractEmployee",
    "AbstractEmployeeOrgRel",
    "AbstractEmployeeDeptRel",
    "AbstractDepartmentLeader",
]
