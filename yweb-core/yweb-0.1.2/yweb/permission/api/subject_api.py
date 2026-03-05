"""
权限模块 - 用户授权 API

提供用户角色分配、权限授予、权限检查等接口。
使用动词风格路由，只使用 GET 和 POST 请求。
"""

from typing import Type, Optional, List, TYPE_CHECKING
from datetime import datetime
from fastapi import APIRouter, Query

from yweb.response import Resp

from ..schemas.assignment import (
    RoleAssignment,
    PermissionAssignment,
    SubjectPermissionsResponse,
)
from ..schemas.permission import PermissionCheck, PermissionCheckResult
from ..services import PermissionService
from ..cache import permission_cache
from ..types import parse_subject_id

if TYPE_CHECKING:
    from ..models import (
        AbstractPermission,
        AbstractRole,
        AbstractSubjectRole,
        AbstractRolePermission,
        AbstractSubjectPermission,
    )


def create_subject_router(
    permission_model: Type["AbstractPermission"],
    role_model: Type["AbstractRole"],
    subject_role_model: Type["AbstractSubjectRole"],
    role_permission_model: Type["AbstractRolePermission"],
    subject_permission_model: Type["AbstractSubjectPermission"],
) -> APIRouter:
    """创建用户授权路由
    
    Args:
        permission_model: 权限模型类
        role_model: 角色模型类
        subject_role_model: 主体-角色关联模型类
        role_permission_model: 角色-权限关联模型类
        subject_permission_model: 主体-权限关联模型类
        
    Returns:
        APIRouter
        
    生成的路由:
        POST /assign-role     - 分配角色
        POST /unassign-role   - 撤销角色
        POST /assign-role-batch - 批量分配角色
        POST /grant-permission  - 授予权限
        POST /revoke-permission - 撤销权限
        GET  /get             - 获取用户权限
        GET  /roles           - 获取用户角色
        POST /check           - 检查权限
        POST /check-batch     - 批量检查权限
        POST /invalidate-cache - 失效用户缓存
    """
    router = APIRouter()
    
    # 创建 PermissionService 实例
    perm_service = PermissionService(
        permission_model=permission_model,
        role_model=role_model,
        subject_role_model=subject_role_model,
        role_permission_model=role_permission_model,
        subject_permission_model=subject_permission_model,
    )
    
    # ==================== 角色分配 ====================
    
    @router.post(
        "/assign-role",
        summary="分配角色",
        description="给用户分配角色"
    )
    async def assign_role(data: RoleAssignment):
        """给用户分配角色"""
        try:
            sr = perm_service.assign_role(
                subject_id=data.subject_id,
                role_code=data.role_code,
                expires_at=data.expires_at,
            )
            return Resp.OK(data={
                "subject_id": data.subject_id,
                "role_code": data.role_code,
                "expires_at": data.expires_at.isoformat() if data.expires_at else None,
            }, message="分配成功")
        except Exception as e:
            return Resp.BadRequest(message=str(e))
    
    @router.post(
        "/unassign-role",
        summary="撤销角色",
        description="撤销用户的角色"
    )
    async def unassign_role(
        subject_id: str = Query(..., description="主体标识，如 employee:123"),
        role_code: str = Query(..., description="角色编码"),
    ):
        """撤销用户角色"""
        result = perm_service.unassign_role(
            subject_id=subject_id,
            role_code=role_code,
        )
        
        message = "撤销成功" if result else "角色不存在"
        return Resp.OK(data={
            "subject_id": subject_id,
            "role_code": role_code,
        }, message=message)
    
    @router.post(
        "/assign-role-batch",
        summary="批量分配角色",
        description="给多个用户分配同一角色"
    )
    async def batch_assign_role(
        subject_ids: List[str],
        role_code: str,
        expires_at: Optional[datetime] = None,
    ):
        """批量分配角色"""
        success = []
        failed = []
        
        for subject_id in subject_ids:
            try:
                perm_service.assign_role(
                    subject_id=subject_id,
                    role_code=role_code,
                    expires_at=expires_at,
                )
                success.append(subject_id)
            except Exception as e:
                failed.append({"subject_id": subject_id, "error": str(e)})
        
        return Resp.OK(data={
            "success_count": len(success),
            "failed_count": len(failed),
            "success": success,
            "failed": failed,
        }, message="批量分配完成")
    
    # ==================== 直接权限授予 ====================
    
    @router.post(
        "/grant-permission",
        summary="授予权限",
        description="直接给用户授予权限（绕过角色）"
    )
    async def grant_permission(data: PermissionAssignment):
        """直接给用户授予权限"""
        try:
            sp = perm_service.grant_subject_permission(
                subject_id=data.subject_id,
                permission_code=data.permission_code,
                expires_at=data.expires_at,
                reason=data.reason,
            )
            return Resp.OK(data={
                "subject_id": data.subject_id,
                "permission_code": data.permission_code,
                "expires_at": data.expires_at.isoformat() if data.expires_at else None,
            }, message="授权成功")
        except Exception as e:
            return Resp.BadRequest(message=str(e))
    
    @router.post(
        "/revoke-permission",
        summary="撤销权限",
        description="撤销用户的直接权限"
    )
    async def revoke_permission(
        subject_id: str = Query(..., description="主体标识"),
        permission_code: str = Query(..., description="权限编码"),
    ):
        """撤销用户的直接权限"""
        result = perm_service.revoke_subject_permission(
            subject_id=subject_id,
            permission_code=permission_code,
        )
        
        message = "撤销成功" if result else "权限不存在"
        return Resp.OK(data={
            "subject_id": subject_id,
            "permission_code": permission_code,
        }, message=message)
    
    # ==================== 用户权限查询 ====================
    
    @router.get(
        "/get",
        response_model=SubjectPermissionsResponse,
        summary="获取用户权限",
        description="获取用户的所有角色和权限"
    )
    async def get_subject_permissions(
        subject_id: str = Query(..., description="主体标识，如 employee:123"),
    ):
        """获取用户的所有角色和权限"""
        try:
            parse_subject_id(subject_id)  # 验证格式
        except ValueError as e:
            return Resp.BadRequest(message=str(e))
        
        # 获取角色
        roles = perm_service.get_all_roles(subject_id)
        
        # 获取所有权限（含继承）
        permissions = perm_service.get_all_permissions(subject_id)
        
        # 获取直接权限
        subject_type, id_value = parse_subject_id(subject_id)
        direct_sp = subject_permission_model.get_subject_permissions(
            subject_type=subject_type,
            subject_id=id_value,
        )
        direct_perm_ids = [sp.permission_id for sp in direct_sp if sp.is_valid]
        direct_perms = set()
        for perm_id in direct_perm_ids:
            perm = permission_model.get(perm_id)
            if perm and perm.is_active:
                direct_perms.add(perm.code)
        
        return Resp.OK(data={
            "subject_id": subject_id,
            "roles": list(roles),
            "permissions": list(permissions),
            "direct_permissions": list(direct_perms),
        })
    
    @router.get(
        "/roles",
        summary="获取用户角色",
        description="获取用户的所有角色"
    )
    async def get_subject_roles(
        subject_id: str = Query(..., description="主体标识"),
    ):
        """获取用户的所有角色"""
        try:
            parse_subject_id(subject_id)
        except ValueError as e:
            return Resp.BadRequest(message=str(e))
        
        roles = perm_service.get_all_roles(subject_id)
        
        # 获取角色详情
        role_details = []
        for role_code in roles:
            role = role_model.query.filter_by(code=role_code).first()
            if role:
                role_details.append(role.to_dict())
        
        return Resp.OK(data={
            "subject_id": subject_id,
            "roles": role_details,
        })
    
    @router.post(
        "/check",
        response_model=PermissionCheckResult,
        summary="检查权限",
        description="检查用户是否有指定权限"
    )
    async def check_permission(
        data: PermissionCheck,
        subject_id: str = Query(..., description="主体标识"),
    ):
        """检查用户是否有指定权限"""
        try:
            parse_subject_id(subject_id)
        except ValueError as e:
            return Resp.BadRequest(message=str(e))
        
        has_perm = perm_service.check_permission(
            subject_id=subject_id,
            permission_code=data.permission_code,
        )
        
        return Resp.OK(data={
            "has_permission": has_perm,
            "subject_id": subject_id,
            "permission_code": data.permission_code,
        })
    
    @router.post(
        "/check-batch",
        summary="批量检查权限",
        description="检查用户是否有多个权限"
    )
    async def check_permissions_batch(
        permission_codes: List[str],
        subject_id: str = Query(..., description="主体标识"),
        require_all: bool = Query(True, description="True=需要全部权限，False=只需任一"),
    ):
        """批量检查权限"""
        try:
            parse_subject_id(subject_id)
        except ValueError as e:
            return Resp.BadRequest(message=str(e))
        
        result = perm_service.check_permissions(
            subject_id=subject_id,
            permission_codes=permission_codes,
            require_all=require_all,
        )
        
        # 获取各权限的检查结果
        details = {}
        all_perms = perm_service.get_all_permissions(subject_id)
        for code in permission_codes:
            details[code] = code in all_perms
        
        return Resp.OK(data={
            "subject_id": subject_id,
            "result": result,
            "require_all": require_all,
            "details": details,
        })
    
    @router.post(
        "/invalidate-cache",
        summary="失效用户缓存",
        description="使用户的权限缓存失效"
    )
    async def invalidate_subject_cache(
        subject_id: str = Query(..., description="主体标识"),
    ):
        """使用户缓存失效"""
        permission_cache.invalidate_subject(subject_id)
        return Resp.OK(data={"subject_id": subject_id}, message="缓存已失效")
    
    return router


__all__ = ["create_subject_router"]
