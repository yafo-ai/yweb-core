"""用户管理 CRUD 路由

提供完整的用户增删改查能力，基于 AbstractUser 的内置字段。

端点列表：
    GET  /list            - 搜索用户列表（关键词 + 状态过滤 + 分页）
    GET  /get             - 获取用户详情（?user_id=）
    POST /create          - 创建用户
    POST /update          - 更新用户信息（?user_id=）
    POST /enable          - 启用用户（?user_id=）
    POST /disable         - 禁用用户（?user_id=）
    POST /reset-password  - 重置密码（?user_id=）

使用示例::

    from yweb.auth.api import create_user_router

    user_router = create_user_router(User)
    app.include_router(user_router, prefix="/api/v1/users", tags=["users"])
"""

from typing import Type, Optional, List, TYPE_CHECKING

from fastapi import APIRouter, Query
from pydantic import BaseModel as PydanticBaseModel

from yweb.response import Resp, PageResponse, ItemResponse, OkResponse
from yweb.orm import DTO

if TYPE_CHECKING:
    from ..models import AbstractUser


def create_user_router(
    user_model: Type["AbstractUser"],
) -> APIRouter:
    """创建用户管理 CRUD 路由

    Args:
        user_model: 用户模型类（AbstractUser 的子类）

    Returns:
        APIRouter，包含用户 CRUD 路由
    """
    from ..validators import PasswordValidator
    from ..password import PasswordHelper

    router = APIRouter()

    # ==================== DTO 定义 ====================

    class UserResponse(DTO):
        """用户响应（含角色信息）"""
        id: int = 0
        username: str = ""
        name: Optional[str] = None
        email: Optional[str] = None
        phone: Optional[str] = None
        is_active: str = "active"
        created_at: str = ""
        roles: List[dict] = []

        _field_mapping = {'is_active': 'status'}
        _value_processors = {
            'is_active': lambda v: 'active' if v else 'inactive',
            'roles': lambda v: [
                {'code': r.code, 'name': r.name} if hasattr(r, 'code')
                else {'code': str(r), 'name': str(r)}
                for r in (v or [])
            ],
        }

    class UserDetailResponse(DTO):
        """用户详情响应"""
        id: int = 0
        username: str = ""
        name: Optional[str] = None
        email: Optional[str] = None
        phone: Optional[str] = None
        is_active: str = "active"
        created_at: str = ""
        last_login_at: Optional[str] = None

        _field_mapping = {'is_active': 'status'}
        _value_processors = {
            'is_active': lambda v: 'active' if v else 'inactive',
        }

    class CreateUserRequest(PydanticBaseModel):
        """创建用户请求"""
        username: str
        name: str
        email: Optional[str] = None
        phone: Optional[str] = None
        password: str
        status: str = "active"

    class UpdateUserRequest(PydanticBaseModel):
        """更新用户请求"""
        name: str
        email: Optional[str] = None
        phone: Optional[str] = None
        status: str

    class ResetPasswordRequest(PydanticBaseModel):
        """重置密码请求"""
        password: str

    # ==================== 查询接口 ====================

    @router.get("/list", response_model=PageResponse[UserResponse], summary="搜索用户列表")
    async def list_users(
        keyword: Optional[str] = Query(None, description="搜索关键词（用户名、姓名、邮箱、手机号）"),
        status: Optional[str] = Query(None, description="用户状态 (active, inactive)"),
        role: Optional[str] = Query(None, description="角色编码过滤（如 admin, user, external）"),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    ):
        """获取用户列表（含角色信息）

        使用 search_with_roles 预加载角色，一次查询返回完整数据，
        避免前端逐个请求用户角色导致的 N+1 问题。
        """
        is_active = None
        if status == "active":
            is_active = True
        elif status == "inactive":
            is_active = False

        page_result = user_model.search_with_roles(
            keyword=keyword,
            is_active=is_active,
            role_code=role,
            page=page,
            page_size=page_size,
        )
        return Resp.OK(UserResponse.from_page(page_result))

    @router.get("/get", response_model=ItemResponse[UserDetailResponse], summary="获取用户详情")
    async def get_user(
        user_id: int = Query(..., description="用户ID"),
    ):
        """获取用户详情"""
        user = user_model.get(user_id)
        if not user:
            return Resp.NotFound("用户不存在")
        return Resp.OK(UserDetailResponse.from_entity(user))

    # ==================== 写入接口 ====================

    @router.post("/create", response_model=ItemResponse[UserResponse], summary="创建用户")
    async def create_user(request: CreateUserRequest):
        """创建用户（自动验证 + 密码哈希）"""
        try:
            user = user_model.create_user(
                username=request.username,
                password=request.password,
                email=request.email,
                phone=request.phone,
                name=request.name,
                is_active=request.status != "inactive",
            )
            return Resp.OK(UserResponse.from_entity(user), message="用户创建成功")
        except ValueError as e:
            return Resp.BadRequest(message=str(e))

    @router.post("/update", response_model=ItemResponse[UserResponse], summary="更新用户信息")
    async def update_user(
        request: UpdateUserRequest,
        user_id: int = Query(..., description="用户ID"),
    ):
        """更新用户信息"""
        user = user_model.get(user_id)
        if not user:
            return Resp.NotFound("用户不存在")

        if request.name:
            user.name = request.name
        if request.email is not None:
            user.email = request.email
        if request.phone is not None:
            user.phone = request.phone
        user.is_active = request.status == "active"
        user.update(True)

        return Resp.OK(UserResponse.from_entity(user), message="用户更新成功")

    @router.post("/enable", response_model=ItemResponse[UserResponse], summary="启用用户")
    async def enable_user(
        user_id: int = Query(..., description="用户ID"),
    ):
        """启用用户"""
        user = user_model.get(user_id)
        if not user:
            return Resp.NotFound("用户不存在")

        user.is_active = True
        user.update()
        return Resp.OK(UserResponse.from_entity(user), message="用户启用成功")

    @router.post("/disable", response_model=ItemResponse[UserResponse], summary="禁用用户")
    async def disable_user(
        user_id: int = Query(..., description="用户ID"),
    ):
        """禁用用户"""
        user = user_model.get(user_id)
        if not user:
            return Resp.NotFound("用户不存在")

        user.is_active = False
        user.update()
        return Resp.OK(UserResponse.from_entity(user), message="用户禁用成功")

    @router.post("/reset-password", response_model=OkResponse, summary="重置密码")
    async def reset_password(
        request: ResetPasswordRequest,
        user_id: int = Query(..., description="用户ID"),
    ):
        """重置用户密码"""
        user = user_model.get(user_id)
        if not user:
            return Resp.NotFound("用户不存在")

        try:
            PasswordValidator.validate_or_raise(request.password)
            user.password_hash = PasswordHelper.hash(request.password)
            user.update()
            return Resp.OK({"id": user.id, "username": user.username}, message="密码重置成功")
        except ValueError as e:
            return Resp.BadRequest(message=str(e))

    return router
