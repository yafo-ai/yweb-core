"""
组织管理模块 - 部门负责人关联抽象模型

定义部门与负责人多对多关联的抽象基类
"""

from sqlalchemy import Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, declared_attr

from yweb.orm import BaseModel


class AbstractDepartmentLeader(BaseModel):
    """部门负责人关联抽象模型
    
    记录部门的负责人信息。
    一个部门可以有多个负责人，但只有一个主负责人（通过 Department.primary_leader_id）。
    
    字段说明:
        - dept_id: 部门ID
        - employee_id: 员工ID（负责人）
        - sort_order: 排序序号
    
    唯一性约束:
        - (dept_id, employee_id) 应该唯一，由 Service 层保证
    
    主负责人说明:
        - 主负责人通过 Department.primary_leader_id 字段标识
        - 本表记录所有负责人（包括主负责人）
    
    使用示例:
        from yweb.organization import AbstractDepartmentLeader
        
        class DepartmentLeader(AbstractDepartmentLeader):
            __tablename__ = "sys_dept_leader"
            
            # 设置外键表名
            __dept_tablename__ = "sys_department"
            __employee_tablename__ = "sys_employee"
    """
    __abstract__ = True
    
    # ==================== 关联字段 ====================
    
    @declared_attr
    def dept_id(cls) -> Mapped[int]:
        """部门ID"""
        dept_tablename = getattr(cls, '__dept_tablename__', 'department')
        return mapped_column(
            Integer,
            ForeignKey(f"{dept_tablename}.id"),
            nullable=False,
            comment="部门ID"
        )
    
    @declared_attr
    def employee_id(cls) -> Mapped[int]:
        """员工ID（负责人）"""
        employee_tablename = getattr(cls, '__employee_tablename__', 'employee')
        return mapped_column(
            Integer,
            ForeignKey(f"{employee_tablename}.id"),
            nullable=False,
            comment="员工ID（负责人）"
        )
    
    # ==================== 其他属性 ====================
    
    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="排序序号"
    )
    
    # ==================== 关系定义（子类需要实现） ====================
    # department = relationship("Department", back_populates="leader_relations")
    # employee = relationship("Employee", back_populates="leader_relations")


__all__ = ["AbstractDepartmentLeader"]
