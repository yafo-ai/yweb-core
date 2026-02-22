"""
组织管理模块 - 辅助函数

提供 setup_org_relationships() 辅助函数，用于自动设置模型间的 relationship。
解决抽象类无法预先定义 relationship 的问题。

使用方式：

方式1（推荐）：使用辅助函数自动设置所有关系
    
    from yweb.organization import (
        AbstractOrganization, AbstractDepartment, AbstractEmployee,
        AbstractEmployeeOrgRel, AbstractEmployeeDeptRel, AbstractDepartmentLeader,
        setup_org_relationships,
    )
    
    class Organization(AbstractOrganization): pass
    class Department(AbstractDepartment): pass
    class Employee(AbstractEmployee): pass
    class EmployeeOrgRel(AbstractEmployeeOrgRel): pass
    class EmployeeDeptRel(AbstractEmployeeDeptRel): pass
    class DepartmentLeader(AbstractDepartmentLeader): pass
    
    # 一行代码设置所有关系
    setup_org_relationships(
        Organization, Department, Employee,
        EmployeeOrgRel, EmployeeDeptRel, DepartmentLeader
    )
    
    # 现在可以直接使用：
    dept = Department.get(1)
    print(dept.organization.name)  # 关联的组织
    print(dept.children)           # 子部门列表
    print(dept.parent)             # 父部门

方式2：手动定义关系（更灵活但代码更多）

    class Department(AbstractDepartment):
        organization = relationship("Organization", back_populates="departments")
        parent = relationship("Department", remote_side="Department.id", back_populates="children")
        children = relationship("Department", back_populates="parent")
        # ... 更多关系定义

级联软删除配置：

    默认策略采用保护性删除：
    - 组织有部门/员工时禁止删除
    - 部门有子部门/员工时禁止删除
    - 员工删除时自动清理关联
    
    可通过 cascade_config 参数自定义：
    
    setup_org_relationships(
        ...,
        cascade_config={
            "org_to_dept": DELETE,  # 改为级联删除
        }
    )
"""

from typing import Type, Optional, Dict
from sqlalchemy.orm import relationship, backref

# 导入级联软删除常量
from yweb.orm.fields import (
    SOFT_DELETE_CASCADE_KEY,
    OnDelete,
    DELETE,
    SET_NULL,
    PROTECT,
    DO_NOTHING,
)


# ==================== 默认级联配置 ====================

DEFAULT_CASCADE_CONFIG: Dict[str, OnDelete] = {
    # 组织删除时 - 保护性删除（有部门/员工时禁止删除）
    "org_to_dept": PROTECT,          # 有部门时禁止删除
    "org_to_emp_org_rel": PROTECT,   # 有员工时禁止删除
    
    # 部门删除时 - 保护性删除（有子部门/员工时禁止删除）
    "dept_to_children": PROTECT,     # 有子部门时禁止删除
    "dept_to_emp_dept_rel": PROTECT, # 有员工时禁止删除
    "dept_to_leader_rel": DELETE,    # 负责人关联可以删除
    
    # 员工删除时 - 清理关联
    "emp_to_primary_leader": SET_NULL,  # 部门主负责人置空
    "emp_to_emp_org_rel": DELETE,       # 员工-组织关联删除
    "emp_to_emp_dept_rel": DELETE,      # 员工-部门关联删除
    "emp_to_leader_rel": DELETE,        # 负责人关联删除
}


