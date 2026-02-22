"""
权限模块 - 角色 CRUD API

提供角色的增删改查接口。
使用动词风格路由，只使用 GET 和 POST 请求。
"""

from typing import Type, Optional, List, TYPE_CHECKING
from fastapi import APIRouter, Query

from yweb.response import Resp

from ..schemas.role import (
    RoleCreate,
    RoleUpdate,
    RoleResponse,
    RoleListResponse,
    RoleTreeResponse,
    RolePermissionSet,
    RoleSubjectsResponse,
)
from ..exceptions import (
    RoleNotFoundException,
    DuplicateRoleException,
    RoleInheritanceCycleException,
    SystemRoleModifyException,
)
from ..cache import permission_cache

if TYPE_CHECKING:
    from ..models import (
        AbstractRole,
        AbstractPermission,
        AbstractRolePermission,
        AbstractSubjectRole,
    )


def create_role_crud_router(
    role_model: Type["AbstractRole"],
    permission_model: Type["AbstractPermission"],
    role_permission_model: Type["AbstractRolePermission"],
    subject_role_model: Type["AbstractSubjectRole"],
) -> APIRouter:
    """创建角色 CRUD 路由
    
    Args:
        role_model: 角色模型类
        permission_model: 权限模型类
        role_permission_model: 角色-权限关联模型类
        subject_role_model: 主体-角色关联模型类
        
    Returns:
        APIRouter
        
    生成的路由:
        GET  /list            - 获取角色列表
        GET  /tree            - 获取角色树
        GET  /get             - 获取角色详情
        POST /create          - 创建角色
        POST /update          - 更新角色
        POST /delete          - 删除角色
        GET  /permissions     - 获取角色权限
        POST /set-permissions - 设置角色权限（全量）
        POST /add-permission  - 添加角色权限
        POST /remove-permission - 移除角色权限
        GET  /subjects        - 获取角色用户
    """
    router = APIRouter()
    
    @router.get(
        "/list",
        response_model=RoleListResponse,
        summary="获取角色列表",
        description="获取所有角色"
    )
    async def list_roles(
        is_active: Optional[bool] = Query(None, description="按状态筛选"),
        include_inactive: bool = Query(False, description="是否包含禁用的角色"),
    ):
        """获取角色列表"""
        query = role_model.query
        
        if not include_inactive:
            query = query.filter(role_model.is_active == True)
        elif is_active is not None:
            query = query.filter(role_model.is_active == is_active)
        
        items = query.order_by(role_model.level, role_model.sort_order).all()
        
        # 使用 to_dict() 获取完整数据（包含用户扩展字段），再用 Schema 包装
        # 非分页列表直接返回数组
        return Resp.OK(data=[RoleResponse(**r.to_dict()).model_dump() for r in items])
    
    @router.get(
        "/tree",
        summary="获取角色树",
        description="获取角色的树形结构"
    )
    async def get_role_tree():
        """获取角色树"""
        root_roles = role_model.query.filter(
            role_model.parent_id.is_(None),
            role_model.is_active == True
        ).order_by(role_model.sort_order).all()
        
        def build_tree(role) -> dict:
            children = role_model.query.filter(
                role_model.parent_id == role.id,
                role_model.is_active == True
            ).order_by(role_model.sort_order).all()
            
            result = role.to_dict()
            result["children"] = [build_tree(c) for c in children]
            return result
        
        return Resp.OK(data={"tree": [build_tree(r) for r in root_roles]})
    
    @router.get(
        "/get",
        response_model=RoleResponse,
        summary="获取角色详情",
        description="根据角色编码获取详情"
    )
    async def get_role(
        code: str = Query(..., description="角色编码"),
        include_permissions: bool = Query(False, description="是否包含权限列表"),
    ):
        """获取角色详情"""
        role = role_model.query.filter_by(code=code).first()
        if not role:
            return Resp.NotFound(message=f"角色不存在: {code}")
        
        # 使用 to_dict() 获取完整数据（包含用户扩展字段）
        response_data = role.to_dict()
        
        if include_permissions:
            # 获取角色权限
            perm_ids = role_permission_model.get_role_permission_ids(role.id)
            perms = permission_model.query.filter(
                permission_model.id.in_(perm_ids)
            ).all() if perm_ids else []
            response_data["permissions"] = [p.code for p in perms]
        
        return Resp.OK(data=RoleResponse(**response_data).model_dump())
    
    @router.post(
        "/create",
        response_model=RoleResponse,
        summary="创建角色",
        description="创建新的角色"
    )
    async def create_role(data: RoleCreate):
        """创建角色"""
        # 检查是否存在
        existing = role_model.query.filter_by(code=data.code).first()
        if existing:
            return Resp.Conflict(message=f"角色已存在: {data.code}")
        
        # 处理父角色
        parent_id = None
        if data.parent_code:
            parent = role_model.query.filter_by(code=data.parent_code).first()
            if not parent:
                return Resp.NotFound(message=f"父角色不存在: {data.parent_code}")
            parent_id = parent.id
        
        role = role_model(
            code=data.code,
            name=data.name,
            description=data.description,
            parent_id=parent_id,
            is_system=data.is_system,
        )
        role.save(True)
        
        # 更新路径和层级
        if hasattr(role, 'update_path_and_level'):
            role.update_path_and_level()
        
        # 使用 to_dict() 获取完整数据（包含用户扩展字段）
        return Resp.OK(data=RoleResponse(**role.to_dict()).model_dump(), message="创建成功")
    
    @router.post(
        "/update",
        response_model=RoleResponse,
        summary="更新角色",
        description="更新角色信息"
    )
    async def update_role(
        data: RoleUpdate,
        code: str = Query(..., description="角色编码"),
    ):
        """更新角色"""
        role = role_model.query.filter_by(code=code).first()
        if not role:
            return Resp.NotFound(message=f"角色不存在: {code}")
        
        if role.is_system and data.is_active is not None and not data.is_active:
            return Resp.Forbidden(message=f"系统角色不可禁用: {code}")
        
        if data.name is not None:
            role.name = data.name
        if data.description is not None:
            role.description = data.description
        if data.is_active is not None:
            role.is_active = data.is_active
        if data.sort_order is not None:
            role.sort_order = data.sort_order
        
        # 更新父角色
        if data.parent_code is not None:
            if data.parent_code == "":
                role.parent_id = None
            else:
                parent = role_model.query.filter_by(code=data.parent_code).first()
                if not parent:
                    return Resp.NotFound(message=f"父角色不存在: {data.parent_code}")
                
                # 检查循环
                if parent.id == role.id:
                    return Resp.BadRequest(message="不能将自己设为父角色")
                
                # 检查 parent 的祖先中是否包含 role
                if hasattr(parent, 'get_ancestors'):
                    ancestors = parent.get_ancestors()
                    if any(a.id == role.id for a in ancestors):
                        return Resp.BadRequest(message="会产生循环继承")
                
                role.parent_id = parent.id
            
            if hasattr(role, 'update_path_and_level'):
                role.update_path_and_level()
        
        role.save(True)
        
        # 失效缓存
        if data.is_active is not None:
            permission_cache.invalidate_all()
        
        # 使用 to_dict() 获取完整数据（包含用户扩展字段）
        return Resp.OK(data=RoleResponse(**role.to_dict()).model_dump(), message="更新成功")
    
    @router.post(
        "/delete",
        summary="删除角色",
        description="删除角色（软删除）"
    )
    async def delete_role(
        code: str = Query(..., description="角色编码"),
        force: bool = Query(False, description="是否强制删除系统角色"),
    ):
        """删除角色"""
        role = role_model.query.filter_by(code=code).first()
        if not role:
            return Resp.NotFound(message=f"角色不存在: {code}")
        
        if role.is_system and not force:
            return Resp.Forbidden(message=f"系统角色不可删除: {code}")
        
        # 处理子角色
        if hasattr(role, 'get_children'):
            children = role.get_children()
            for child in children:
                child.parent_id = role.parent_id
                child.save(True)
                if hasattr(child, 'update_path_and_level'):
                    child.update_path_and_level()
        
        role.delete()
        
        # 失效缓存
        permission_cache.invalidate_all()
        
        return Resp.OK(data={"code": code}, message="删除成功")
    
    # ==================== 角色权限管理 ====================
    
    @router.get(
        "/permissions",
        summary="获取角色权限",
        description="获取角色拥有的权限列表"
    )
    async def get_role_permissions(
        code: str = Query(..., description="角色编码"),
        include_inherited: bool = Query(False, description="是否包含继承的权限"),
    ):
        """获取角色权限"""
        role = role_model.query.filter_by(code=code).first()
        if not role:
            return Resp.NotFound(message=f"角色不存在: {code}")
        
        # 直接权限
        perm_ids = role_permission_model.get_role_permission_ids(role.id)
        direct_perms = permission_model.query.filter(
            permission_model.id.in_(perm_ids),
            permission_model.is_active == True
        ).all() if perm_ids else []
        
        result = {
            "role_code": code,
            "permissions": [{"code": p.code, "name": p.name} for p in direct_perms]
        }
        
        if include_inherited and hasattr(role, 'get_ancestors'):
            inherited = []
            for ancestor in role.get_ancestors():
                if ancestor.is_active:
                    ancestor_perm_ids = role_permission_model.get_role_permission_ids(ancestor.id)
                    ancestor_perms = permission_model.query.filter(
                        permission_model.id.in_(ancestor_perm_ids),
                        permission_model.is_active == True
                    ).all() if ancestor_perm_ids else []
                    for p in ancestor_perms:
                        inherited.append({
                            "code": p.code,
                            "name": p.name,
                            "from_role": ancestor.code
                        })
            result["inherited_permissions"] = inherited
        
        return Resp.OK(data=result)
    
    @router.post(
        "/set-permissions",
        summary="设置角色权限",
        description="设置角色的权限（全量覆盖）"
    )
    async def set_role_permissions(
        data: RolePermissionSet,
        code: str = Query(..., description="角色编码"),
    ):
        """设置角色权限（全量覆盖）"""
        role = role_model.query.filter_by(code=code).first()
        if not role:
            return Resp.NotFound(message=f"角色不存在: {code}")
        
        # 验证权限存在性
        permission_ids = []
        for perm_code in data.permission_codes:
            perm = permission_model.query.filter_by(code=perm_code).first()
            if not perm:
                return Resp.NotFound(message=f"权限不存在: {perm_code}")
            permission_ids.append(perm.id)
        
        # 设置权限
        role_permission_model.set_role_permissions(role.id, permission_ids)
        
        # 失效缓存
        permission_cache.invalidate_role(code)
        # 失效所有拥有该角色的用户
        subject_roles = subject_role_model.get_role_subjects(role.id)
        subject_ids = [f"{sr.subject_type}:{sr.subject_id}" for sr in subject_roles]
        if subject_ids:
            permission_cache.invalidate_subjects_batch(subject_ids)
        
        return Resp.OK(data={"role_code": code, "permissions": data.permission_codes}, message="设置成功")
    
    @router.post(
        "/add-permission",
        summary="添加角色权限",
        description="给角色添加单个权限"
    )
    async def add_role_permission(
        code: str = Query(..., description="角色编码"),
        perm_code: str = Query(..., description="权限编码"),
    ):
        """添加角色权限"""
        role = role_model.query.filter_by(code=code).first()
        if not role:
            return Resp.NotFound(message=f"角色不存在: {code}")
        
        perm = permission_model.query.filter_by(code=perm_code).first()
        if not perm:
            return Resp.NotFound(message=f"权限不存在: {perm_code}")
        
        result = role_permission_model.add_role_permission(role.id, perm.id)
        
        if result:
            # 失效缓存
            permission_cache.invalidate_role(code)
            subject_roles = subject_role_model.get_role_subjects(role.id)
            subject_ids = [f"{sr.subject_type}:{sr.subject_id}" for sr in subject_roles]
            if subject_ids:
                permission_cache.invalidate_subjects_batch(subject_ids)
        
        message = "添加成功" if result else "权限已存在"
        return Resp.OK(data={"role_code": code, "permission_code": perm_code}, message=message)
    
    @router.post(
        "/remove-permission",
        summary="移除角色权限",
        description="移除角色的单个权限"
    )
    async def remove_role_permission(
        code: str = Query(..., description="角色编码"),
        perm_code: str = Query(..., description="权限编码"),
    ):
        """移除角色权限"""
        role = role_model.query.filter_by(code=code).first()
        if not role:
            return Resp.NotFound(message=f"角色不存在: {code}")
        
        perm = permission_model.query.filter_by(code=perm_code).first()
        if not perm:
            return Resp.OK(data={"role_code": code, "permission_code": perm_code}, message="权限不存在")
        
        result = role_permission_model.remove_role_permission(role.id, perm.id)
        
        if result:
            # 失效缓存
            permission_cache.invalidate_role(code)
            subject_roles = subject_role_model.get_role_subjects(role.id)
            subject_ids = [f"{sr.subject_type}:{sr.subject_id}" for sr in subject_roles]
            if subject_ids:
                permission_cache.invalidate_subjects_batch(subject_ids)
        
        message = "移除成功" if result else "权限不存在"
        return Resp.OK(data={"role_code": code, "permission_code": perm_code}, message=message)
    
    # ==================== 角色用户管理 ====================
    
    @router.get(
        "/subjects",
        response_model=RoleSubjectsResponse,
        summary="获取角色用户",
        description="获取拥有该角色的所有用户"
    )
    async def get_role_subjects(
        code: str = Query(..., description="角色编码"),
        subject_type: Optional[str] = Query(None, description="筛选用户类型"),
    ):
        """获取拥有该角色的用户"""
        role = role_model.query.filter_by(code=code).first()
        if not role:
            return Resp.NotFound(message=f"角色不存在: {code}")
        
        subject_roles = subject_role_model.get_role_subjects(
            role_id=role.id,
            subject_type=subject_type
        )
        
        return Resp.OK(data={
            "role_code": code,
            "subjects": [
                {
                    "subject_type": sr.subject_type,
                    "subject_id": sr.subject_id,
                    "granted_at": sr.granted_at.isoformat() if sr.granted_at else None,
                    "expires_at": sr.expires_at.isoformat() if sr.expires_at else None,
                }
                for sr in subject_roles
            ]
        })
    
    return router


__all__ = ["create_role_crud_router"]
