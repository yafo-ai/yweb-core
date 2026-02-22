"""
组织管理模块 - 员工抽象模型

定义员工（Employee）的抽象基类
"""

from typing import Optional
from sqlalchemy import String, Integer, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, declared_attr

from yweb.orm import BaseModel
from ..enums import Gender


class AbstractEmployee(BaseModel):
    """员工抽象模型
    
    员工是组织中的人员实体。一个员工可以属于多个组织和多个部门，
    但只有一个主组织和一个主部门。
    
    字段说明:
        - name: 姓名（继承自 BaseModel）
        - mobile: 手机号
        - email: 邮箱
        - avatar: 头像URL
        - gender: 性别
        - is_senior: 是否高管（可隐藏联系方式）
        - primary_org_id: 主组织ID（冗余字段，方便查询）
        - primary_dept_id: 主部门ID（冗余字段，方便查询）
    
    关联关系说明:
        - 员工与组织：多对多（通过 EmployeeOrgRel）
        - 员工与部门：多对多（通过 EmployeeDeptRel）
        - 员工的具体属性（工号、职位等）在关联表中
    
    账号状态说明:
        账号状态（account_status）不再存储在员工表中，而是通过关联的
        User 模型动态推导：
        - user_id IS NULL → 未激活（0）
        - user.is_active == True → 已激活（1）
        - user.is_active == False → 已禁用（-1）
        这需要通过 employee_mixin 添加 user 关联（如 EmployeeUserMixin）。
        未配置 Mixin 时，不提供账号状态功能。
    
    使用示例:
        from yweb.organization import AbstractEmployee
        
        class Employee(AbstractEmployee):
            __tablename__ = "sys_employee"
            
            # 可添加自定义字段
            id_card = mapped_column(String(18), comment="身份证号")
    
    注意:
        应用层需要自行定义 primary_org_id 和 primary_dept_id 的外键关系。
    """
    __abstract__ = True
    
    # ==================== 基础字段 ====================
    # name, code, note, caption 继承自 BaseModel
    # 对于员工，name 用作姓名
    
    mobile: Mapped[str] = mapped_column(
        String(20),
        nullable=True,
        comment="手机号"
    )
    
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=True,
        comment="邮箱"
    )
    
    avatar: Mapped[str] = mapped_column(
        String(500),
        nullable=True,
        comment="头像URL"
    )
    
    gender: Mapped[int] = mapped_column(
        Integer,
        default=Gender.UNKNOWN.value,
        comment="性别（0-未知，1-男，2-女）"
    )
    
    is_senior: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="是否高管（可隐藏联系方式）"
    )
    
    # ==================== 主归属（冗余字段） ====================
    
    @declared_attr
    def primary_org_id(cls) -> Mapped[Optional[int]]:
        """主组织ID
        
        子类可以通过设置 __org_tablename__ 来指定组织表名，
        或者直接在子类中重新定义此字段。
        """
        org_tablename = getattr(cls, '__org_tablename__', 'organization')
        return mapped_column(
            Integer,
            ForeignKey(f"{org_tablename}.id"),
            nullable=True,
            comment="主组织ID"
        )
    
    @declared_attr
    def primary_dept_id(cls) -> Mapped[Optional[int]]:
        """主部门ID
        
        子类可以通过设置 __dept_tablename__ 来指定部门表名，
        或者直接在子类中重新定义此字段。
        """
        dept_tablename = getattr(cls, '__dept_tablename__', 'department')
        return mapped_column(
            Integer,
            ForeignKey(f"{dept_tablename}.id"),
            nullable=True,
            comment="主部门ID"
        )
    
    # ==================== 关系定义（子类需要实现） ====================
    # 以下关系需要在子类中定义，因为具体的模型类在应用层
    
    # primary_org = relationship("Organization", foreign_keys=[primary_org_id])
    # primary_dept = relationship("Department", foreign_keys=[primary_dept_id])
    # organizations = relationship("Organization", secondary="emp_org_rel", back_populates="employees")
    # departments = relationship("Department", secondary="emp_dept_rel", back_populates="employees")
    # leading_departments = relationship("Department", secondary="dept_leader", back_populates="leaders")
    
    # ==================== 便捷方法 ====================
    
    def get_account_status(self) -> int:
        """获取账号状态（从关联的 User 模型推导）
        
        Returns:
            0: 未激活（无关联用户）
            1: 已激活（用户 is_active=True）
            -1: 已禁用（用户 is_active=False）
            None: 未配置用户关联
        """
        if not hasattr(self, 'user_id'):
            return None
        if getattr(self, 'user_id', None) is None:
            return 0   # 未激活
        user = getattr(self, 'user', None)
        if user and getattr(user, 'is_active', False):
            return 1   # 已激活
        return -1       # 已禁用
    
    def get_account_status_display(self) -> str:
        """获取账号状态显示文本"""
        status_map = {-1: "已禁用", 0: "未激活", 1: "已激活"}
        status = self.get_account_status()
        if status is None:
            return "未配置"
        return status_map.get(status, "未知")
    
    def is_male(self) -> bool:
        """判断是否为男性"""
        return self.gender == Gender.MALE.value
    
    def is_female(self) -> bool:
        """判断是否为女性"""
        return self.gender == Gender.FEMALE.value
    
    def get_gender_display(self) -> str:
        """获取性别显示文本"""
        gender_map = {
            Gender.UNKNOWN.value: "未知",
            Gender.MALE.value: "男",
            Gender.FEMALE.value: "女",
        }
        return gender_map.get(self.gender, "未知")


__all__ = ["AbstractEmployee"]
