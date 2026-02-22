"""认证端点路由（登录 / 刷新 / 登出 / 踢出）

提供标准的登录、刷新令牌、登出、踢出用户等认证端点。

端点列表：
    POST /token   - OAuth2 密码模式登录
    POST /login   - JSON 用户名密码登录
    POST /refresh - 刷新访问令牌
    POST /logout  - 用户登出
    POST /kick    - 踢出用户

使用示例::

    from yweb.auth.api import create_auth_router

    auth_router = create_auth_router(auth_service, jwt_manager)
    app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
"""

from typing import Type, Optional, Callable, TYPE_CHECKING

from fastapi import APIRouter, Request, Depends
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel as PydanticBaseModel, Field, ConfigDict

from yweb.response import Resp, ItemResponse, OkResponse
from yweb.orm import DTO
from yweb.log import get_logger
from yweb.exceptions import AuthenticationException

if TYPE_CHECKING:
    from ..service import BaseAuthService
    from ..jwt import JWTManager
    from ..token_store import TokenBlacklist

_logger = get_logger("yweb.auth.api.auth")


def create_auth_router(
    auth_service: "BaseAuthService",
    jwt_manager: "JWTManager",
    token_blacklist: Optional["TokenBlacklist"] = None,
    user_getter: Optional[Callable] = None,
    # 端点开关
    enable_oauth2_token: bool = True,
    enable_json_login: bool = True,
    enable_refresh: bool = True,
    enable_logout: bool = True,
    enable_kick: bool = False,
    # 自定义
    login_response_builder: Optional[Callable] = None,
    user_response_dto: Optional[Type] = None,
) -> APIRouter:
    """创建认证端点路由

    提供标准的登录、刷新令牌、登出、踢出用户等认证端点。
    路由层只做参数验证、调用 service、包装响应，不写业务日志。

    如果项目需要完全自定义认证流程（如第三方登录、短信登录等），
    可以不使用此工厂函数，自行编写路由。

    Args:
        auth_service: BaseAuthService 实例（或其子类），提供认证核心操作
        jwt_manager: JWTManager 实例，用于令牌刷新（支持滑动过期）
        token_blacklist: TokenBlacklist 实例（可选，用于刷新时检查令牌撤销）
        user_getter: 用户获取函数 (user_id) -> user（可选，刷新令牌时使用）
        enable_oauth2_token: 是否启用 POST /token（OAuth2 密码模式，默认 True）
        enable_json_login: 是否启用 POST /login（JSON 登录，默认 True）
        enable_refresh: 是否启用 POST /refresh（刷新令牌，默认 True）
        enable_logout: 是否启用 POST /logout（登出，默认 True）
        enable_kick: 是否启用 POST /kick（踢出用户，默认 False）
        login_response_builder: 自定义登录响应构建函数 (user, access_token, refresh_token) -> dict
        user_response_dto: 自定义用户响应 DTO 类型（默认使用内置的 DefaultUserResponse）

    Returns:
        APIRouter，根据启用开关包含认证路由
    """
    router = APIRouter()

    # ==================== DTO 定义 ====================

    class LoginRequest(PydanticBaseModel):
        """登录请求"""
        username: str = Field(min_length=2, max_length=50, description="用户名", examples=["admin"])
        password: str = Field(min_length=6, max_length=128, description="密码", examples=["123456"])

    class DefaultUserResponse(DTO):
        """默认用户响应（登录成功时返回的用户信息）"""
        id: int
        username: str
        email: Optional[str] = None
        phone: Optional[str] = None
        is_active: bool = True

        model_config = ConfigDict(from_attributes=True, extra="allow")

    # 使用自定义或默认的用户响应 DTO
    UserResponseDTO = user_response_dto or DefaultUserResponse

    class LoginResponseSchema(PydanticBaseModel):
        """登录响应"""
        access_token: str
        refresh_token: str
        token_type: str = "bearer"
        user: dict

    class RefreshRequest(PydanticBaseModel):
        """刷新令牌请求"""
        refresh_token: str = Field(description="刷新令牌")

    class RefreshResponseSchema(PydanticBaseModel):
        """刷新令牌响应"""
        access_token: str
        refresh_token: Optional[str] = None
        token_type: str = "bearer"

    # ==================== 内部辅助 ====================

    def _do_login(username: str, password: str, ip_address: str, user_agent: str) -> dict:
        """执行登录流程（token 和 login 端点共用）"""
        rate_limiter = auth_service.rate_limiter

        # 0. IP 频率限制检查（一级防线）
        if rate_limiter and rate_limiter.is_blocked(ip_address):
            remaining_sec = rate_limiter.get_block_remaining_seconds(ip_address)
            remaining_min = remaining_sec // 60 + (1 if remaining_sec % 60 else 0)
            auth_service.on_authenticate_failure(
                username, ip_address=ip_address, user_agent=user_agent,
                reason=f"IP已封锁（剩余{remaining_min}分钟）",
            )
            raise AuthenticationException(
                f"登录尝试次数过多，请{remaining_min}分钟后重试",
            )

        # 1. 认证（捕获系统异常，确保失败记录被正确创建）
        try:
            user = auth_service.authenticate(username, password)
        except Exception as e:
            # 系统异常（数据库错误等），记录后重新抛出
            _logger.error(f"认证过程发生系统异常: {e}", exc_info=True)
            auth_service.on_authenticate_failure(
                username, ip_address=ip_address, user_agent=user_agent,
                reason=f"系统异常: {e}",
            )
            raise

        if not user:
            # 判断具体失败原因（仅用于内部记录，不暴露给客户端）
            reason = auth_service.get_failure_reason(username)
            auth_service.on_authenticate_failure(
                username, ip_address=ip_address, user_agent=user_agent,
                reason=reason,
            )

            # IP 频率限制：记录失败并获取剩余次数
            if rate_limiter:
                was_blocked, remaining = rate_limiter.record_failure(ip_address)
                if was_blocked:
                    raise AuthenticationException(
                        f"登录尝试次数过多，请{rate_limiter.block_minutes}分钟后重试",
                    )
                raise AuthenticationException(
                    f"用户名或密码错误，还可尝试{remaining}次",
                )

            raise AuthenticationException("用户名或密码错误")

        # 2. 登录成功：重置 IP 失败计数
        if rate_limiter:
            rate_limiter.reset(ip_address)

        # 3. 创建令牌
        access_token = auth_service.create_access_token(user)
        refresh_token = auth_service.create_refresh_token(user)

        # 3. 触发成功钩子 + 更新最后登录时间
        auth_service.on_authenticate_success(
            user, ip_address=ip_address, user_agent=user_agent
        )
        auth_service.update_last_login(
            user.id, ip_address=ip_address, user_agent=user_agent, status="success"
        )

        # 4. 构建响应
        if login_response_builder:
            return login_response_builder(user, access_token, refresh_token)

        user_data = UserResponseDTO.from_entity(user) if hasattr(UserResponseDTO, 'from_entity') else user
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": user_data.to_dict() if hasattr(user_data, 'to_dict') else user_data,
        }

    # ==================== 路由定义 ====================

    if enable_oauth2_token:
        @router.post("/token", response_model=ItemResponse[LoginResponseSchema], summary="OAuth2 密码模式登录")
        def login_for_access_token(
            request: Request,
            form_data: OAuth2PasswordRequestForm = Depends(),
        ):
            """OAuth2 密码模式登录，获取访问令牌和刷新令牌

            用于 Swagger UI 授权以及标准 OAuth2 客户端。
            """
            client_ip = request.client.host if request.client else "未知"
            user_agent = request.headers.get("User-Agent", "未知")
            result = _do_login(form_data.username, form_data.password, client_ip, user_agent)
            return Resp.OK(result, "OAuth2登录成功")

    if enable_json_login:
        @router.post("/login", response_model=ItemResponse[LoginResponseSchema], summary="用户登录")
        def login(request: Request, login_request: LoginRequest):
            """用户名密码登录，返回访问令牌、刷新令牌和用户信息"""
            client_ip = request.client.host if request.client else "未知"
            user_agent = request.headers.get("User-Agent", "未知")
            result = _do_login(
                login_request.username, login_request.password, client_ip, user_agent
            )
            return Resp.OK(result, "登录成功")

    if enable_refresh:
        @router.post("/refresh", response_model=ItemResponse[RefreshResponseSchema], summary="刷新访问令牌")
        def refresh_access_token(refresh_request: RefreshRequest):
            """使用刷新令牌获取新的访问令牌（支持滑动过期自动续期）"""
            refresh_token_str = refresh_request.refresh_token

            # 检查黑名单
            if token_blacklist and token_blacklist.is_revoked(refresh_token_str):
                raise AuthenticationException("刷新令牌无效或已过期")

            # 使用 jwt_manager.refresh_tokens（支持滑动过期）
            result = jwt_manager.refresh_tokens(
                refresh_token_str,
                user_getter=user_getter,
            )

            if not result:
                raise AuthenticationException("刷新令牌无效或已过期")

            return Resp.OK({
                "access_token": result["access_token"],
                "refresh_token": result.get("refresh_token"),
                "token_type": result["token_type"],
            }, "刷新令牌成功")

    if enable_logout:
        @router.post("/logout", response_model=OkResponse, summary="用户登出")
        def logout(user_id: int):
            """撤销用户的所有令牌"""
            auth_service.logout(user_id)
            return Resp.OK(message="登出成功")

    if enable_kick:
        @router.post("/kick", response_model=OkResponse, summary="踢出用户")
        def kick_user(user_id: int):
            """撤销用户的所有令牌并锁定账户"""
            auth_service.lock_user(user_id)
            return Resp.OK(message="用户已成功踢出")

    return router
