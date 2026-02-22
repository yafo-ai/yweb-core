"""
组织管理模块 - 部门服务

提供部门（Department）聚合的业务逻辑，包括部门负责人管理。

设计原则：
- 部门负责人依附于部门存在，归属本服务
- 跨聚合验证通过组合其他服务完成
"""

from typing import Type, Optional, List, Any, Dict

from yweb.orm import BaseModel


class BaseDepartmentService:
    """部门服务基类
    
    提供部门的增删改查、树形操作、负责人管理。
    
    使用示例:
        from yweb.organization import BaseDepartmentService
        from .models import Department, DepartmentLeader
        
        class DepartmentService(BaseDepartmentService):
            dept_model = Department
            dept_leader_model = DepartmentLeader
    """
    
    # 模型类配置（子类必须设置）
    dept_model: Type[BaseModel] = None
    dept_leader_model: Type[BaseModel] = None
    
    # 可选：用于跨聚合检查的服务引用
    org_service: "BaseOrganizationService" = None
    employee_service: "BaseEmployeeService" = None
    
    def __init__(self):
        """初始化服务"""
        if self.dept_model is None:
            raise ValueError("请在子类中配置 dept_model")
    
    # ==================== 部门 CRUD ====================
    
    def create_dept(
        self,
        org_id: int,
        name: str,
        parent_id: Optional[int] = None,
        code: Optional[str] = None,
        **kwargs
    ) -> BaseModel:
        """创建部门
        
        Args:
            org_id: 所属组织ID
            name: 部门名称
            parent_id: 父部门ID（为空表示根部门）
            code: 部门编码
            **kwargs: 其他字段
            
        Returns:
            创建的部门对象
            
        Raises:
            ValueError: 如果组织不存在、父部门无效、编码已存在
        """
        # 跨聚合验证：检查组织存在
        if self.org_service:
            org = self.org_service.get_org(org_id)
            if not org:
                raise ValueError(f"组织不存在: {org_id}")
        
        # 领域模型验证
        if code:
            self.dept_model.validate_code_unique(org_id=org_id, code=code)
        
        level = 1
        if parent_id is not None:
            parent = self.dept_model.validate_parent(parent_id=parent_id, org_id=org_id)
            level = parent.level + 1
        
        dept = self.dept_model(
            org_id=org_id,
            name=name,
            code=code,
            parent_id=parent_id,
            level=level,
            **kwargs
        )
        
        # 先保存获取ID，再更新路径，最后统一提交
        dept.save()
        dept.update_path_and_level()
        dept.save(commit=True)
        
        return dept
    
    def update_dept(self, dept_id: int, **kwargs) -> BaseModel:
        """更新部门
        
        Args:
            dept_id: 部门ID
            **kwargs: 要更新的字段
            
        Returns:
            更新后的部门对象
            
        Raises:
            ValueError: 如果部门不存在或新编码已存在
        """
        dept = self.dept_model.get(dept_id)
        if dept is None:
            raise ValueError(f"部门不存在: {dept_id}")
        
        # 编码变更时验证唯一性
        if 'code' in kwargs and kwargs['code'] != dept.code:
            self.dept_model.validate_code_unique(
                org_id=dept.org_id,
                code=kwargs['code'],
                exclude_id=dept_id
            )
        
        # 父部门变更使用移动方法
        if 'parent_id' in kwargs:
            new_parent_id = kwargs.pop('parent_id')
            dept.move_to_parent(new_parent_id)
        
        dept.update_properties(**kwargs)
        dept.save(commit=True)
        return dept
    
    def delete_dept(
        self,
        dept_id: int,
        force: bool = False,
        promote_children: bool = True
    ) -> Dict[str, Any]:
        """删除部门
        
        Args:
            dept_id: 部门ID
            force: 是否强制删除（即使有员工/子部门）
            promote_children: 强制删除时是否将子部门提升到父级
            
        Returns:
            包含删除信息的字典 {"promoted_children": [...], "employee_count": n}
            
        Raises:
            ValueError: 如果部门不存在，或有子部门/员工且非强制删除
        """
        dept = self.dept_model.get(dept_id)
        if dept is None:
            raise ValueError(f"部门不存在: {dept_id}")
        
        # 调用领域模型验证
        result = dept.validate_can_delete(force=force)
        
        promoted_children = []
        
        # 强制删除时，将子部门提升到父级
        if force and result["children"] and promote_children:
            promoted_children = dept.promote_children_to_parent()
            for child in promoted_children:
                child.save(commit=True)
        
        dept.delete(commit=True)
        
        return {
            "promoted_children": [c.id for c in promoted_children],
            "employee_count": result["employee_count"]
        }
    
    def get_dept(self, dept_id: int) -> Optional[BaseModel]:
        """获取部门"""
        return self.dept_model.get(dept_id)
    
    def get_dept_by_code(self, org_id: int, code: str) -> Optional[BaseModel]:
        """根据编码获取部门"""
        return self.dept_model.query.filter(
            self.dept_model.org_id == org_id,
            self.dept_model.code == code
        ).first()
    
    # ==================== 树形操作 ====================
    
    def get_dept_tree(self, org_id: int) -> List[BaseModel]:
        """获取组织的部门列表（按层级排序）
        
        Args:
            org_id: 组织ID
            
        Returns:
            按层级和排序返回的部门列表
        """
        return self.dept_model.query.filter(
            self.dept_model.org_id == org_id
        ).order_by(
            self.dept_model.level,
            self.dept_model.sort_order
        ).all()
    
    def get_root_depts(self, org_id: int) -> List[BaseModel]:
        """获取组织的根部门"""
        return self.dept_model.query.filter(
            self.dept_model.org_id == org_id,
            self.dept_model.parent_id.is_(None)
        ).order_by(self.dept_model.sort_order).all()
    
    def move_dept(self, dept_id: int, new_parent_id: Optional[int]) -> BaseModel:
        """移动部门
        
        Args:
            dept_id: 部门ID
            new_parent_id: 新父部门ID，None 表示移到根级
            
        Returns:
            移动后的部门对象
            
        Raises:
            ValueError: 如果部门不存在，或会导致循环引用、跨组织移动
        """
        dept = self.dept_model.get(dept_id)
        if dept is None:
            raise ValueError(f"部门不存在: {dept_id}")
        
        # 调用领域模型的移动方法
        dept.move_to_parent(new_parent_id)
        
        # 保存所有变更
        for descendant in dept.get_descendants():
            descendant.save()
        # 最后提交
        dept.save(commit=True)
        
        return dept
    
    def count_by_org(self, org_id: int) -> int:
        """统计组织下的部门数量"""
        return self.dept_model.query.filter(
            self.dept_model.org_id == org_id
        ).count()
    
    # ==================== 部门负责人管理 ====================
    
    def add_dept_leader(
        self,
        dept_id: int,
        employee_id: int,
        set_as_primary: bool = False,
        **kwargs
    ) -> BaseModel:
        """添加部门负责人
        
        Args:
            dept_id: 部门ID
            employee_id: 员工ID
            set_as_primary: 是否设为主负责人
            **kwargs: 其他字段
            
        Returns:
            部门负责人关联对象
            
        Raises:
            ValueError: 如果该员工已是负责人或不在该部门中
        """
        if self.dept_leader_model is None:
            raise ValueError("未配置 dept_leader_model")
        
        # 检查是否已是负责人
        if self._exists_dept_leader(dept_id, employee_id):
            raise ValueError("该员工已是部门负责人")
        
        # 跨聚合验证：检查员工是否在该部门中
        if self.employee_service:
            if not self.employee_service.is_employee_in_dept(employee_id, dept_id):
                raise ValueError("员工不在该部门中，无法设为负责人")
        
        leader = self.dept_leader_model(
            dept_id=dept_id,
            employee_id=employee_id,
            **kwargs
        )
        leader.save(commit=True)
        
        if set_as_primary:
            self.set_primary_leader(dept_id, employee_id)
        
        return leader
    
    def remove_dept_leader(self, dept_id: int, employee_id: int):
        """移除部门负责人"""
        if self.dept_leader_model is None:
            raise ValueError("未配置 dept_leader_model")

        dept = self.dept_model.get(dept_id)
        if dept is None:
            raise ValueError(f"部门不存在: {dept_id}")

        self.dept_leader_model.query.filter(
            self.dept_leader_model.dept_id == dept_id,
            self.dept_leader_model.employee_id == employee_id
        ).delete()

        # expire 关联集合避免引用已删除对象
        expire_attrs = [
            attr for attr in ['department_leader_rels']
            if hasattr(dept, attr)
        ]
        if expire_attrs:
            dept.session.expire(dept, expire_attrs)

        # 清理主负责人引用
        if dept.primary_leader_id == employee_id:
            dept.primary_leader_id = None

        # 通过模型实例提交
        dept.save(commit=True)
    
    def set_primary_leader(self, dept_id: int, employee_id: int):
        """设置部门主负责人
        
        Args:
            dept_id: 部门ID
            employee_id: 员工ID
            
        Raises:
            ValueError: 如果该员工不是部门负责人或部门不存在
        """
        if not self._exists_dept_leader(dept_id, employee_id):
            raise ValueError("该员工不是部门负责人，请先添加为负责人")
        
        dept = self.dept_model.get(dept_id)
        if dept is None:
            raise ValueError(f"部门不存在: {dept_id}")
        
        dept.primary_leader_id = employee_id
        dept.save(commit=True)
    
    def get_dept_leaders(self, dept_id: int) -> List[BaseModel]:
        """获取部门的所有负责人"""
        if self.dept_leader_model is None:
            return []
        
        return self.dept_leader_model.query.filter(
            self.dept_leader_model.dept_id == dept_id
        ).order_by(self.dept_leader_model.sort_order).all()
    
    def _exists_dept_leader(self, dept_id: int, employee_id: int) -> bool:
        """检查部门负责人关联是否存在"""
        if self.dept_leader_model is None:
            return False
        
        return self.dept_leader_model.query.filter(
            self.dept_leader_model.dept_id == dept_id,
            self.dept_leader_model.employee_id == employee_id
        ).count() > 0
    
    # ==================== 部门-员工便捷方法 ====================
    
    def add_employee(
        self,
        dept_id: int,
        employee_id: int,
        set_as_primary: bool = False,
        **kwargs
    ) -> BaseModel:
        """将员工添加到部门
        
        Args:
            dept_id: 部门ID
            employee_id: 员工ID
            set_as_primary: 是否设为主部门
            **kwargs: 其他字段
            
        Returns:
            员工-部门关联对象
            
        Raises:
            ValueError: 如果未配置 employee_service 或员工已在部门中
        """
        if self.employee_service is None:
            raise ValueError("未配置 employee_service")
        
        return self.employee_service.add_to_dept(
            employee_id=employee_id,
            dept_id=dept_id,
            set_as_primary=set_as_primary,
            **kwargs
        )
    
    def remove_employee(self, dept_id: int, employee_id: int):
        """从部门中移除员工
        
        Args:
            dept_id: 部门ID
            employee_id: 员工ID
        """
        if self.employee_service is None:
            raise ValueError("未配置 employee_service")
        
        self.employee_service.remove_from_dept(employee_id, dept_id)
    
    def get_employees(self, dept_id: int) -> List[BaseModel]:
        """获取部门下的所有员工关联
        
        Args:
            dept_id: 部门ID
            
        Returns:
            员工-部门关联列表
        """
        if self.employee_service is None:
            return []
        
        return self.employee_service.get_dept_employees(dept_id)


__all__ = ["BaseDepartmentService"]
