"""
组织管理模块 - 员工服务

提供员工（Employee）聚合的业务逻辑，包括：
- 员工的增删改查
- 员工-组织关联管理
- 员工-部门关联管理
- 主组织/主部门设置

设计原则：
- 关联操作归属于"主动方"（员工）聚合
- 统一管理所有员工相关的操作和关联关系
"""

from datetime import datetime
from typing import Type, Optional, List

from yweb.orm import BaseModel
from ..enums import EmployeeStatus


class BaseEmployeeService:
    """员工服务基类
    
    提供员工的增删改查、组织/部门关联管理。
    
    使用示例:
        from yweb.organization import BaseEmployeeService
        from .models import (
            Employee, Department,
            EmployeeOrgRel, EmployeeDeptRel, DepartmentLeader
        )
        
        class EmployeeService(BaseEmployeeService):
            employee_model = Employee
            dept_model = Department
            emp_org_rel_model = EmployeeOrgRel
            emp_dept_rel_model = EmployeeDeptRel
            dept_leader_model = DepartmentLeader
    """
    
    # 模型类配置（子类必须设置）
    employee_model: Type[BaseModel] = None
    dept_model: Type[BaseModel] = None
    emp_org_rel_model: Type[BaseModel] = None
    emp_dept_rel_model: Type[BaseModel] = None
    dept_leader_model: Type[BaseModel] = None
    
    def __init__(self):
        """初始化服务"""
        if self.employee_model is None:
            raise ValueError("请在子类中配置 employee_model")
    
    # ==================== 员工 CRUD ====================
    
    def create_employee(self, name: str, **kwargs) -> BaseModel:
        """创建员工
        
        Args:
            name: 姓名
            **kwargs: 其他字段
            
        Returns:
            创建的员工对象
        """
        employee = self.employee_model(name=name, **kwargs)
        employee.save(commit=True)
        return employee
    
    def update_employee(self, employee_id: int, **kwargs) -> BaseModel:
        """更新员工
        
        Args:
            employee_id: 员工ID
            **kwargs: 要更新的字段
            
        Returns:
            更新后的员工对象
            
        Raises:
            ValueError: 如果员工不存在
        """
        employee = self.employee_model.get(employee_id)
        if employee is None:
            raise ValueError(f"员工不存在: {employee_id}")
        
        employee.update_properties(**kwargs)
        employee.save(commit=True)
        return employee
    
    def delete_employee(self, employee_id: int):
        """删除员工
        
        框架会自动处理级联删除：
        - 员工-组织关联（DELETE）
        - 员工-部门关联（DELETE）
        - 负责人关联（DELETE）
        - 主负责人引用（SET_NULL）
        
        联动：同时禁用关联的用户账号（仅影响绑定了员工的账号）。
        
        Args:
            employee_id: 员工ID
            
        Raises:
            ValueError: 如果员工不存在
        """
        employee = self.employee_model.get(employee_id)
        if employee is None:
            raise ValueError(f"员工不存在: {employee_id}")
        
        # 删除前禁用关联账号（独立用户账号不受影响）
        self._disable_linked_account(employee)
        
        # 框架的级联软删除会自动清理关联数据
        employee.delete(commit=True)
    
    def get_employee(self, employee_id: int) -> Optional[BaseModel]:
        """获取员工"""
        return self.employee_model.get(employee_id)
    
    def get_employee_by_code(self, code: str) -> Optional[BaseModel]:
        """根据编码获取员工"""
        if not hasattr(self.employee_model, 'code'):
            return None
        return self.employee_model.query.filter(
            self.employee_model.code == code
        ).first()
    
    def list_employees(
        self,
        keyword: str = None,
        page: int = 1,
        page_size: int = 20
    ):
        """获取员工列表
        
        Args:
            keyword: 搜索关键字（姓名）
            page: 页码
            page_size: 每页数量
            
        Returns:
            分页结果
        """
        query = self.employee_model.query
        
        if keyword:
            query = query.filter(self.employee_model.name.contains(keyword))
        
        return query.order_by(self.employee_model.id).paginate(
            page=page, page_size=page_size
        )
    
    # ==================== 员工-组织关联 ====================
    
    def add_to_org(
        self,
        employee_id: int,
        org_id: int,
        emp_no: Optional[str] = None,
        position: Optional[str] = None,
        status: int = EmployeeStatus.ACTIVE,
        set_as_primary: bool = False,
        **kwargs
    ) -> BaseModel:
        """添加员工到组织
        
        Args:
            employee_id: 员工ID
            org_id: 组织ID
            emp_no: 工号
            position: 职位
            status: 员工状态
            set_as_primary: 是否设为主组织
            **kwargs: 其他字段
            
        Returns:
            员工-组织关联对象
            
        Raises:
            ValueError: 如果员工已在该组织中
        """
        if self.emp_org_rel_model is None:
            raise ValueError("未配置 emp_org_rel_model")
        
        if self._exists_emp_org_rel(employee_id, org_id):
            raise ValueError("员工已在该组织中")
        
        rel = self.emp_org_rel_model(
            employee_id=employee_id,
            org_id=org_id,
            emp_no=emp_no,
            position=position,
            status=status,
            joined_at=datetime.now(),
            **kwargs
        )
        rel.save(commit=True)
        
        if set_as_primary:
            self.set_primary_org(employee_id, org_id)
        
        return rel
    
    def remove_from_org(self, employee_id: int, org_id: int):
        """从组织中移除员工
        
        同时移除该员工在该组织下所有部门的关联。
        """
        if self.emp_org_rel_model is None:
            return
        
        employee = self.employee_model.get(employee_id)
        if employee is None:
            raise ValueError(f"员工不存在: {employee_id}")
        
        # 检查是否需要清空主组织（在删除前检查）
        need_clear_primary = employee.primary_org_id == org_id
        
        # 获取该组织下的所有部门ID
        if self.dept_model:
            dept_ids = [
                d.id for d in self.dept_model.query.filter(
                    self.dept_model.org_id == org_id
                ).all()
            ]
            
            # 移除员工-部门关联
            if dept_ids and self.emp_dept_rel_model:
                self.emp_dept_rel_model.query.filter(
                    self.emp_dept_rel_model.employee_id == employee_id,
                    self.emp_dept_rel_model.dept_id.in_(dept_ids)
                ).delete(synchronize_session=False)
                
                # 移除负责人关联
                if self.dept_leader_model:
                    self.dept_leader_model.query.filter(
                        self.dept_leader_model.employee_id == employee_id,
                        self.dept_leader_model.dept_id.in_(dept_ids)
                    ).delete(synchronize_session=False)
                    
                    # 清理主负责人引用
                    self.dept_model.query.filter(
                        self.dept_model.id.in_(dept_ids),
                        self.dept_model.primary_leader_id == employee_id
                    ).update({self.dept_model.primary_leader_id: None}, synchronize_session=False)
        
        # 移除员工-组织关联
        self.emp_org_rel_model.query.filter(
            self.emp_org_rel_model.employee_id == employee_id,
            self.emp_org_rel_model.org_id == org_id
        ).delete()
        
        # 提交事务前，先 expire 关联集合避免引用已删除对象
        expire_attrs = [
            attr for attr in ['employee_org_rels', 'employee_dept_rels', 'department_leader_rels']
            if hasattr(employee, attr)
        ]
        if expire_attrs:
            employee.session.expire(employee, expire_attrs)
        
        # 如果是主组织，清空主组织和主部门
        if need_clear_primary:
            employee.primary_org_id = None
            employee.primary_dept_id = None
        
        # 通过模型实例统一提交
        employee.save(commit=True)
        
        # 移除后检查：若所有组织都不活跃了，禁用关联账号
        if not self._has_any_active_org(employee_id):
            self._disable_linked_account(employee)
    
    def get_employee_orgs(self, employee_id: int) -> List[BaseModel]:
        """获取员工所属的所有组织关联"""
        if self.emp_org_rel_model is None:
            return []
        return self.emp_org_rel_model.query.filter(
            self.emp_org_rel_model.employee_id == employee_id
        ).all()
    
    def get_org_employees(self, org_id: int) -> List[BaseModel]:
        """获取组织下的所有员工关联"""
        if self.emp_org_rel_model is None:
            return []
        return self.emp_org_rel_model.query.filter(
            self.emp_org_rel_model.org_id == org_id
        ).all()
    
    def count_employees_in_org(self, org_id: int) -> int:
        """统计组织下的员工数量"""
        if self.emp_org_rel_model is None:
            return 0
        return self.emp_org_rel_model.query.filter(
            self.emp_org_rel_model.org_id == org_id
        ).count()
    
    # ==================== 员工-部门关联 ====================
    
    def add_to_dept(
        self,
        employee_id: int,
        dept_id: int,
        set_as_primary: bool = False,
        **kwargs
    ) -> BaseModel:
        """添加员工到部门
        
        Args:
            employee_id: 员工ID
            dept_id: 部门ID
            set_as_primary: 是否设为主部门
            **kwargs: 其他字段
            
        Returns:
            员工-部门关联对象
            
        Raises:
            ValueError: 如果员工已在该部门中、部门不存在、或员工不在该部门所属组织中
        """
        if self.emp_dept_rel_model is None:
            raise ValueError("未配置 emp_dept_rel_model")
        
        if self._exists_emp_dept_rel(employee_id, dept_id):
            raise ValueError("员工已在该部门中")
        
        # 验证部门存在
        if self.dept_model:
            dept = self.dept_model.get(dept_id)
            if dept is None:
                raise ValueError(f"部门不存在: {dept_id}")
            
            # 验证员工是否在该部门所属的组织中
            if not self._exists_emp_org_rel(employee_id, dept.org_id):
                raise ValueError("员工不在该部门所属的组织中，请先添加到组织")
        
        rel = self.emp_dept_rel_model(
            employee_id=employee_id,
            dept_id=dept_id,
            joined_at=datetime.now(),
            **kwargs
        )
        rel.save(commit=True)
        
        if set_as_primary:
            self.set_primary_dept(employee_id, dept_id)
        
        return rel
    
    def remove_from_dept(self, employee_id: int, dept_id: int):
        """从部门中移除员工"""
        if self.emp_dept_rel_model is None:
            return
        
        employee = self.employee_model.get(employee_id)
        if employee is None:
            raise ValueError(f"员工不存在: {employee_id}")
        
        # 检查是否需要清空主部门（在删除前检查）
        need_clear_primary = employee.primary_dept_id == dept_id
        
        # 删除员工-部门关联
        self.emp_dept_rel_model.query.filter(
            self.emp_dept_rel_model.employee_id == employee_id,
            self.emp_dept_rel_model.dept_id == dept_id
        ).delete()
        
        # 移除负责人关联
        if self.dept_leader_model:
            self.dept_leader_model.query.filter(
                self.dept_leader_model.employee_id == employee_id,
                self.dept_leader_model.dept_id == dept_id
            ).delete()
            
            # 清理主负责人引用
            if self.dept_model:
                self.dept_model.query.filter(
                    self.dept_model.id == dept_id,
                    self.dept_model.primary_leader_id == employee_id
                ).update({self.dept_model.primary_leader_id: None})
        
        # 提交事务前，先 expire 关联集合避免引用已删除对象
        expire_attrs = [
            attr for attr in ['employee_dept_rels', 'department_leader_rels']
            if hasattr(employee, attr)
        ]
        if expire_attrs:
            employee.session.expire(employee, expire_attrs)
        
        # 如果是主部门，清空主部门
        if need_clear_primary:
            employee.primary_dept_id = None
        
        # 通过模型实例统一提交
        employee.save(commit=True)
    
    def get_employee_depts(self, employee_id: int) -> List[BaseModel]:
        """获取员工所属的所有部门关联"""
        if self.emp_dept_rel_model is None:
            return []
        return self.emp_dept_rel_model.query.filter(
            self.emp_dept_rel_model.employee_id == employee_id
        ).all()
    
    def get_dept_employees(self, dept_id: int) -> List[BaseModel]:
        """获取部门下的所有员工关联"""
        if self.emp_dept_rel_model is None:
            return []
        return self.emp_dept_rel_model.query.filter(
            self.emp_dept_rel_model.dept_id == dept_id
        ).all()
    
    def is_employee_in_dept(self, employee_id: int, dept_id: int) -> bool:
        """检查员工是否在部门中"""
        return self._exists_emp_dept_rel(employee_id, dept_id)
    
    def is_employee_in_org(self, employee_id: int, org_id: int) -> bool:
        """检查员工是否在组织中"""
        return self._exists_emp_org_rel(employee_id, org_id)
    
    # ==================== 主组织/主部门管理 ====================
    
    def set_primary_org(self, employee_id: int, org_id: int):
        """设置员工的主组织
        
        Args:
            employee_id: 员工ID
            org_id: 组织ID
            
        Raises:
            ValueError: 如果员工不存在或不在该组织中
        """
        employee = self.employee_model.get(employee_id)
        if employee is None:
            raise ValueError(f"员工不存在: {employee_id}")
        
        if not self._exists_emp_org_rel(employee_id, org_id):
            raise ValueError("员工不在该组织中，无法设为主组织")
        
        # 如果切换了主组织，清空主部门
        if employee.primary_org_id != org_id:
            employee.primary_dept_id = None
        
        employee.primary_org_id = org_id
        employee.save(commit=True)
    
    def set_primary_dept(self, employee_id: int, dept_id: int):
        """设置员工的主部门
        
        Args:
            employee_id: 员工ID
            dept_id: 部门ID
            
        Raises:
            ValueError: 如果员工或部门不存在，或员工不在该部门中
        """
        employee = self.employee_model.get(employee_id)
        if employee is None:
            raise ValueError(f"员工不存在: {employee_id}")
        
        if self.dept_model:
            dept = self.dept_model.get(dept_id)
            if dept is None:
                raise ValueError(f"部门不存在: {dept_id}")
            
            # 验证主部门必须属于主组织
            if employee.primary_org_id and dept.org_id != employee.primary_org_id:
                raise ValueError("主部门必须属于主组织")
        
        if not self._exists_emp_dept_rel(employee_id, dept_id):
            raise ValueError("员工不在该部门中，无法设为主部门")
        
        employee.primary_dept_id = dept_id
        employee.save(commit=True)
    
    # ==================== 状态管理 ====================
    
    def update_emp_org_status(self, employee_id: int, org_id: int, status: int) -> BaseModel:
        """修改员工在组织中的雇佣状态
        
        联动逻辑（仅影响绑定了员工的账号，独立用户不受影响）：
        - 改为非活跃（离职/停职）时：若该员工在所有组织中都不活跃，自动禁用账号
        - 改为活跃（待入职/试用/在职）时：不自动激活账号（需管理员手动激活）
        
        Args:
            employee_id: 员工ID
            org_id: 组织ID
            status: 新状态（EmployeeStatus 枚举值）
            
        Returns:
            更新后的员工-组织关联对象
            
        Raises:
            ValueError: 如果关联不存在或状态值无效
        """
        if self.emp_org_rel_model is None:
            raise ValueError("未配置 emp_org_rel_model")
        
        # 校验状态值
        valid_values = [s.value for s in EmployeeStatus]
        if status not in valid_values:
            raise ValueError(f"无效的状态值: {status}，有效值: {valid_values}")
        
        rel = self.emp_org_rel_model.query.filter(
            self.emp_org_rel_model.employee_id == employee_id,
            self.emp_org_rel_model.org_id == org_id
        ).first()
        
        if rel is None:
            raise ValueError("员工不在该组织中")
        
        old_status = rel.status
        rel.status = status
        rel.save(commit=True)
        
        # 联动账号：当状态为非活跃时，检查是否需要禁用账号
        if status <= 0:
            if not self._has_any_active_org(employee_id):
                employee = self.employee_model.get(employee_id)
                if employee:
                    self._disable_linked_account(employee)
        
        return rel
    
    def update_account_status(self, employee_id: int, account_status: int) -> BaseModel:
        """修改员工的账号状态（通过关联的 User.is_active）
        
        直接修改关联用户的 is_active 字段。
        激活时会校验雇佣状态：所有组织都非活跃的员工不允许激活账号。
        
        Args:
            employee_id: 员工ID
            account_status: 目标状态（1-激活，-1-禁用）
            
        Returns:
            更新后的员工对象
            
        Raises:
            ValueError: 如果员工不存在、无关联账号、状态值无效、或雇佣状态不允许
        """
        if account_status not in (1, -1):
            raise ValueError(f"无效的账号状态值: {account_status}，有效值: [1, -1]（不可手动设为'未激活'）")
        
        employee = self.employee_model.get(employee_id)
        if employee is None:
            raise ValueError(f"员工不存在: {employee_id}")
        
        if not hasattr(employee, 'user_id'):
            raise ValueError("当前未启用账号关联功能")
        
        if getattr(employee, 'user_id', None) is None:
            raise ValueError("该员工尚未创建账号，无法修改账号状态")
        
        user = getattr(employee, 'user', None)
        if user is None:
            raise ValueError("关联的用户账号不存在")
        
        # 激活时校验：雇佣状态必须有至少一个活跃组织
        if account_status == 1 and not self._has_any_active_org(employee_id):
            raise ValueError("该员工在所有组织中均为非活跃状态（离职/停职），不允许激活账号")
        
        user.is_active = (account_status == 1)
        user.save(commit=True)
        return employee
    
    # ==================== 内部方法 ====================
    
    def _has_any_active_org(self, employee_id: int) -> bool:
        """检查员工是否在任何组织中有活跃状态（status > 0）
        
        活跃状态包括：待入职(1)、试用期(2)、在职(3)
        非活跃状态包括：停职(0)、离职(-1)
        """
        if self.emp_org_rel_model is None:
            return False
        return self.emp_org_rel_model.query.filter(
            self.emp_org_rel_model.employee_id == employee_id,
            self.emp_org_rel_model.status > 0
        ).count() > 0
    
    def _disable_linked_account(self, employee) -> bool:
        """禁用员工关联的用户账号（容错：无关联时静默跳过）
        
        仅影响"绑定了员工"的账号，独立用户账号不受影响。
        
        Returns:
            True 如果实际执行了禁用，False 如果跳过
        """
        if not hasattr(employee, 'user_id'):
            return False
        user_id = getattr(employee, 'user_id', None)
        if user_id is None:
            return False
        
        # 优先通过 relationship 获取，失败则通过模型类直接查询
        user = getattr(employee, 'user', None)
        if user is None:
            try:
                user_rel = getattr(type(employee), 'user', None)
                if user_rel is not None and hasattr(user_rel, 'property'):
                    user_cls = user_rel.property.mapper.class_
                    user = user_cls.get(user_id)
            except Exception:
                pass
        if user is None:
            return False
        
        if user.is_active:
            user.is_active = False
            user.save(commit=True)
            return True
        return False
    
    def _exists_emp_org_rel(self, employee_id: int, org_id: int) -> bool:
        """检查员工-组织关联是否存在"""
        if self.emp_org_rel_model is None:
            return False
        return self.emp_org_rel_model.query.filter(
            self.emp_org_rel_model.employee_id == employee_id,
            self.emp_org_rel_model.org_id == org_id
        ).count() > 0
    
    def _exists_emp_dept_rel(self, employee_id: int, dept_id: int) -> bool:
        """检查员工-部门关联是否存在"""
        if self.emp_dept_rel_model is None:
            return False
        return self.emp_dept_rel_model.query.filter(
            self.emp_dept_rel_model.employee_id == employee_id,
            self.emp_dept_rel_model.dept_id == dept_id
        ).count() > 0


__all__ = ["BaseEmployeeService"]