def setup_org_relationships(
    org_model: Type,
    dept_model: Type,
    employee_model: Type,
    emp_org_rel_model: Optional[Type] = None,
    emp_dept_rel_model: Optional[Type] = None,
    dept_leader_model: Optional[Type] = None,
    cascade_config: Optional[Dict[str, OnDelete]] = None,
) -> None:
    """设置组织架构模型间的所有 relationship
    
    此函数会自动为各模型添加 relationship 属性，简化用户代码。
    同时配置级联软删除行为。
    
    Args:
        org_model: 组织模型类（继承自 AbstractOrganization）
        dept_model: 部门模型类（继承自 AbstractDepartment）
        employee_model: 员工模型类（继承自 AbstractEmployee）
        emp_org_rel_model: 员工-组织关联模型（可选）
        emp_dept_rel_model: 员工-部门关联模型（可选）
        dept_leader_model: 部门负责人模型（可选）
        cascade_config: 级联软删除配置（可选，覆盖默认配置）
            可配置的键：
            - org_to_dept: 组织→部门（默认 PROTECT）
            - org_to_emp_org_rel: 组织→员工关联（默认 PROTECT）
            - dept_to_children: 部门→子部门（默认 PROTECT）
            - dept_to_emp_dept_rel: 部门→员工关联（默认 PROTECT）
            - dept_to_leader_rel: 部门→负责人关联（默认 DELETE）
            - emp_to_primary_leader: 员工→主负责人引用（默认 SET_NULL）
            - emp_to_emp_org_rel: 员工→组织关联（默认 DELETE）
            - emp_to_emp_dept_rel: 员工→部门关联（默认 DELETE）
            - emp_to_leader_rel: 员工→负责人关联（默认 DELETE）
    
    设置的关系包括：
    
    Organization:
        - departments: List[Department] (一对多)
        - employee_org_rels: List[EmployeeOrgRel] (一对多，如果提供)
    
    Department:
        - organization: Organization (多对一)
        - parent: Department (自引用，多对一)
        - children: List[Department] (自引用，一对多)
        - primary_leader: Employee (多对一)
        - employee_dept_rels: List[EmployeeDeptRel] (一对多，如果提供)
        - department_leader_rels: List[DepartmentLeader] (一对多，如果提供)
    
    Employee:
        - primary_org: Organization (多对一)
        - primary_dept: Department (多对一)
        - employee_org_rels: List[EmployeeOrgRel] (一对多，如果提供)
        - employee_dept_rels: List[EmployeeDeptRel] (一对多，如果提供)
        - department_leader_rels: List[DepartmentLeader] (一对多，如果提供)
    
    EmployeeOrgRel (如果提供):
        - employee: Employee (多对一)
        - organization: Organization (多对一)
    
    EmployeeDeptRel (如果提供):
        - employee: Employee (多对一)
        - department: Department (多对一)
    
    DepartmentLeader (如果提供):
        - department: Department (多对一)
        - employee: Employee (多对一)
    
    Example:
        >>> from yweb.organization import setup_org_relationships
        >>> setup_org_relationships(
        ...     Organization, Department, Employee,
        ...     EmployeeOrgRel, EmployeeDeptRel, DepartmentLeader
        ... )
        >>> 
        >>> # 现在可以使用关系了
        >>> dept = Department.get(1)
        >>> print(dept.organization.name)
        >>> for child in dept.children:
        ...     print(child.name)
        
        >>> # 自定义级联配置
        >>> from yweb.orm.fields import DELETE
        >>> setup_org_relationships(
        ...     ...,
        ...     cascade_config={"org_to_dept": DELETE}  # 组织删除时级联删除部门
        ... )
    """
    # 合并级联配置
    cascade = {**DEFAULT_CASCADE_CONFIG, **(cascade_config or {})}
    
    org_name = org_model.__name__
    dept_name = dept_model.__name__
    emp_name = employee_model.__name__
    
    # ============================================================
    # Organization 的关系
    # ============================================================
    
    # Organization.departments -> List[Department]
    # 级联行为：组织删除时，检查是否有部门（默认 PROTECT）
    if not hasattr(org_model, 'departments') or org_model.departments is None:
        org_model.departments = relationship(
            dept_name,
            back_populates="organization",
            foreign_keys=f"[{dept_name}.org_id]",
            lazy="selectin",
            info={SOFT_DELETE_CASCADE_KEY: cascade["org_to_dept"]},
        )
    
    # Organization.employee_org_rels -> List[EmployeeOrgRel]
    # 级联行为：组织删除时，检查是否有员工关联（默认 PROTECT）
    if emp_org_rel_model and (not hasattr(org_model, 'employee_org_rels') or org_model.employee_org_rels is None):
        org_model.employee_org_rels = relationship(
            emp_org_rel_model.__name__,
            back_populates="organization",
            lazy="selectin",
            info={SOFT_DELETE_CASCADE_KEY: cascade["org_to_emp_org_rel"]},
        )
    
    # ============================================================
    # Department 的关系
    # ============================================================
    
    # Department.organization -> Organization（多对一，无级联）
    if not hasattr(dept_model, 'organization') or dept_model.organization is None:
        dept_model.organization = relationship(
            org_name,
            back_populates="departments",
            foreign_keys=f"[{dept_name}.org_id]",
        )
    
    # Department.parent -> Department (自引用，多对一，无级联)
    if not hasattr(dept_model, 'parent') or dept_model.parent is None:
        dept_model.parent = relationship(
            dept_name,
            remote_side=f"{dept_name}.id",
            back_populates="children",
            foreign_keys=f"[{dept_name}.parent_id]",
        )
    
    # Department.children -> List[Department] (自引用，一对多)
    # 级联行为：部门删除时，检查是否有子部门（默认 PROTECT）
    if not hasattr(dept_model, 'children') or dept_model.children is None:
        dept_model.children = relationship(
            dept_name,
            back_populates="parent",
            foreign_keys=f"[{dept_name}.parent_id]",
            lazy="selectin",
            info={SOFT_DELETE_CASCADE_KEY: cascade["dept_to_children"]},
        )
    
    # Department.primary_leader -> Employee（多对一，无级联）
    if not hasattr(dept_model, 'primary_leader') or dept_model.primary_leader is None:
        dept_model.primary_leader = relationship(
            emp_name,
            foreign_keys=f"[{dept_name}.primary_leader_id]",
            back_populates="leading_departments",
        )
    
    # Department.employee_dept_rels -> List[EmployeeDeptRel]
    # 级联行为：部门删除时，检查是否有员工关联（默认 PROTECT）
    if emp_dept_rel_model and (not hasattr(dept_model, 'employee_dept_rels') or dept_model.employee_dept_rels is None):
        dept_model.employee_dept_rels = relationship(
            emp_dept_rel_model.__name__,
            back_populates="department",
            lazy="selectin",
            info={SOFT_DELETE_CASCADE_KEY: cascade["dept_to_emp_dept_rel"]},
        )
    
    # Department.department_leader_rels -> List[DepartmentLeader]
    # 级联行为：部门删除时，删除负责人关联（默认 DELETE）
    if dept_leader_model and (not hasattr(dept_model, 'department_leader_rels') or dept_model.department_leader_rels is None):
        dept_model.department_leader_rels = relationship(
            dept_leader_model.__name__,
            back_populates="department",
            lazy="selectin",
            info={SOFT_DELETE_CASCADE_KEY: cascade["dept_to_leader_rel"]},
        )
    
    # ============================================================
    # Employee 的关系
    # ============================================================
    
    # Employee.primary_org -> Organization（多对一，无级联）
    if not hasattr(employee_model, 'primary_org') or employee_model.primary_org is None:
        employee_model.primary_org = relationship(
            org_name,
            foreign_keys=f"[{emp_name}.primary_org_id]",
        )
    
    # Employee.primary_dept -> Department（多对一，无级联）
    if not hasattr(employee_model, 'primary_dept') or employee_model.primary_dept is None:
        employee_model.primary_dept = relationship(
            dept_name,
            foreign_keys=f"[{emp_name}.primary_dept_id]",
        )
    
    # Employee.employee_org_rels -> List[EmployeeOrgRel]
    # 级联行为：员工删除时，删除员工-组织关联（默认 DELETE）
    if emp_org_rel_model and (not hasattr(employee_model, 'employee_org_rels') or employee_model.employee_org_rels is None):
        employee_model.employee_org_rels = relationship(
            emp_org_rel_model.__name__,
            back_populates="employee",
            lazy="selectin",
            info={SOFT_DELETE_CASCADE_KEY: cascade["emp_to_emp_org_rel"]},
        )
    
    # Employee.employee_dept_rels -> List[EmployeeDeptRel]
    # 级联行为：员工删除时，删除员工-部门关联（默认 DELETE）
    if emp_dept_rel_model and (not hasattr(employee_model, 'employee_dept_rels') or employee_model.employee_dept_rels is None):
        employee_model.employee_dept_rels = relationship(
            emp_dept_rel_model.__name__,
            back_populates="employee",
            lazy="selectin",
            info={SOFT_DELETE_CASCADE_KEY: cascade["emp_to_emp_dept_rel"]},
        )
    
    # Employee.department_leader_rels -> List[DepartmentLeader]
    # 级联行为：员工删除时，删除负责人关联（默认 DELETE）
    if dept_leader_model and (not hasattr(employee_model, 'department_leader_rels') or employee_model.department_leader_rels is None):
        employee_model.department_leader_rels = relationship(
            dept_leader_model.__name__,
            back_populates="employee",
            lazy="selectin",
            info={SOFT_DELETE_CASCADE_KEY: cascade["emp_to_leader_rel"]},
        )
    
    # Employee.leading_departments -> List[Department]
    # 反向关系：员工作为主负责人的部门列表
    # 级联行为：员工删除时，将这些部门的 primary_leader_id 置空（默认 SET_NULL）
    if not hasattr(employee_model, 'leading_departments') or employee_model.leading_departments is None:
        employee_model.leading_departments = relationship(
            dept_name,
            foreign_keys=f"[{dept_name}.primary_leader_id]",
            back_populates="primary_leader",
            lazy="selectin",
            info={SOFT_DELETE_CASCADE_KEY: cascade["emp_to_primary_leader"]},
        )
    
    # ============================================================
    # EmployeeOrgRel 的关系
    # ============================================================
    if emp_org_rel_model:
        rel_name = emp_org_rel_model.__name__
        
        # EmployeeOrgRel.employee -> Employee
        if not hasattr(emp_org_rel_model, 'employee') or emp_org_rel_model.employee is None:
            emp_org_rel_model.employee = relationship(
                emp_name,
                back_populates="employee_org_rels",
                foreign_keys=f"[{rel_name}.employee_id]",
            )
        
        # EmployeeOrgRel.organization -> Organization
        if not hasattr(emp_org_rel_model, 'organization') or emp_org_rel_model.organization is None:
            emp_org_rel_model.organization = relationship(
                org_name,
                back_populates="employee_org_rels",
                foreign_keys=f"[{rel_name}.org_id]",
            )
    
    # ============================================================
    # EmployeeDeptRel 的关系
    # ============================================================
    if emp_dept_rel_model:
        rel_name = emp_dept_rel_model.__name__
        
        # EmployeeDeptRel.employee -> Employee
        if not hasattr(emp_dept_rel_model, 'employee') or emp_dept_rel_model.employee is None:
            emp_dept_rel_model.employee = relationship(
                emp_name,
                back_populates="employee_dept_rels",
                foreign_keys=f"[{rel_name}.employee_id]",
            )
        
        # EmployeeDeptRel.department -> Department
        if not hasattr(emp_dept_rel_model, 'department') or emp_dept_rel_model.department is None:
            emp_dept_rel_model.department = relationship(
                dept_name,
                back_populates="employee_dept_rels",
                foreign_keys=f"[{rel_name}.dept_id]",
            )
    
    # ============================================================
    # DepartmentLeader 的关系
    # ============================================================
    if dept_leader_model:
        rel_name = dept_leader_model.__name__
        
        # DepartmentLeader.department -> Department
        if not hasattr(dept_leader_model, 'department') or dept_leader_model.department is None:
            dept_leader_model.department = relationship(
                dept_name,
                back_populates="department_leader_rels",
                foreign_keys=f"[{rel_name}.dept_id]",
            )
        
        # DepartmentLeader.employee -> Employee
        if not hasattr(dept_leader_model, 'employee') or dept_leader_model.employee is None:
            dept_leader_model.employee = relationship(
                emp_name,
                back_populates="department_leader_rels",
                foreign_keys=f"[{rel_name}.employee_id]",
            )


__all__ = [
    "setup_org_relationships",
    "DEFAULT_CASCADE_CONFIG",
]
