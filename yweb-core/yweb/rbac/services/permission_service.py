"""
权限模块 - 权限服务

提供权限检查、权限管理等核心业务逻辑。

使用示例:
    from yweb.permission import PermissionService
    
    # 创建服务实例
    perm_service = PermissionService(
        permission_model=Permission,
        role_model=Role,
        subject_role_model=SubjectRole,
        role_permission_model=RolePermission,
        subject_permission_model=SubjectPermission,
    )
    
    # 检查权限
    has_perm = perm_service.check_permission("employee:123", "user:read")
    
    # 获取用户所有权限
    perms = perm_service.get_all_permissions("employee:123")
"""

from typing import Set, List, Optional, Type, TYPE_CHECKING
from datetime import datetime

from ..cache import permission_cache
from ..enums import UserType
from ..types import SubjectId, PermissionCode, RoleCode, parse_subject_id
from ..exceptions import (
    PermissionDeniedException,
    PermissionNotFoundException,
    DuplicatePermissionException,
)
from yweb.log import get_logger

if TYPE_CHECKING:
    from ..models import (
        AbstractPermission,
        AbstractRole,
        AbstractSubjectRole,
        AbstractRolePermission,
        AbstractSubjectPermission,
    )

logger = get_logger("yweb.permission.service")


class PermissionService:
    """权限服务
    
    提供权限检查和管理的核心功能：
    - 权限检查（支持缓存）
    - 权限 CRUD
    - 权限分配（给角色/用户）
    
    缓存机制：
    - 使用 TTLCache 缓存权限结果
    - 权限变更时自动失效相关缓存
    
    使用示例:
        # 初始化服务
        perm_service = PermissionService(
            permission_model=Permission,
            role_model=Role,
            subject_role_model=SubjectRole,
            role_permission_model=RolePermission,
            subject_permission_model=SubjectPermission,
        )
        
        # 检查权限
        if perm_service.check_permission("employee:123", "user:read"):
            # 有权限
            pass
        
        # 获取用户所有权限
        perms = perm_service.get_all_permissions("employee:123")
        
        # 授予用户直接权限
        perm_service.grant_subject_permission(
            "employee:123",
            "admin:special",
            granted_by=admin_id
        )
    """
    
    def __init__(
        self,
        permission_model: Type["AbstractPermission"],
        role_model: Type["AbstractRole"],
        subject_role_model: Type["AbstractSubjectRole"],
        role_permission_model: Type["AbstractRolePermission"],
        subject_permission_model: Type["AbstractSubjectPermission"],
        use_cache: bool = True
    ):
        """初始化权限服务
        
        Args:
            permission_model: 权限模型类
            role_model: 角色模型类
            subject_role_model: 主体-角色关联模型类
            role_permission_model: 角色-权限关联模型类
            subject_permission_model: 主体-权限关联模型类
            use_cache: 是否使用缓存，默认 True
        """
        self._permission_model = permission_model
        self._role_model = role_model
        self._subject_role_model = subject_role_model
        self._role_permission_model = role_permission_model
        self._subject_permission_model = subject_permission_model
        self._use_cache = use_cache
    
    # ==================== 权限检查 ====================
    
    def check_permission(
        self,
        subject_id: SubjectId,
        permission_code: PermissionCode,
        raise_exception: bool = False
    ) -> bool:
        """检查主体是否有某个权限
        
        检查顺序：
        1. 查缓存
        2. 缓存未命中则加载并缓存
        
        Args:
            subject_id: 主体标识，如 "employee:123"
            permission_code: 权限编码，如 "user:read"
            raise_exception: 无权限时是否抛出异常
            
        Returns:
            是否有权限
            
        Raises:
            PermissionDeniedException: 当 raise_exception=True 且无权限时
        """
        # 尝试从缓存获取
        if self._use_cache:
            cached = permission_cache.has_permission(subject_id, permission_code)
            if cached is not None:
                if not cached and raise_exception:
                    raise PermissionDeniedException(
                        permission_code=permission_code,
                        subject_id=subject_id
                    )
                return cached
        
        # 缓存未命中，加载权限
        permissions = self._load_permissions(subject_id)
        
        # 更新缓存
        if self._use_cache:
            permission_cache.set_permissions(subject_id, permissions)
        
        has_perm = permission_code in permissions
        
        if not has_perm and raise_exception:
            raise PermissionDeniedException(
                permission_code=permission_code,
                subject_id=subject_id
            )
        
        return has_perm
    
    def check_permissions(
        self,
        subject_id: SubjectId,
        permission_codes: List[PermissionCode],
        require_all: bool = True
    ) -> bool:
        """检查主体是否有多个权限
        
        Args:
            subject_id: 主体标识
            permission_codes: 权限编码列表
            require_all: True 表示需要全部权限，False 表示只需任一
            
        Returns:
            是否满足权限要求
        """
        if not permission_codes:
            return True
        
        permissions = self.get_all_permissions(subject_id)
        
        if require_all:
            return all(code in permissions for code in permission_codes)
        else:
            return any(code in permissions for code in permission_codes)
    
    def get_all_permissions(self, subject_id: SubjectId) -> Set[PermissionCode]:
        """获取主体的所有权限编码
        
        包括：
        - 通过角色获得的权限
        - 角色继承的权限
        - 直接授予的权限
        
        Args:
            subject_id: 主体标识
            
        Returns:
            权限编码集合
        """
        # 尝试从缓存获取
        if self._use_cache:
            cached = permission_cache.get_permissions(subject_id)
            if cached is not None:
                return cached
        
        # 加载权限
        permissions = self._load_permissions(subject_id)
        
        # 更新缓存
        if self._use_cache:
            permission_cache.set_permissions(subject_id, permissions)
        
        return permissions
    
    def _load_permissions(self, subject_id: SubjectId) -> Set[PermissionCode]:
        """从数据库加载主体的所有权限
        
        Args:
            subject_id: 主体标识
            
        Returns:
            权限编码集合
        """
        permissions: Set[str] = set()
        
        # 解析主体ID
        subject_type, id_value = parse_subject_id(subject_id)
        
        # 1. 获取主体的角色
        role_ids = self._get_subject_role_ids(subject_type, id_value)
        
        # 2. 获取角色及其祖先的权限
        for role_id in role_ids:
            role = self._role_model.get(role_id)
            if role and role.is_active:
                # 角色自身的权限
                role_perms = self._get_role_permissions(role.code)
                permissions.update(role_perms)
                
                # 祖先角色的权限（继承）
                ancestors = role.get_ancestors()
                for ancestor in ancestors:
                    if ancestor.is_active:
                        ancestor_perms = self._get_role_permissions(ancestor.code)
                        permissions.update(ancestor_perms)
        
        # 3. 获取直接授予的权限
        direct_perms = self._get_subject_direct_permissions(subject_type, id_value)
        permissions.update(direct_perms)
        
        return permissions
    
    def _get_subject_role_ids(self, subject_type: str, subject_id: int) -> List[int]:
        """获取主体的角色ID列表"""
        subject_roles = self._subject_role_model.get_subject_roles(
            subject_type=subject_type,
            subject_id=subject_id
        )
        return [sr.role_id for sr in subject_roles if sr.is_valid]
    
    def _get_role_permissions(self, role_code: RoleCode) -> Set[PermissionCode]:
        """获取角色的权限（带缓存）"""
        # 尝试从缓存获取
        if self._use_cache:
            cached = permission_cache.get_role_permissions(role_code)
            if cached is not None:
                return cached
        
        # 从数据库加载
        role = self._role_model.get_by_code(role_code)
        if not role:
            return set()
        
        perm_ids = self._role_permission_model.get_role_permission_ids(role.id)
        permissions = set()
        
        for perm_id in perm_ids:
            perm = self._permission_model.get(perm_id)
            if perm and perm.is_active:
                permissions.add(perm.code)
        
        # 更新缓存
        if self._use_cache:
            permission_cache.set_role_permissions(role_code, permissions)
        
        return permissions
    
    def _get_subject_direct_permissions(
        self,
        subject_type: str,
        subject_id: int
    ) -> Set[PermissionCode]:
        """获取主体直接授予的权限"""
        subject_perms = self._subject_permission_model.get_subject_permissions(
            subject_type=subject_type,
            subject_id=subject_id
        )
        
        permissions = set()
        for sp in subject_perms:
            if sp.is_valid:
                perm = self._permission_model.get(sp.permission_id)
                if perm and perm.is_active:
                    permissions.add(perm.code)
        
        return permissions
    
    # ==================== 角色检查 ====================
    
    def check_role(
        self,
        subject_id: SubjectId,
        role_code: RoleCode,
        raise_exception: bool = False
    ) -> bool:
        """检查主体是否有某个角色
        
        Args:
            subject_id: 主体标识
            role_code: 角色编码
            raise_exception: 无角色时是否抛出异常
            
        Returns:
            是否有该角色
        """
        roles = self.get_all_roles(subject_id)
        has_role = role_code in roles
        
        if not has_role and raise_exception:
            raise PermissionDeniedException(
                message=f"需要角色: {role_code}",
                subject_id=subject_id,
                required_roles=[role_code]
            )
        
        return has_role
    
    def get_all_roles(self, subject_id: SubjectId) -> Set[RoleCode]:
        """获取主体的所有角色编码
        
        包括直接分配的角色及其祖先角色。
        
        Args:
            subject_id: 主体标识
            
        Returns:
            角色编码集合
        """
        # 尝试从缓存获取
        if self._use_cache:
            cached = permission_cache.get_roles(subject_id)
            if cached is not None:
                return cached
        
        # 加载角色
        roles = self._load_roles(subject_id)
        
        # 更新缓存
        if self._use_cache:
            permission_cache.set_roles(subject_id, roles)
        
        return roles
    
    def _load_roles(self, subject_id: SubjectId) -> Set[RoleCode]:
        """从数据库加载主体的所有角色"""
        roles: Set[str] = set()
        
        subject_type, id_value = parse_subject_id(subject_id)
        
        role_ids = self._get_subject_role_ids(subject_type, id_value)
        
        for role_id in role_ids:
            role = self._role_model.get(role_id)
            if role and role.is_active:
                roles.add(role.code)
                # 添加祖先角色
                ancestor_codes = role.get_all_ancestor_codes()
                roles.update(ancestor_codes)
        
        return roles
    
    # ==================== 权限管理 ====================
    
    def create_permission(
        self,
        code: str,
        name: str,
        resource: Optional[str] = None,
        action: Optional[str] = None,
        description: Optional[str] = None,
        module: Optional[str] = None
    ) -> "AbstractPermission":
        """创建权限
        
        Args:
            code: 权限编码，如 "user:read"
            name: 权限名称
            resource: 资源类型（不提供则从 code 解析）
            action: 操作类型（不提供则从 code 解析）
            description: 描述
            module: 所属模块
            
        Returns:
            创建的权限对象
            
        Raises:
            DuplicatePermissionException: 权限编码已存在
        """
        # 检查是否存在
        existing = self._permission_model.get_by_code(code)
        if existing:
            raise DuplicatePermissionException(code)
        
        # 解析 resource 和 action
        if not resource or not action:
            if ":" in code:
                parts = code.split(":", 1)
                resource = resource or parts[0]
                action = action or parts[1]
            else:
                resource = resource or code
                action = action or "*"
        
        permission = self._permission_model(
            code=code,
            name=name,
            resource=resource,
            action=action,
            description=description,
            module=module
        )
        permission.save(commit=True)
        
        logger.info(f"Permission created: {code}")
        return permission
    
    def get_permission(self, code: str) -> Optional["AbstractPermission"]:
        """获取权限"""
        return self._permission_model.get_by_code(code)
    
    def update_permission(
        self,
        code: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None,
        module: Optional[str] = None
    ) -> "AbstractPermission":
        """更新权限
        
        Args:
            code: 权限编码
            name: 新名称
            description: 新描述
            is_active: 是否启用
            module: 所属模块
            
        Returns:
            更新后的权限对象
        """
        permission = self._permission_model.get_by_code(code)
        if not permission:
            raise PermissionNotFoundException(code)
        
        if name is not None:
            permission.name = name
        if description is not None:
            permission.description = description
        if is_active is not None:
            permission.is_active = is_active
        if module is not None:
            permission.module = module
        
        permission.save(commit=True)
        
        # 失效相关缓存
        if self._use_cache and is_active is not None:
            # 权限状态变化影响范围大，直接失效所有缓存
            permission_cache.invalidate_all()
        
        logger.info(f"Permission updated: {code}")
        return permission
    
    def delete_permission(self, code: str) -> bool:
        """删除权限（软删除）"""
        permission = self._permission_model.get_by_code(code)
        if not permission:
            return False
        
        permission.delete(commit=True)
        
        # 失效缓存
        if self._use_cache:
            permission_cache.invalidate_all()
        
        logger.info(f"Permission deleted: {code}")
        return True
    
    # ==================== 直接权限授予 ====================
    
    def grant_subject_permission(
        self,
        subject_id: SubjectId,
        permission_code: PermissionCode,
        granted_by: Optional[int] = None,
        expires_at: Optional[datetime] = None,
        reason: Optional[str] = None
    ) -> "AbstractSubjectPermission":
        """给主体直接授予权限
        
        Args:
            subject_id: 主体标识
            permission_code: 权限编码
            granted_by: 授权人ID
            expires_at: 过期时间
            reason: 授权原因
            
        Returns:
            主体权限关联对象
        """
        subject_type, id_value = parse_subject_id(subject_id)
        
        # 获取权限
        permission = self._permission_model.get_by_code(permission_code)
        if not permission:
            raise PermissionNotFoundException(permission_code)
        
        # 检查是否已存在
        existing = self._subject_permission_model.query.filter_by(
            subject_type=subject_type,
            subject_id=id_value,
            permission_id=permission.id
        ).first()
        
        if existing:
            # 更新
            existing.granted_by = granted_by
            existing.granted_at = datetime.now()
            existing.expires_at = expires_at
            existing.reason = reason
            existing.is_active = True
            existing.save(commit=True)
            sp = existing
        else:
            # 创建
            sp = self._subject_permission_model(
                subject_type=subject_type,
                subject_id=id_value,
                permission_id=permission.id,
                granted_by=granted_by,
                expires_at=expires_at,
                reason=reason
            )
            sp.save(commit=True)
        
        # 失效缓存
        if self._use_cache:
            permission_cache.invalidate_subject(subject_id)
        
        logger.info(f"Permission granted: {subject_id} <- {permission_code}")
        return sp
    
    def revoke_subject_permission(
        self,
        subject_id: SubjectId,
        permission_code: PermissionCode
    ) -> bool:
        """撤销主体的直接权限
        
        Args:
            subject_id: 主体标识
            permission_code: 权限编码
            
        Returns:
            是否成功
        """
        subject_type, id_value = parse_subject_id(subject_id)
        
        permission = self._permission_model.get_by_code(permission_code)
        if not permission:
            return False
        
        sp = self._subject_permission_model.query.filter_by(
            subject_type=subject_type,
            subject_id=id_value,
            permission_id=permission.id
        ).first()
        
        if not sp:
            return False
        
        sp.delete(commit=True)
        
        # 失效缓存
        if self._use_cache:
            permission_cache.invalidate_subject(subject_id)
        
        logger.info(f"Permission revoked: {subject_id} <- {permission_code}")
        return True
    
    # ==================== 角色分配 ====================
    
    def assign_role(
        self,
        subject_id: SubjectId,
        role_code: RoleCode,
        granted_by: Optional[int] = None,
        expires_at: Optional[datetime] = None
    ) -> "AbstractSubjectRole":
        """给主体分配角色
        
        Args:
            subject_id: 主体标识
            role_code: 角色编码
            granted_by: 授权人ID
            expires_at: 过期时间
            
        Returns:
            主体角色关联对象
        """
        from ..exceptions import RoleNotFoundException
        
        subject_type, id_value = parse_subject_id(subject_id)
        
        # 获取角色
        role = self._role_model.get_by_code(role_code)
        if not role:
            raise RoleNotFoundException(role_code)
        
        # 检查是否已存在
        existing = self._subject_role_model.query.filter_by(
            subject_type=subject_type,
            subject_id=id_value,
            role_id=role.id
        ).first()
        
        if existing:
            # 更新
            existing.granted_by = granted_by
            existing.granted_at = datetime.now()
            existing.expires_at = expires_at
            existing.is_active = True
            existing.save(commit=True)
            sr = existing
        else:
            # 创建
            sr = self._subject_role_model(
                subject_type=subject_type,
                subject_id=id_value,
                role_id=role.id,
                granted_by=granted_by,
                expires_at=expires_at
            )
            sr.save(commit=True)
        
        # 失效缓存
        if self._use_cache:
            permission_cache.invalidate_subject(subject_id)
        
        logger.info(f"Role assigned: {subject_id} <- {role_code}")
        return sr
    
    def unassign_role(
        self,
        subject_id: SubjectId,
        role_code: RoleCode
    ) -> bool:
        """撤销主体的角色
        
        Args:
            subject_id: 主体标识
            role_code: 角色编码
            
        Returns:
            是否成功
        """
        subject_type, id_value = parse_subject_id(subject_id)
        
        role = self._role_model.get_by_code(role_code)
        if not role:
            return False
        
        sr = self._subject_role_model.query.filter_by(
            subject_type=subject_type,
            subject_id=id_value,
            role_id=role.id
        ).first()
        
        if not sr:
            return False
        
        sr.delete(commit=True)
        
        # 失效缓存
        if self._use_cache:
            permission_cache.invalidate_subject(subject_id)
        
        logger.info(f"Role unassigned: {subject_id} <- {role_code}")
        return True


__all__ = ["PermissionService"]
