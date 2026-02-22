"""
组织管理模块 - 员工-部门关联抽象模型

定义员工与部门多对多关联的抽象基类
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, declared_attr

from yweb.orm import BaseModel


class AbstractEmployeeDeptRel(BaseModel):
    """员工-部门关联抽象模型
    
    记录员工所属的部门信息。
    一个员工可以属于多个部门。
    
    字段说明:
        - employee_id: 员工ID
        - dept_id: 部门ID
        - sort_order: 排序序号
        - joined_at: 加入部门时间
        - external_dept_id: 外部部门ID
    
    唯一性约束:
        - (employee_id, dept_id) 应该唯一，由 Service 层保证
    
    使用示例:
        from yweb.organization import AbstractEmployeeDeptRel
        
        class EmployeeDeptRel(AbstractEmployeeDeptRel):
            __tablename__ = "sys_emp_dept_rel"
            
            # 设置外键表名
            __employee_tablename__ = "sys_employee"
            __dept_tablename__ = "sys_department"
    """
    __abstract__ = True
    
    # ==================== 关联字段 ====================
    
    @declared_attr
    def employee_id(cls) -> Mapped[int]:
        """员工ID"""
        employee_tablename = getattr(cls, '__employee_tablename__', 'employee')
        return mapped_column(
            Integer,
            ForeignKey(f"{employee_tablename}.id"),
            nullable=False,
            comment="员工ID"
        )
    
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
    
    # ==================== 部门级属性 ====================
    
    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="排序序号"
    )
    
    joined_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=True,
        comment="加入部门时间"
    )
    
    # ==================== 外部系统字段 ====================
    
    external_dept_id: Mapped[str] = mapped_column(
        String(255),
        nullable=True,
        comment="外部部门ID"
    )
    
    # ==================== 关系定义（子类需要实现） ====================
    # employee = relationship("Employee", back_populates="dept_relations")
    # department = relationship("Department", back_populates="employee_relations")


__all__ = ["AbstractEmployeeDeptRel"]
