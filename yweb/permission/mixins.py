"""
权限模块 - Mixins

提供可混入到模型类中的权限主体功能。

使用示例:
    from yweb.organization import AbstractEmployee
    from yweb.permission.mixins import SubjectMixin
    
    class Employee(AbstractEmployee, SubjectMixin):
        __tablename__ = "employee"
        __subject_type__ = "employee"  # 指定主体类型
"""

from typing import ClassVar, TYPE_CHECKING

from .enums import UserType
from .types import SubjectId

if TYPE_CHECKING:
    pass


class SubjectMixin:
    """权限主体 Mixin
    
    为模型类添加权限主体功能，使其能够直接用于权限检查。
    
    使用示例:
        from yweb.organization import AbstractEmployee
        from yweb.permission.mixins import SubjectMixin
        
        class Employee(AbstractEmployee, SubjectMixin):
            __tablename__ = "employee"
            __subject_type__ = "employee"
        
        # 使用
        emp = Employee.get(123)
        subject_id = emp.subject_id  # "employee:123"
        
        from yweb.permission import get_permission_service
        perm_service = get_permission_service()
        if perm_service.check_permission(emp.subject_id, "user:read"):
            ...
    """
    
    # 子类可以覆盖此属性来指定主体类型
    __subject_type__: ClassVar[str] = "employee"
    
    @property
    def subject_id(self) -> SubjectId:
        """获取主体唯一标识
        
        格式: "{subject_type}:{id}"
        """
        subject_type = getattr(self.__class__, '__subject_type__', 'employee')
        return f"{subject_type}:{self.id}"
    
    @property
    def subject_type(self) -> UserType:
        """获取主体类型"""
        type_str = getattr(self.__class__, '__subject_type__', 'employee')
        if type_str == 'employee':
            return UserType.EMPLOYEE
        return UserType.EXTERNAL


class EmployeeSubjectMixin(SubjectMixin):
    """员工权限主体 Mixin
    
    专门用于内部员工的权限主体 Mixin。
    
    使用示例:
        from yweb.organization import AbstractEmployee
        from yweb.permission.mixins import EmployeeSubjectMixin
        
        class Employee(AbstractEmployee, EmployeeSubjectMixin):
            __tablename__ = "employee"
    """
    __subject_type__: ClassVar[str] = "employee"
    
    @property
    def subject_type(self) -> UserType:
        return UserType.EMPLOYEE


class ExternalUserSubjectMixin(SubjectMixin):
    """外部用户权限主体 Mixin
    
    专门用于外部用户的权限主体 Mixin。
    
    使用示例:
        from yweb.auth import AbstractUser
        from yweb.permission.mixins import ExternalUserSubjectMixin
        
        class User(AbstractUser, ExternalUserSubjectMixin):
            __tablename__ = "sys_user"
        
        # User 实例自动拥有 subject_id 属性
        user = User.get(456)
        user.subject_id  # "external:456"
    """
    __subject_type__: ClassVar[str] = "external"
    
    @property
    def subject_type(self) -> UserType:
        return UserType.EXTERNAL


__all__ = [
    "SubjectMixin",
    "EmployeeSubjectMixin",
    "ExternalUserSubjectMixin",
]
