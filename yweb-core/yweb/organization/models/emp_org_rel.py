"""
组织管理模块 - 员工-组织关联抽象模型

定义员工与组织多对多关联的抽象基类
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, declared_attr

from yweb.orm import BaseModel
from ..enums import EmployeeStatus


class AbstractEmployeeOrgRel(BaseModel):
    """员工-组织关联抽象模型
    
    记录员工在某个组织中的身份信息。
    一个员工可以属于多个组织，每个组织有独立的工号、职位、状态等。
    
    字段说明:
        - employee_id: 员工ID
        - org_id: 组织ID
        - emp_no: 工号（组织内唯一）
        - position: 职位
        - status: 员工状态（在职/离职/试用等）
        - joined_at: 入职日期
        - external_user_id: 外部用户ID（如企微的userid）
        - external_union_id: 跨应用用户ID（如飞书的union_id）
        - external_config: 外部系统扩展字段（JSON）
    
    唯一性约束:
        - (employee_id, org_id) 应该唯一，由 Service 层保证
    
    使用示例:
        from yweb.organization import AbstractEmployeeOrgRel
        
        class EmployeeOrgRel(AbstractEmployeeOrgRel):
            __tablename__ = "sys_emp_org_rel"
            
            # 设置外键表名
            __employee_tablename__ = "sys_employee"
            __org_tablename__ = "sys_organization"
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
    def org_id(cls) -> Mapped[int]:
        """组织ID"""
        org_tablename = getattr(cls, '__org_tablename__', 'organization')
        return mapped_column(
            Integer,
            ForeignKey(f"{org_tablename}.id"),
            nullable=False,
            comment="组织ID"
        )
    
    # ==================== 组织级属性 ====================
    
    emp_no: Mapped[str] = mapped_column(
        String(100),
        nullable=True,
        comment="工号（组织内）"
    )
    
    position: Mapped[str] = mapped_column(
        String(255),
        nullable=True,
        comment="职位"
    )
    
    status: Mapped[int] = mapped_column(
        Integer,
        default=EmployeeStatus.ACTIVE.value,
        comment="员工状态（-1-离职，0-停职，1-待入职，2-试用，3-在职）"
    )
    
    joined_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=True,
        comment="入职日期"
    )
    
    # ==================== 外部系统字段 ====================
    
    external_user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=True,
        comment="外部用户ID（如企微的userid、飞书的open_id、钉钉的userid）"
    )
    
    external_union_id: Mapped[str] = mapped_column(
        String(255),
        nullable=True,
        comment="跨应用用户ID（如飞书的union_id、钉钉的unionid）"
    )
    
    external_config: Mapped[str] = mapped_column(
        Text,
        nullable=True,
        comment="外部系统扩展字段（JSON格式）"
    )
    
    # ==================== 关系定义（子类需要实现） ====================
    # employee = relationship("Employee", back_populates="org_relations")
    # organization = relationship("Organization", back_populates="employee_relations")
    
    # ==================== 便捷方法 ====================
    
    def is_active(self) -> bool:
        """判断是否在职"""
        return self.status == EmployeeStatus.ACTIVE.value
    
    def is_resigned(self) -> bool:
        """判断是否离职"""
        return self.status == EmployeeStatus.RESIGNED.value
    
    def get_status_display(self) -> str:
        """获取状态显示文本"""
        status_map = {
            EmployeeStatus.RESIGNED.value: "离职",
            EmployeeStatus.SUSPENDED.value: "停职",
            EmployeeStatus.PENDING.value: "待入职",
            EmployeeStatus.PROBATION.value: "试用期",
            EmployeeStatus.ACTIVE.value: "在职",
        }
        return status_map.get(self.status, "未知")
    
    def get_external_config_dict(self) -> dict:
        """获取外部配置字典"""
        if not self.external_config:
            return {}
        
        import json
        try:
            return json.loads(self.external_config)
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_external_config_dict(self, config: dict):
        """设置外部配置字典"""
        import json
        self.external_config = json.dumps(config, ensure_ascii=False)


__all__ = ["AbstractEmployeeOrgRel"]
