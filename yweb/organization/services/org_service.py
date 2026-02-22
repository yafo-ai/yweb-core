"""
组织管理模块 - 组织服务

提供组织（Organization）聚合的业务逻辑。

设计原则：
- 单一职责：只处理组织相关操作
- 跨聚合验证通过组合其他服务完成
"""

from typing import Type, Optional, List

from yweb.orm import BaseModel


class BaseOrganizationService:
    """组织服务基类
    
    提供组织的增删改查业务逻辑。
    
    使用示例:
        from yweb.organization import BaseOrganizationService
        from .models import Organization
        
        class OrganizationService(BaseOrganizationService):
            org_model = Organization
    """
    
    # 模型类配置（子类必须设置）
    org_model: Type[BaseModel] = None
    
    # 可选：用于跨聚合检查的服务引用
    dept_service: "BaseDepartmentService" = None
    employee_service: "BaseEmployeeService" = None
    
    def __init__(self):
        """初始化服务"""
        if self.org_model is None:
            raise ValueError("请在子类中配置 org_model")
    
    # ==================== 组织 CRUD ====================
    
    def create_org(self, name: str, code: str = None, **kwargs) -> BaseModel:
        """创建组织
        
        Args:
            name: 组织名称
            code: 组织编码
            **kwargs: 其他字段
            
        Returns:
            创建的组织对象
            
        Raises:
            ValueError: 如果编码已存在
        """
        if code:
            self.org_model.validate_code_unique(code)
        
        org = self.org_model(name=name, code=code, **kwargs)
        org.save(commit=True)
        return org
    
    def update_org(self, org_id: int, **kwargs) -> BaseModel:
        """更新组织
        
        Args:
            org_id: 组织ID
            **kwargs: 要更新的字段
            
        Returns:
            更新后的组织对象
            
        Raises:
            ValueError: 如果组织不存在或新编码已存在
        """
        org = self.org_model.get(org_id)
        if org is None:
            raise ValueError(f"组织不存在: {org_id}")
        
        # 编码变更时验证唯一性
        if 'code' in kwargs and kwargs['code'] != org.code:
            self.org_model.validate_code_unique(kwargs['code'], exclude_id=org_id)
        
        org.update_properties(**kwargs)
        org.save(commit=True)
        return org
    
    def delete_org(self, org_id: int, force: bool = False):
        """删除组织
        
        Args:
            org_id: 组织ID
            force: 是否强制删除（即使有部门/员工）
            
        Raises:
            ValueError: 如果组织不存在，或有部门/员工且未强制删除
        """
        org = self.org_model.get(org_id)
        if org is None:
            raise ValueError(f"组织不存在: {org_id}")
        
        if not force:
            # 通过服务检查关联数据
            if self.dept_service:
                dept_count = self.dept_service.count_by_org(org_id)
                if dept_count > 0:
                    raise ValueError(f"组织下有 {dept_count} 个部门，无法删除")
            
            if self.employee_service:
                emp_count = self.employee_service.count_employees_in_org(org_id)
                if emp_count > 0:
                    raise ValueError(f"组织下有 {emp_count} 名员工，无法删除")
        
        org.delete(commit=True)
    
    def get_org(self, org_id: int) -> Optional[BaseModel]:
        """获取组织"""
        return self.org_model.get(org_id)
    
    def get_org_by_code(self, code: str) -> Optional[BaseModel]:
        """根据编码获取组织"""
        return self.org_model.query.filter(
            self.org_model.code == code
        ).first()
    
    def list_orgs(self, is_active: bool = None) -> List[BaseModel]:
        """获取组织列表
        
        Args:
            is_active: 按状态筛选，None 表示全部
        """
        query = self.org_model.query
        if is_active is not None:
            query = query.filter(self.org_model.is_active == is_active)
        return query.all()
    
    # ==================== 组织-员工便捷方法 ====================
    
    def add_employee(
        self,
        org_id: int,
        employee_id: int,
        emp_no: Optional[str] = None,
        position: Optional[str] = None,
        set_as_primary: bool = False,
        **kwargs
    ) -> BaseModel:
        """将员工添加到组织
        
        Args:
            org_id: 组织ID
            employee_id: 员工ID
            emp_no: 工号
            position: 职位
            set_as_primary: 是否设为主组织
            **kwargs: 其他字段
            
        Returns:
            员工-组织关联对象
            
        Raises:
            ValueError: 如果未配置 employee_service 或员工已在组织中
        """
        if self.employee_service is None:
            raise ValueError("未配置 employee_service")
        
        return self.employee_service.add_to_org(
            employee_id=employee_id,
            org_id=org_id,
            emp_no=emp_no,
            position=position,
            set_as_primary=set_as_primary,
            **kwargs
        )
    
    def remove_employee(self, org_id: int, employee_id: int):
        """从组织中移除员工
        
        Args:
            org_id: 组织ID
            employee_id: 员工ID
        """
        if self.employee_service is None:
            raise ValueError("未配置 employee_service")
        
        self.employee_service.remove_from_org(employee_id, org_id)
    
    def get_employees(self, org_id: int) -> List[BaseModel]:
        """获取组织下的所有员工关联
        
        Args:
            org_id: 组织ID
            
        Returns:
            员工-组织关联列表
        """
        if self.employee_service is None:
            return []
        
        return self.employee_service.get_org_employees(org_id)
    
    # ==================== 组织-部门便捷方法 ====================
    
    def get_departments(self, org_id: int) -> List[BaseModel]:
        """获取组织下的所有部门
        
        Args:
            org_id: 组织ID
            
        Returns:
            部门列表（按层级排序）
        """
        if self.dept_service is None:
            return []
        
        return self.dept_service.get_dept_tree(org_id)
    
    # ==================== 部门操作便捷方法（委托给 dept_service）====================
    
    def create_dept(self, org_id: int, name: str, **kwargs) -> BaseModel:
        """创建部门（委托给 dept_service）"""
        if self.dept_service is None:
            raise ValueError("未配置 dept_service")
        return self.dept_service.create_dept(org_id=org_id, name=name, **kwargs)
    
    def update_dept(self, dept_id: int, **kwargs) -> BaseModel:
        """更新部门（委托给 dept_service）"""
        if self.dept_service is None:
            raise ValueError("未配置 dept_service")
        return self.dept_service.update_dept(dept_id=dept_id, **kwargs)
    
    def delete_dept(self, dept_id: int, force: bool = False, promote_children: bool = True) -> dict:
        """删除部门（委托给 dept_service）"""
        if self.dept_service is None:
            raise ValueError("未配置 dept_service")
        return self.dept_service.delete_dept(dept_id=dept_id, force=force, promote_children=promote_children)
    
    def move_dept(self, dept_id: int, new_parent_id: Optional[int]) -> BaseModel:
        """移动部门（委托给 dept_service）"""
        if self.dept_service is None:
            raise ValueError("未配置 dept_service")
        return self.dept_service.move_dept(dept_id=dept_id, new_parent_id=new_parent_id)
    
    def add_dept_leader(self, dept_id: int, employee_id: int, set_as_primary: bool = False) -> BaseModel:
        """添加部门负责人（委托给 dept_service）"""
        if self.dept_service is None:
            raise ValueError("未配置 dept_service")
        return self.dept_service.add_dept_leader(dept_id=dept_id, employee_id=employee_id, set_as_primary=set_as_primary)
    
    def remove_dept_leader(self, dept_id: int, employee_id: int):
        """移除部门负责人（委托给 dept_service）"""
        if self.dept_service is None:
            raise ValueError("未配置 dept_service")
        return self.dept_service.remove_dept_leader(dept_id=dept_id, employee_id=employee_id)
    
    # ==================== 员工操作便捷方法（委托给 employee_service）====================
    
    def create_employee(self, name: str, **kwargs) -> BaseModel:
        """创建员工（委托给 employee_service）"""
        if self.employee_service is None:
            raise ValueError("未配置 employee_service")
        return self.employee_service.create_employee(name=name, **kwargs)
    
    def update_employee(self, employee_id: int, **kwargs) -> BaseModel:
        """更新员工（委托给 employee_service）"""
        if self.employee_service is None:
            raise ValueError("未配置 employee_service")
        return self.employee_service.update_employee(employee_id=employee_id, **kwargs)
    
    def delete_employee(self, employee_id: int):
        """删除员工（委托给 employee_service）"""
        if self.employee_service is None:
            raise ValueError("未配置 employee_service")
        return self.employee_service.delete_employee(employee_id=employee_id)
    
    def add_employee_to_org(self, employee_id: int, org_id: int, **kwargs) -> BaseModel:
        """员工加入组织（委托给 employee_service）"""
        if self.employee_service is None:
            raise ValueError("未配置 employee_service")
        return self.employee_service.add_to_org(employee_id=employee_id, org_id=org_id, **kwargs)
    
    def remove_employee_from_org(self, employee_id: int, org_id: int):
        """员工离开组织（委托给 employee_service）"""
        if self.employee_service is None:
            raise ValueError("未配置 employee_service")
        return self.employee_service.remove_from_org(employee_id=employee_id, org_id=org_id)
    
    def set_primary_org(self, employee_id: int, org_id: int):
        """设置主组织（委托给 employee_service）"""
        if self.employee_service is None:
            raise ValueError("未配置 employee_service")
        return self.employee_service.set_primary_org(employee_id=employee_id, org_id=org_id)
    
    def add_employee_to_dept(self, employee_id: int, dept_id: int, **kwargs) -> BaseModel:
        """员工加入部门（委托给 employee_service）"""
        if self.employee_service is None:
            raise ValueError("未配置 employee_service")
        return self.employee_service.add_to_dept(employee_id=employee_id, dept_id=dept_id, **kwargs)
    
    def remove_employee_from_dept(self, employee_id: int, dept_id: int):
        """员工离开部门（委托给 employee_service）"""
        if self.employee_service is None:
            raise ValueError("未配置 employee_service")
        return self.employee_service.remove_from_dept(employee_id=employee_id, dept_id=dept_id)
    
    def set_primary_dept(self, employee_id: int, dept_id: int):
        """设置主部门（委托给 employee_service）"""
        if self.employee_service is None:
            raise ValueError("未配置 employee_service")
        return self.employee_service.set_primary_dept(employee_id=employee_id, dept_id=dept_id)
    
    def update_emp_org_status(self, employee_id: int, org_id: int, status: int) -> BaseModel:
        """修改雇佣状态（委托给 employee_service）"""
        if self.employee_service is None:
            raise ValueError("未配置 employee_service")
        return self.employee_service.update_emp_org_status(employee_id=employee_id, org_id=org_id, status=status)
    
    def update_account_status(self, employee_id: int, account_status: int) -> BaseModel:
        """修改账号状态（委托给 employee_service）"""
        if self.employee_service is None:
            raise ValueError("未配置 employee_service")
        return self.employee_service.update_account_status(employee_id=employee_id, account_status=account_status)


__all__ = ["BaseOrganizationService"]
