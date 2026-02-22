"""
权限模块 - 角色服务

提供角色管理的业务逻辑。

使用示例:
    from yweb.permission import RoleService
    
    role_service = RoleService(
        role_model=Role,
        permission_model=Permission,
        role_permission_model=RolePermission,
        subject_role_model=SubjectRole,
    )
    
    # 创建角色
    role = role_service.create_role("admin", "管理员")
    
    # 设置角色权限
    role_service.set_role_permissions("admin", ["user:read", "user:write"])
"""

from typing import Set, List, Optional, Type, TYPE_CHECKING

from ..cache import permission_cache
from ..types import RoleCode, PermissionCode
from ..exceptions import (
    RoleNotFoundException,
    PermissionNotFoundException,
    DuplicateRoleException,
    RoleInheritanceCycleException,
    SystemRoleModifyException,
)
from yweb.log import get_logger

if TYPE_CHECKING:
    from ..models import (
        AbstractRole,
        AbstractPermission,
        AbstractRolePermission,
        AbstractSubjectRole,
    )

logger = get_logger("yweb.permission.role_service")


class RoleService:
    """角色服务
    
    提供角色 CRUD 和权限分配功能：
    - 角色创建、更新、删除
    - 角色权限设置
    - 角色继承管理
    
    使用示例:
        role_service = RoleService(
            role_model=Role,
            permission_model=Permission,
            role_permission_model=RolePermission,
            subject_role_model=SubjectRole,
        )
        
        # 创建角色层级
        admin = role_service.create_role("admin", "管理员")
        manager = role_service.create_role("manager", "经理", parent_code="admin")
        
        # 设置角色权限
        role_service.set_role_permissions("admin", ["user:*", "system:*"])
        role_service.set_role_permissions("manager", ["user:read", "user:update"])
    """
    
    def __init__(
        self,
        role_model: Type["AbstractRole"],
        permission_model: Type["AbstractPermission"],
        role_permission_model: Type["AbstractRolePermission"],
        subject_role_model: Type["AbstractSubjectRole"],
        use_cache: bool = True
    ):
        """初始化角色服务
        
        Args:
            role_model: 角色模型类
            permission_model: 权限模型类
            role_permission_model: 角色-权限关联模型类
            subject_role_model: 主体-角色关联模型类
            use_cache: 是否使用缓存
        """
        self._role_model = role_model
        self._permission_model = permission_model
        self._role_permission_model = role_permission_model
        self._subject_role_model = subject_role_model
        self._use_cache = use_cache
    
    # ==================== 角色 CRUD ====================
    
    def create_role(
        self,
        code: str,
        name: str,
        description: Optional[str] = None,
        parent_code: Optional[str] = None,
        is_system: bool = False
    ) -> "AbstractRole":
        """创建角色
        
        Args:
            code: 角色编码
            name: 角色名称
            description: 描述
            parent_code: 父角色编码（用于继承）
            is_system: 是否系统内置
            
        Returns:
            创建的角色对象
            
        Raises:
            DuplicateRoleException: 角色编码已存在
            RoleNotFoundException: 父角色不存在
        """
        # 检查是否存在
        existing = self._role_model.get_by_code(code)
        if existing:
            raise DuplicateRoleException(code)
        
        # 处理父角色
        parent_id = None
        if parent_code:
            parent = self._role_model.get_by_code(parent_code)
            if not parent:
                raise RoleNotFoundException(parent_code)
            parent_id = parent.id
        
        role = self._role_model(
            code=code,
            name=name,
            description=description,
            parent_id=parent_id,
            is_system=is_system
        )
        role.save(commit=True)
        
        # 更新路径和层级
        if hasattr(role, 'update_path_and_level'):
            role.update_path_and_level()
        
        logger.info(f"Role created: {code}")
        return role
    
    def get_role(self, code: str) -> Optional["AbstractRole"]:
        """获取角色"""
        return self._role_model.get_by_code(code)
    
    def get_all_roles(self, include_inactive: bool = False) -> List["AbstractRole"]:
        """获取所有角色"""
        if include_inactive:
            return self._role_model.query.order_by(
                self._role_model.level,
                self._role_model.sort_order
            ).all()
        return self._role_model.get_active_roles()
    
    def get_role_tree(self) -> List["AbstractRole"]:
        """获取角色树（根角色列表）"""
        return self._role_model.get_root_roles()
    
    def update_role(
        self,
        code: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None,
        parent_code: Optional[str] = None
    ) -> "AbstractRole":
        """更新角色
        
        Args:
            code: 角色编码
            name: 新名称
            description: 新描述
            is_active: 是否启用
            parent_code: 新父角色编码（空字符串表示移除父角色）
            
        Returns:
            更新后的角色对象
        """
        role = self._role_model.get_by_code(code)
        if not role:
            raise RoleNotFoundException(code)
        
        if role.is_system and (is_active is not None and not is_active):
            raise SystemRoleModifyException(code, "禁用")
        
        if name is not None:
            role.name = name
        if description is not None:
            role.description = description
        if is_active is not None:
            role.is_active = is_active
        
        # 更新父角色
        if parent_code is not None:
            if parent_code == "":
                # 移除父角色
                role.parent_id = None
            else:
                parent = self._role_model.get_by_code(parent_code)
                if not parent:
                    raise RoleNotFoundException(parent_code)
                
                # 检查循环
                if self._would_create_cycle(role, parent):
                    raise RoleInheritanceCycleException(code, parent_code)
                
                role.parent_id = parent.id
            
            # 更新路径
            if hasattr(role, 'update_path_and_level'):
                role.update_path_and_level()
        
        role.save(commit=True)
        
        # 失效缓存
        if self._use_cache and is_active is not None:
            permission_cache.invalidate_all()
        
        logger.info(f"Role updated: {code}")
        return role
    
    def _would_create_cycle(self, role: "AbstractRole", new_parent: "AbstractRole") -> bool:
        """检查设置父角色是否会产生循环"""
        if role.id == new_parent.id:
            return True
        
        # 检查 new_parent 的祖先中是否包含 role
        ancestors = new_parent.get_ancestors()
        return any(a.id == role.id for a in ancestors)
    
    def delete_role(self, code: str, force: bool = False) -> bool:
        """删除角色
        
        Args:
            code: 角色编码
            force: 是否强制删除系统角色
            
        Returns:
            是否成功
        """
        role = self._role_model.get_by_code(code)
        if not role:
            return False
        
        if role.is_system and not force:
            raise SystemRoleModifyException(code, "删除")
        
        # 检查是否有子角色
        children = role.get_children()
        if children:
            # 将子角色的父角色设为当前角色的父角色
            for child in children:
                child.parent_id = role.parent_id
                child.save(commit=True)
                if hasattr(child, 'update_path_and_level'):
                    child.update_path_and_level()
        
        role.delete(commit=True)
        
        # 失效缓存
        if self._use_cache:
            permission_cache.invalidate_all()
        
        logger.info(f"Role deleted: {code}")
        return True
    
    # ==================== 角色权限管理 ====================
    
    def get_role_permissions(self, role_code: RoleCode) -> Set[PermissionCode]:
        """获取角色的权限编码（不含继承）
        
        Args:
            role_code: 角色编码
            
        Returns:
            权限编码集合
        """
        role = self._role_model.get_by_code(role_code)
        if not role:
            raise RoleNotFoundException(role_code)
        
        perm_ids = self._role_permission_model.get_role_permission_ids(role.id)
        permissions = set()
        
        for perm_id in perm_ids:
            perm = self._permission_model.get(perm_id)
            if perm and perm.is_active:
                permissions.add(perm.code)
        
        return permissions
    
    def get_role_all_permissions(self, role_code: RoleCode) -> Set[PermissionCode]:
        """获取角色的所有权限（含继承）
        
        Args:
            role_code: 角色编码
            
        Returns:
            权限编码集合
        """
        role = self._role_model.get_by_code(role_code)
        if not role:
            raise RoleNotFoundException(role_code)
        
        permissions = self.get_role_permissions(role_code)
        
        # 添加继承的权限
        ancestors = role.get_ancestors()
        for ancestor in ancestors:
            if ancestor.is_active:
                ancestor_perms = self.get_role_permissions(ancestor.code)
                permissions.update(ancestor_perms)
        
        return permissions
    
    def set_role_permissions(
        self,
        role_code: RoleCode,
        permission_codes: List[PermissionCode]
    ):
        """设置角色的权限（全量覆盖）
        
        Args:
            role_code: 角色编码
            permission_codes: 权限编码列表
        """
        role = self._role_model.get_by_code(role_code)
        if not role:
            raise RoleNotFoundException(role_code)
        
        # 验证权限存在性并获取ID
        permission_ids = []
        for code in permission_codes:
            perm = self._permission_model.get_by_code(code)
            if not perm:
                raise PermissionNotFoundException(code)
            permission_ids.append(perm.id)
        
        # 设置权限
        self._role_permission_model.set_role_permissions(role.id, permission_ids)
        
        # 失效缓存
        if self._use_cache:
            permission_cache.invalidate_role(role_code)
            # 需要失效所有拥有该角色的用户缓存
            self._invalidate_role_subjects(role.id)
        
        logger.info(f"Role permissions set: {role_code} <- {permission_codes}")
    
    def add_role_permission(
        self,
        role_code: RoleCode,
        permission_code: PermissionCode
    ) -> bool:
        """给角色添加权限
        
        Args:
            role_code: 角色编码
            permission_code: 权限编码
            
        Returns:
            是否成功（已存在返回 False）
        """
        role = self._role_model.get_by_code(role_code)
        if not role:
            raise RoleNotFoundException(role_code)
        
        perm = self._permission_model.get_by_code(permission_code)
        if not perm:
            raise PermissionNotFoundException(permission_code)
        
        result = self._role_permission_model.add_role_permission(role.id, perm.id)
        
        if result and self._use_cache:
            permission_cache.invalidate_role(role_code)
            self._invalidate_role_subjects(role.id)
        
        if result:
            logger.info(f"Permission added to role: {role_code} <- {permission_code}")
        
        return result
    
    def remove_role_permission(
        self,
        role_code: RoleCode,
        permission_code: PermissionCode
    ) -> bool:
        """移除角色的权限
        
        Args:
            role_code: 角色编码
            permission_code: 权限编码
            
        Returns:
            是否成功
        """
        role = self._role_model.get_by_code(role_code)
        if not role:
            raise RoleNotFoundException(role_code)
        
        perm = self._permission_model.get_by_code(permission_code)
        if not perm:
            return False
        
        result = self._role_permission_model.remove_role_permission(role.id, perm.id)
        
        if result and self._use_cache:
            permission_cache.invalidate_role(role_code)
            self._invalidate_role_subjects(role.id)
        
        if result:
            logger.info(f"Permission removed from role: {role_code} <- {permission_code}")
        
        return result
    
    def _invalidate_role_subjects(self, role_id: int):
        """失效拥有指定角色的所有用户的缓存"""
        subject_roles = self._subject_role_model.get_role_subjects(role_id)
        subject_ids = [
            f"{sr.subject_type}:{sr.subject_id}"
            for sr in subject_roles
        ]
        if subject_ids:
            permission_cache.invalidate_subjects_batch(subject_ids)
    
    # ==================== 角色用户管理 ====================
    
    def get_role_subjects(
        self,
        role_code: RoleCode,
        subject_type: Optional[str] = None
    ) -> List[dict]:
        """获取拥有指定角色的所有用户
        
        Args:
            role_code: 角色编码
            subject_type: 可选，筛选用户类型
            
        Returns:
            用户信息列表 [{"subject_type": "employee", "subject_id": 123}, ...]
        """
        role = self._role_model.get_by_code(role_code)
        if not role:
            raise RoleNotFoundException(role_code)
        
        subject_roles = self._subject_role_model.get_role_subjects(
            role_id=role.id,
            subject_type=subject_type
        )
        
        return [
            {
                "subject_type": sr.subject_type,
                "subject_id": sr.subject_id,
                "granted_at": sr.granted_at,
                "expires_at": sr.expires_at,
            }
            for sr in subject_roles
        ]


__all__ = ["RoleService"]
