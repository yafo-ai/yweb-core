"""认证一站式设置模块

提供 setup_auth() 便捷函数，一行代码完成认证依赖配置。

使用示例:

    级别1：零配置（最简，推荐）::
    
        from yweb.auth import setup_auth
        from app.domain.auth.model.user import User
        
        auth = setup_auth(User)
        
        # 直接使用
        get_current_user = auth.get_current_user
        get_current_user_optional = auth.get_current_user_optional
    
    级别2：启用角色（零配置角色管理）::
    
        auth = setup_auth(User, role_model=True)
        
        # 框架自动创建 Role 模型 + 中间表 + User.roles relationship
        Role = auth.role_model
        Role.create_role(name="管理员", code="admin")
        
        user = User.get(1)
        user.has_role("admin")  # RoleMixin 自动混入
    
    级别3：自定义角色模型::
    
        from yweb.auth import AbstractSimpleRole
        
        class MyRole(AbstractSimpleRole):
            __tablename__ = "sys_role"
            sort_order = mapped_column(Integer, default=0)
        
        auth = setup_auth(User, role_model=MyRole)
        # 框架自动设置 User.roles + RoleMixin
    
    级别4：轻量自定义::
    
        auth = setup_auth(
            User,
            role_model=True,
            token_url="/api/v1/auth/token",
            cache_ttl=120,
        )
    
    级别5：完全自定义（使用 create_auth_dependency）::
    
        from yweb.auth import create_auth_dependency
        
        get_current_user = create_auth_dependency(
            jwt_manager=my_jwt_manager,
            user_getter=my_custom_getter,
        )
"""

from dataclasses import dataclass, field
from typing import Type, Optional, Callable, Any, Union

from .jwt import JWTManager
from yweb.log import get_logger

logger = get_logger("yweb.auth.setup")


@dataclass
class AuthSetup:
    """认证设置返回对象
    
    包含认证所需的所有组件，通过 setup_auth() 创建。
    
    属性:
        get_current_user: 必须认证的 FastAPI 依赖（未登录抛 401）
        get_current_user_optional: 可选认证的 FastAPI 依赖（未登录返回 None）
        jwt_manager: JWTManager 实例（用于 token 创建/验证/刷新等）
        user_getter: 用户获取函数（可能带缓存）
        role_model: 角色模型类（启用角色时可用，否则为 None）
    
    使用示例:
        auth = setup_auth(User, role_model=True)
        
        # 在路由中使用
        @app.get("/me")
        def get_me(user = Depends(auth.get_current_user)):
            return user
        
        # 角色模型
        Role = auth.role_model
        Role.create_role(name="管理员", code="admin")
        
        # 用户角色操作（RoleMixin 自动混入）
        user.has_role("admin")
        user.role_codes  # {"admin"}
        
        # 挂载预置路由（用户管理 + 登录记录）
        auth.mount_routes(
            app,
            login_record_model=LoginRecord,
            api_prefix="/api/v1",
        )
    """
    get_current_user: Callable
    get_current_user_optional: Callable
    jwt_manager: JWTManager
    user_getter: Callable
    role_model: Optional[Type] = field(default=None)
    
    # 登录记录模型（mount_routes 后可用）
    login_record_model: Optional[Type] = field(default=None, repr=False)
    
    # 认证服务和令牌黑名单（mount_routes 挂载 auth 路由后可用）
    auth_service: Any = field(default=None, repr=False)
    token_blacklist: Any = field(default=None, repr=False)
    
    # 路由引用（mount_routes 后可用）
    user_router: Any = field(default=None, repr=False)
    login_record_router: Any = field(default=None, repr=False)
    auth_router: Any = field(default=None, repr=False)
    
    # 私有：缓存管理引用（有缓存时才可用）
    _cached_func: Any = field(default=None, repr=False)
    # 私有：用户模型引用（用于 create_auth_service）
    _user_model: Type = field(default=None, repr=False)
    
    def invalidate_user_cache(self, user_id: int) -> bool:
        """手动失效单个用户的认证缓存
        
        Args:
            user_id: 用户 ID
            
        Returns:
            是否成功失效
        """
        if self._cached_func is None:
            return False
        return self._cached_func.invalidate(user_id)
    
    def invalidate_users_cache(self, user_ids: list) -> int:
        """手动批量失效用户的认证缓存
        
        Args:
            user_ids: 用户 ID 列表
            
        Returns:
            成功失效的数量
        """
        if self._cached_func is None:
            return 0
        return self._cached_func.invalidate_many(user_ids)
    
    def get_user_cache_stats(self) -> dict:
        """获取用户认证缓存统计信息
        
        Returns:
            缓存统计字典，包含 hits, misses, hit_rate 等。
            未启用缓存时返回空字典。
        """
        if self._cached_func is None:
            return {}
        return self._cached_func.stats()
    
    def create_auth_service(
        self,
        token_blacklist=None,
        audit_service=None,
        roles_getter=None,
        login_record_model=None,
        max_login_attempts: int = 20,
        lock_duration_minutes: int = 30,
        rate_limiter=None,
    ) -> "BaseAuthService":
        """便捷创建 BaseAuthService
        
        自动传入 jwt_manager 和 user_model，只需提供可选的扩展组件。
        
        Args:
            token_blacklist: TokenBlacklist 实例（可选，用于令牌撤销）
            audit_service: LoginAuditService 实例（可选，用于审计日志）
            roles_getter: 角色提取回调 (user) -> List[str]（可选）
            login_record_model: 登录记录模型类（可选，传入后自动记录登录成功/失败）
            max_login_attempts: 账户级别最大失败次数（默认 20，需 LockableMixin）
            lock_duration_minutes: 账户锁定时长（分钟，默认 30，需 LockableMixin）
            rate_limiter: LoginRateLimiter 实例（可选，IP 频率限制）
            
        Returns:
            BaseAuthService 实例
            
        Raises:
            RuntimeError: 未关联 user_model 时（不应出现，setup_auth 会自动设置）
        
        使用示例:
            auth = setup_auth(User)
            
            # 最简用法
            auth_service = auth.create_auth_service()
            
            # 带黑名单和审计
            from yweb.auth import configure_token_blacklist, LoginAuditService
            blacklist = configure_token_blacklist(jwt_manager=auth.jwt_manager)
            audit = LoginAuditService(LoginRecord)
            
            auth_service = auth.create_auth_service(
                token_blacklist=blacklist,
                audit_service=audit,
            )
        """
        if self._user_model is None:
            raise RuntimeError(
                "AuthSetup 未关联 user_model，无法创建 auth_service。"
                "请通过 setup_auth(User) 创建 AuthSetup 实例。"
            )
        
        from .service import BaseAuthService
        
        return BaseAuthService(
            user_model=self._user_model,
            jwt_manager=self.jwt_manager,
            token_blacklist=token_blacklist,
            audit_service=audit_service,
            roles_getter=roles_getter,
            login_record_model=login_record_model,
            max_login_attempts=max_login_attempts,
            lock_duration_minutes=lock_duration_minutes,
            rate_limiter=rate_limiter,
        )
    
    def mount_routes(
        self,
        app,
        login_record_model: Union[bool, Type, None] = None,
        login_record_table_name: Optional[str] = None,
        api_prefix: str = "/api/v1",
        user_prefix: str = "/users",
        user_tags: Optional[list] = None,
        user_dependencies: Optional[list] = None,
        login_record_prefix: str = "/login-records",
        login_record_tags: Optional[list] = None,
        login_record_dependencies: Optional[list] = None,
        # Auth 路由参数
        auth_routes: Union[bool, None] = None,
        auth_service: Optional[Any] = None,
        auth_service_class: Optional[Type] = None,
        token_blacklist: Union[bool, Any, None] = None,
        auth_prefix: str = "/auth",
        auth_tags: Optional[list] = None,
        auth_dependencies: Optional[list] = None,
        enable_oauth2_token: bool = True,
        enable_json_login: bool = True,
        enable_refresh: bool = True,
        enable_logout: bool = True,
        enable_kick: bool = False,
        login_response_builder: Optional[Callable] = None,
        user_response_dto: Optional[Type] = None,
        max_login_attempts: int = 20,
        lock_duration_minutes: int = 30,
        ip_max_attempts: int = 10,
        ip_block_minutes: int = 15,
    ) -> None:
        """挂载认证相关的预置路由到 FastAPI 应用
        
        在 app 创建后调用，将用户管理、登录记录和认证端点路由挂载到应用。
        与 setup_organization(app=app, ...) 风格一致，统一在 main.py 中管理。
        
        Args:
            app: FastAPI 应用实例
            login_record_model: 登录记录模型配置。支持以下类型：
                - None/False: 不挂载登录记录路由
                - True: 自动创建 LoginRecord 模型（从 user_model 推导表名前缀）
                - AbstractLoginRecord 子类: 使用自定义 LoginRecord
            login_record_table_name: 登录记录表名（仅 login_record_model=True 时生效）
            api_prefix: API 路由前缀（默认 "/api/v1"）
            user_prefix: 用户路由子前缀（默认 "/users"）
            user_tags: 用户路由 OpenAPI 标签
            user_dependencies: 用户路由依赖（如权限检查）
            login_record_prefix: 登录记录路由子前缀（默认 "/login-records"）
            login_record_tags: 登录记录路由 OpenAPI 标签
            login_record_dependencies: 登录记录路由依赖（如权限检查）
            auth_routes: 是否挂载认证端点路由（登录/登出/刷新/踢出）。
                - None/False: 不挂载
                - True: 挂载认证端点路由
            auth_service: BaseAuthService 实例（可选，优先使用）
            auth_service_class: BaseAuthService 子类（可选，框架自动实例化）
            token_blacklist: 令牌黑名单配置。支持以下类型：
                - None/False: 不使用黑名单
                - True: 自动创建 InMemoryTokenStore + TokenBlacklist
                - TokenBlacklist 实例: 直接使用
            auth_prefix: 认证路由子前缀（默认 "/auth"）
            auth_tags: 认证路由 OpenAPI 标签
            auth_dependencies: 认证路由依赖
            enable_oauth2_token: 是否启用 POST /token（OAuth2 密码模式）
            enable_json_login: 是否启用 POST /login（JSON 登录）
            enable_refresh: 是否启用 POST /refresh（刷新令牌）
            enable_logout: 是否启用 POST /logout（登出）
            enable_kick: 是否启用 POST /kick（踢出用户，默认关闭）
            login_response_builder: 自定义登录响应构建函数
            user_response_dto: 自定义用户响应 DTO 类型
        
        使用示例::
        
            # 最简用法（自动创建 LoginRecord + 认证路由）
            auth.mount_routes(app, login_record_model=True, auth_routes=True)
            
            # 使用自定义 auth_service
            auth.mount_routes(
                app,
                login_record_model=LoginRecord,
                auth_routes=True,
                auth_service_class=MyAuthService,
                token_blacklist=True,
            )
            
            # 只挂载用户管理（不挂载登录记录和认证路由）
            auth.mount_routes(app, login_record_model=False, auth_routes=False)
        """
        from .api import create_user_router, create_login_record_router
        
        # 用户管理路由
        self.user_router = create_user_router(self._user_model)
        app.include_router(
            self.user_router,
            prefix=f"{api_prefix}{user_prefix}",
            tags=user_tags or ["users"],
            dependencies=user_dependencies or [],
        )
        
        # 登录记录路由（可选）
        if login_record_model and login_record_model is not False:
            # 解析 login_record_model（True → 动态创建，类 → 直接使用）
            if login_record_model is True:
                resolved = _resolve_login_record_model(
                    login_record_model=True,
                    user_model=self._user_model,
                    login_record_table_name=login_record_table_name,
                )
            elif isinstance(login_record_model, type):
                # 已经是类，直接使用（从 setup_auth 传入或用户直接指定）
                resolved = login_record_model
            else:
                raise ValueError(
                    f"login_record_model 必须是 True 或 AbstractLoginRecord 子类，"
                    f"当前传入: {login_record_model}"
                )
            self.login_record_model = resolved
            self.login_record_router = create_login_record_router(resolved)
            app.include_router(
                self.login_record_router,
                prefix=f"{api_prefix}{login_record_prefix}",
                tags=login_record_tags or ["login-records"],
                dependencies=login_record_dependencies or [],
            )
        
        # 认证端点路由（可选）
        if auth_routes:
            self._mount_auth_routes(
                app=app,
                api_prefix=api_prefix,
                auth_service=auth_service,
                auth_service_class=auth_service_class,
                token_blacklist=token_blacklist,
                auth_prefix=auth_prefix,
                auth_tags=auth_tags,
                auth_dependencies=auth_dependencies,
                enable_oauth2_token=enable_oauth2_token,
                enable_json_login=enable_json_login,
                enable_refresh=enable_refresh,
                enable_logout=enable_logout,
                enable_kick=enable_kick,
                login_response_builder=login_response_builder,
                user_response_dto=user_response_dto,
                max_login_attempts=max_login_attempts,
                lock_duration_minutes=lock_duration_minutes,
                ip_max_attempts=ip_max_attempts,
                ip_block_minutes=ip_block_minutes,
            )
    
    def _mount_auth_routes(
        self,
        app,
        api_prefix: str,
        auth_service: Optional[Any] = None,
        auth_service_class: Optional[Type] = None,
        token_blacklist: Union[bool, Any, None] = None,
        auth_prefix: str = "/auth",
        auth_tags: Optional[list] = None,
        auth_dependencies: Optional[list] = None,
        enable_oauth2_token: bool = True,
        enable_json_login: bool = True,
        enable_refresh: bool = True,
        enable_logout: bool = True,
        enable_kick: bool = False,
        login_response_builder: Optional[Callable] = None,
        user_response_dto: Optional[Type] = None,
        max_login_attempts: int = 20,
        lock_duration_minutes: int = 30,
        ip_max_attempts: int = 10,
        ip_block_minutes: int = 15,
    ) -> None:
        """内部方法：解析参数并挂载认证端点路由"""
        from .api import create_auth_router
        
        # 1. 解析 token_blacklist
        resolved_blacklist = None
        if token_blacklist is True:
            from .token_store import InMemoryTokenStore, configure_token_blacklist
            resolved_blacklist = configure_token_blacklist(
                store=InMemoryTokenStore(),
                jwt_manager=self.jwt_manager,
            )
            logger.info("自动创建内存令牌黑名单")
        elif token_blacklist and token_blacklist is not False:
            # 已经是 TokenBlacklist 实例
            resolved_blacklist = token_blacklist
        
        # 2. 创建 IP 频率限制器
        resolved_rate_limiter = None
        if ip_max_attempts and ip_max_attempts > 0:
            from .rate_limiter import LoginRateLimiter
            resolved_rate_limiter = LoginRateLimiter(
                max_attempts=ip_max_attempts,
                block_minutes=ip_block_minutes,
            )
            logger.info(
                f"IP 频率限制已启用: {ip_max_attempts}次/{ip_block_minutes}分钟"
            )
        
        # 3. 解析 auth_service（优先级：实例 > class > 默认创建）
        resolved_service = None
        if auth_service is not None:
            resolved_service = auth_service
        elif auth_service_class is not None:
            resolved_service = auth_service_class(
                user_model=self._user_model,
                jwt_manager=self.jwt_manager,
                token_blacklist=resolved_blacklist,
                login_record_model=self.login_record_model,
                max_login_attempts=max_login_attempts,
                lock_duration_minutes=lock_duration_minutes,
                rate_limiter=resolved_rate_limiter,
            )
            logger.info(f"使用自定义认证服务类: {auth_service_class.__name__}")
        else:
            resolved_service = self.create_auth_service(
                token_blacklist=resolved_blacklist,
                login_record_model=self.login_record_model,
                max_login_attempts=max_login_attempts,
                lock_duration_minutes=lock_duration_minutes,
                rate_limiter=resolved_rate_limiter,
            )
            logger.info("自动创建默认认证服务 (BaseAuthService)")
        
        # 3. 存储引用
        self.auth_service = resolved_service
        self.token_blacklist = resolved_blacklist
        
        # 4. 创建并挂载路由
        self.auth_router = create_auth_router(
            auth_service=resolved_service,
            jwt_manager=self.jwt_manager,
            token_blacklist=resolved_blacklist,
            user_getter=self.user_getter,
            enable_oauth2_token=enable_oauth2_token,
            enable_json_login=enable_json_login,
            enable_refresh=enable_refresh,
            enable_logout=enable_logout,
            enable_kick=enable_kick,
            login_response_builder=login_response_builder,
            user_response_dto=user_response_dto,
        )
        app.include_router(
            self.auth_router,
            prefix=f"{api_prefix}{auth_prefix}",
            tags=auth_tags or ["auth"],
            dependencies=auth_dependencies or [],
        )
        logger.info(f"认证端点路由已挂载: {api_prefix}{auth_prefix}")


def setup_auth(
    user_model: Type,
    jwt_settings=None,
    token_url: Optional[str] = None,
    active_field: Optional[str] = "is_active",
    cache_ttl: int = 60,
    role_model: Union[bool, Type, None] = None,
    role_table_name: Optional[str] = None,
    role_assoc_table_name: Optional[str] = None,
    # 路由挂载（可选，提供 app 时自动挂载）
    app=None,
    login_record_model: Union[bool, Type, None] = None,
    login_record_table_name: Optional[str] = None,
    api_prefix: str = "/api/v1",
    user_prefix: str = "/users",
    user_tags: Optional[list] = None,
    user_dependencies: Optional[list] = None,
    login_record_prefix: str = "/login-records",
    login_record_tags: Optional[list] = None,
    login_record_dependencies: Optional[list] = None,
    login_record_require_auth: bool = True,
    # Auth 路由（可选，提供 app 时自动挂载）
    auth_routes: Union[bool, None] = None,
    auth_service: Optional[Any] = None,
    auth_service_class: Optional[Type] = None,
    token_blacklist: Union[bool, Any, None] = None,
    auth_prefix: str = "/auth",
    auth_tags: Optional[list] = None,
    auth_dependencies: Optional[list] = None,
    enable_oauth2_token: bool = True,
    enable_json_login: bool = True,
    enable_refresh: bool = True,
    enable_logout: bool = True,
    enable_kick: bool = False,
    login_response_builder: Optional[Callable] = None,
    user_response_dto: Optional[Type] = None,
    max_login_attempts: int = 20,
    lock_duration_minutes: int = 30,
    ip_max_attempts: int = 10,
    ip_block_minutes: int = 15,
) -> AuthSetup:
    """一站式认证设置
    
    自动完成以下步骤：
    1. 从 jwt_settings（或 settings.jwt）创建 JWTManager
    2. （可选）设置角色模型和 User.roles 关系
    3. 创建 user_getter（带可选缓存和活跃状态检查）
    4. 创建 get_current_user 和 get_current_user_optional 依赖
    5. （可选）提供 app 时，自动挂载用户管理、登录记录和认证端点路由
    
    Args:
        user_model: 用户模型类，需有 .get(id) 类方法（CoreModel 内置）
        jwt_settings: JWT 配置。支持以下类型：
            - None: 自动从 app.config.settings.jwt 读取
            - JWTSettings 实例: 直接使用（推荐显式传入）
            - dict: 作为 JWTManager 构造参数
        token_url: OAuth2 tokenUrl，影响 Swagger UI 的登录地址。
            默认自动推导：提供 app 时为 "{api_prefix}/auth/token"，否则为 "token"
        active_field: 用户活跃状态字段名。
            默认 "is_active"，设为 None 则不检查活跃状态
        cache_ttl: 用户查询缓存秒数。
            默认 60 秒，设为 0 则不缓存
        role_model: 角色模型配置。支持以下类型：
            - None: 提供 app 时默认 True（一站式模式自动启用角色），否则不启用
            - False: 明确不启用角色
            - True: 自动创建 Role 模型 + 设置 User.roles 关系 + 混入 RoleMixin
            - AbstractSimpleRole 子类: 使用自定义 Role + 自动设置 User.roles 关系 + 混入 RoleMixin
        role_table_name: 角色表名（仅 role_model=True 时生效，默认 "role"）
        role_assoc_table_name: 用户-角色关联表名（默认 "user_role"）
        app: FastAPI 应用实例（可选）。提供时自动挂载路由。
        login_record_model: 登录记录模型配置。支持以下类型：
            - None: 提供 app 时默认 True（一站式模式自动启用登录记录），否则不启用
            - False: 明确不启用登录记录路由
            - True: 自动创建 LoginRecord 模型（从 user_model 推导表名前缀）
            - AbstractLoginRecord 子类: 使用自定义 LoginRecord
        login_record_table_name: 登录记录表名（仅 login_record_model=True 时生效）
        api_prefix: API 路由前缀（默认 "/api/v1"）
        user_prefix: 用户路由子前缀（默认 "/users"）
        user_tags: 用户路由 OpenAPI 标签
        user_dependencies: 用户路由依赖
        login_record_prefix: 登录记录路由子前缀（默认 "/login-records"）
        login_record_tags: 登录记录路由 OpenAPI 标签
        login_record_dependencies: 登录记录路由依赖（优先级高于 login_record_require_auth）
        login_record_require_auth: 登录记录路由是否需要认证（默认 True）
        auth_routes: 是否挂载认证端点路由。
            - None: 提供 app 时默认 True，否则不启用
            - False: 明确不启用
            - True: 挂载认证端点路由（登录/登出/刷新/踢出）
        auth_service: BaseAuthService 实例（可选，优先使用）
        auth_service_class: BaseAuthService 子类（可选，框架自动实例化）
        token_blacklist: 令牌黑名单配置。
            - None: 启用 auth_routes 时默认 True
            - False: 不使用黑名单
            - True: 自动创建 InMemoryTokenStore + TokenBlacklist
            - TokenBlacklist 实例: 直接使用
        auth_prefix: 认证路由子前缀（默认 "/auth"）
        auth_tags: 认证路由 OpenAPI 标签
        auth_dependencies: 认证路由依赖
        enable_oauth2_token: 是否启用 POST /token（默认 True）
        enable_json_login: 是否启用 POST /login（默认 True）
        enable_refresh: 是否启用 POST /refresh（默认 True）
        enable_logout: 是否启用 POST /logout（默认 True）
        enable_kick: 是否启用 POST /kick（默认 False）
        login_response_builder: 自定义登录响应构建函数
        user_response_dto: 自定义用户响应 DTO 类型
        max_login_attempts: 账户级别最大失败次数，二级防线（默认 20，需 LockableMixin）
        lock_duration_minutes: 账户锁定时长（分钟，默认 30，需 LockableMixin）
        ip_max_attempts: 同一 IP 最大失败次数，一级防线（默认 10，0 为禁用）
        ip_block_minutes: IP 封锁时长（分钟，默认 15）
    
    Returns:
        AuthSetup 对象，包含认证依赖、auth_service、token_blacklist 等
    
    使用示例:
        # 最简用法（不挂载路由）
        auth = setup_auth(User)
        
        # 一站式最简：全部自动（角色 + 登录记录 + 认证路由自动挂载）
        auth = setup_auth(app=app, user_model=User, jwt_settings=settings.jwt)
        
        # 一站式：使用自定义 AuthService 和 LoginRecord
        auth = setup_auth(
            app=app,
            user_model=User,
            login_record_model=LoginRecord,
            jwt_settings=settings.jwt,
            auth_service_class=MyAuthService,
            token_blacklist=True,
            enable_kick=True,
        )
        
        # 一站式：不启用认证路由（手动写登录端点）
        auth = setup_auth(app=app, user_model=User, auth_routes=False)
        
        # 不挂载路由（向后兼容，后续可手动调用 auth.mount_routes）
        auth = setup_auth(User, role_model=True)
        auth.mount_routes(app=app, login_record_model=True, auth_routes=True)
    
    Raises:
        ImportError: python-jose 未安装时
        ValueError: jwt_settings 配置无效时
    """
    # 0. 推导默认值（一站式模式：提供 app 时）
    if token_url is None:
        token_url = f"{api_prefix}/auth/token" if app is not None else "token"
    if role_model is None and app is not None:
        role_model = True
    if login_record_model is None and app is not None:
        login_record_model = True
    if auth_routes is None and app is not None:
        auth_routes = True
    if token_blacklist is None and auth_routes:
        token_blacklist = True
    
    # 1. 创建 JWTManager
    jwt_mgr = _create_jwt_manager(jwt_settings)
    
    # 2. （可选）设置角色
    resolved_role_model = None
    if role_model:
        resolved_role_model = _setup_roles(
            user_model=user_model,
            role_model=role_model,
            role_table_name=role_table_name,
            role_assoc_table_name=role_assoc_table_name,
        )
    
    # 3. 创建 user_getter
    user_getter, cached_func = _create_user_getter(
        user_model=user_model,
        active_field=active_field,
        cache_ttl=cache_ttl,
    )
    
    # 4. 创建认证依赖
    get_current_user, get_current_user_optional = _create_auth_dependencies(
        jwt_manager=jwt_mgr,
        user_getter=user_getter,
        token_url=token_url,
    )
    
    role_info = f", role_model={resolved_role_model.__name__}" if resolved_role_model else ""
    logger.info(
        f"认证设置完成: user_model={user_model.__name__}, "
        f"token_url={token_url}, cache_ttl={cache_ttl}s, "
        f"active_field={active_field}{role_info}"
    )
    
    auth_setup = AuthSetup(
        get_current_user=get_current_user,
        get_current_user_optional=get_current_user_optional,
        jwt_manager=jwt_mgr,
        user_getter=user_getter,
        role_model=resolved_role_model,
        _cached_func=cached_func,
        _user_model=user_model,
    )
    
    # 5. （可选）挂载路由
    if app is not None:
        # 解析 login_record_model（True → 动态创建）
        resolved_login_record = None
        if login_record_model and login_record_model is not False:
            resolved_login_record = _resolve_login_record_model(
                login_record_model=login_record_model,
                user_model=user_model,
                login_record_table_name=login_record_table_name,
            )
            auth_setup.login_record_model = resolved_login_record
        
        # login_record_require_auth: 自动用 get_current_user 作为登录记录依赖
        if login_record_dependencies is None and login_record_require_auth:
            from fastapi import Depends
            login_record_dependencies = [Depends(get_current_user)]
        
        auth_setup.mount_routes(
            app=app,
            login_record_model=resolved_login_record,
            api_prefix=api_prefix,
            user_prefix=user_prefix,
            user_tags=user_tags,
            user_dependencies=user_dependencies,
            login_record_prefix=login_record_prefix,
            login_record_tags=login_record_tags,
            login_record_dependencies=login_record_dependencies,
            # Auth 路由参数
            auth_routes=auth_routes,
            auth_service=auth_service,
            auth_service_class=auth_service_class,
            token_blacklist=token_blacklist,
            auth_prefix=auth_prefix,
            auth_tags=auth_tags,
            auth_dependencies=auth_dependencies,
            enable_oauth2_token=enable_oauth2_token,
            enable_json_login=enable_json_login,
            enable_refresh=enable_refresh,
            enable_logout=enable_logout,
            enable_kick=enable_kick,
            login_response_builder=login_response_builder,
            user_response_dto=user_response_dto,
            max_login_attempts=max_login_attempts,
            lock_duration_minutes=lock_duration_minutes,
            ip_max_attempts=ip_max_attempts,
            ip_block_minutes=ip_block_minutes,
        )
    
    return auth_setup


# ==================== 内部函数 ====================


def _setup_roles(
    user_model: Type,
    role_model: Union[bool, Type],
    role_table_name: Optional[str],
    role_assoc_table_name: Optional[str],
) -> Type:
    """设置角色模型和 User.roles 关系
    
    处理三件事：
    1. 确定 Role 模型（动态创建或使用传入的）
    2. 在 User 上设置 roles = ManyToMany(Role, UNLINK)
    3. 确保 User 有 RoleMixin 的方法
    
    Args:
        user_model: 用户模型类
        role_model: True（自动创建）或 AbstractSimpleRole 子类（自定义）
        role_table_name: 角色表名
        role_assoc_table_name: 关联表名
        
    Returns:
        解析后的 Role 模型类
    """
    from .models import AbstractSimpleRole, RoleMixin
    
    # 从 user_model.__tablename__ 推导表名前缀
    # 例: "sys_user" → "sys_", "user" → "", "t_user" → "t_"
    table_prefix = _detect_table_prefix(user_model)
    
    # 1. 确定 Role 模型
    if role_model is True:
        # 动态创建 Role 类
        tablename = role_table_name or f"{table_prefix}role"
        resolved_role = type("Role", (AbstractSimpleRole,), {
            "__tablename__": tablename,
            "__table_args__": {"extend_existing": True},
        })
        logger.info(f"动态创建角色模型: Role (table={tablename})")
    else:
        # 使用传入的自定义 Role
        if not (isinstance(role_model, type) and issubclass(role_model, AbstractSimpleRole)):
            raise ValueError(
                f"role_model 必须是 True 或 AbstractSimpleRole 子类，"
                f"当前传入: {role_model}"
            )
        resolved_role = role_model
        logger.info(f"使用自定义角色模型: {resolved_role.__name__}")
    
    # 2. 在 User 上设置 roles relationship（如果尚未定义）
    if not _has_roles_relationship(user_model):
        assoc_table = role_assoc_table_name or f"{table_prefix}user_role"
        _add_roles_relationship(user_model, resolved_role, assoc_table)
        logger.info(
            f"自动设置 {user_model.__name__}.roles = "
            f"ManyToMany({resolved_role.__name__}, table={assoc_table})"
        )
    else:
        logger.debug(
            f"{user_model.__name__} 已定义 roles relationship，跳过自动设置"
        )
    
    # 3. 确保 User 有 RoleMixin 的方法
    if not _has_role_mixin(user_model):
        _inject_role_mixin(user_model, RoleMixin)
        logger.info(f"自动混入 RoleMixin 到 {user_model.__name__}")
    
    return resolved_role


def _detect_table_prefix(user_model: Type) -> str:
    """从 user_model.__tablename__ 推导表名前缀
    
    规则：如果表名以 "user" 结尾，则前缀为去掉 "user" 后的部分。
    
    示例:
        "sys_user" → "sys_"
        "t_user"   → "t_"
        "user"     → ""
        "account"  → ""（不以 "user" 结尾，无法推导）
    """
    tablename = getattr(user_model, '__tablename__', '') or ''
    if tablename.endswith("user"):
        return tablename[:-len("user")]
    return ""


def _resolve_login_record_model(
    login_record_model: Union[bool, Type],
    user_model: Type,
    login_record_table_name: Optional[str] = None,
) -> Type:
    """解析登录记录模型
    
    处理 login_record_model 参数：
    - True: 动态创建 LoginRecord 类（从 user_model 推导表名前缀）
    - AbstractLoginRecord 子类: 直接使用
    
    Args:
        login_record_model: True 或 AbstractLoginRecord 子类
        user_model: 用户模型类（用于推导表名前缀）
        login_record_table_name: 登录记录表名（仅 login_record_model=True 时生效）
    
    Returns:
        解析后的 LoginRecord 模型类
    """
    from .models import AbstractLoginRecord
    
    table_prefix = _detect_table_prefix(user_model)
    
    if login_record_model is True:
        # 动态创建 LoginRecord 类
        tablename = login_record_table_name or f"{table_prefix}login_record"
        resolved = type("LoginRecord", (AbstractLoginRecord,), {
            "__tablename__": tablename,
            "__table_args__": {"extend_existing": True},
        })
        logger.info(f"动态创建登录记录模型: LoginRecord (table={tablename})")
    else:
        # 使用传入的自定义 LoginRecord
        if not (isinstance(login_record_model, type) and issubclass(login_record_model, AbstractLoginRecord)):
            raise ValueError(
                f"login_record_model 必须是 True 或 AbstractLoginRecord 子类，"
                f"当前传入: {login_record_model}"
            )
        resolved = login_record_model
        logger.info(f"使用自定义登录记录模型: {resolved.__name__}")
    
    return resolved


def _has_roles_relationship(user_model: Type) -> bool:
    """检查 User 模型是否已定义 roles relationship"""
    from sqlalchemy.orm import RelationshipProperty
    from sqlalchemy import inspect as sa_inspect
    
    # 检查是否已有 roles 属性（relationship 或 fields.ManyToMany 配置）
    roles_attr = vars(user_model).get('roles')
    if roles_attr is not None:
        return True
    
    # 检查 mapper 上是否有（可能来自父类）
    try:
        mapper = sa_inspect(user_model)
        if 'roles' in mapper.relationships:
            return True
    except Exception:
        pass
    
    return False


def _add_roles_relationship(user_model: Type, role_model: Type, assoc_table_name: str):
    """动态在 User 模型上添加 roles = ManyToMany(Role, UNLINK)"""
    from yweb.orm import fields
    
    # 设置 ManyToMany 配置
    m2m_config = fields.ManyToMany(
        role_model,
        on_delete=fields.UNLINK,
        table_name=assoc_table_name,
    )
    setattr(user_model, 'roles', m2m_config)
    
    # 触发 fields 处理（正常流程在 __init_subclass__ 中触发，
    # 但动态添加时需要手动触发）
    from yweb.orm.fields import process_relationship_fields
    process_relationship_fields(user_model)


def _has_role_mixin(user_model: Type) -> bool:
    """检查 User 是否已有 RoleMixin 的方法"""
    return hasattr(user_model, 'has_role') and hasattr(user_model, 'role_codes')


def _inject_role_mixin(user_model: Type, role_mixin: Type):
    """动态将 RoleMixin 的方法注入到 User 模型"""
    for attr_name in ('has_role', 'has_any_role', 'has_all_roles',
                       'add_role', 'remove_role'):
        method = getattr(role_mixin, attr_name, None)
        if method and not hasattr(user_model, attr_name):
            setattr(user_model, attr_name, method)
    
    # role_codes 是 property，需要特殊处理
    if not _has_property(user_model, 'role_codes'):
        prop = getattr(role_mixin, 'role_codes', None)
        if prop:
            setattr(user_model, 'role_codes', prop)


def _has_property(cls: Type, name: str) -> bool:
    """检查类是否有指定的 property"""
    for klass in cls.__mro__:
        if name in klass.__dict__ and isinstance(klass.__dict__[name], property):
            return True
    return False


def _create_jwt_manager(jwt_settings) -> JWTManager:
    """从配置创建 JWTManager"""
    if jwt_settings is None:
        # 尝试常见的配置位置
        jwt_conf = None
        
        # 优先尝试 app.config.settings（用户项目的标准位置）
        for module_path in ("app.config", "config"):
            try:
                import importlib
                mod = importlib.import_module(module_path)
                settings_obj = getattr(mod, "settings", None)
                if settings_obj and hasattr(settings_obj, "jwt"):
                    jwt_conf = settings_obj.jwt
                    break
            except (ImportError, AttributeError):
                continue
        
        if jwt_conf is None:
            raise RuntimeError(
                "无法自动获取 JWT 配置。请通过以下方式之一提供：\n"
                "  1. 在 app/config.py 中定义 settings.jwt（推荐）\n"
                "  2. 手动传入 jwt_settings 参数，例如：\n"
                "     setup_auth(User, jwt_settings={'secret_key': 'your-key'})"
            )
        
        return JWTManager(
            secret_key=jwt_conf.secret_key,
            algorithm=jwt_conf.algorithm,
            access_token_expire_minutes=jwt_conf.access_token_expire_minutes,
            refresh_token_expire_days=jwt_conf.refresh_token_expire_days,
            refresh_token_sliding_days=getattr(jwt_conf, 'refresh_token_sliding_days', 2),
        )
    
    elif isinstance(jwt_settings, dict):
        return JWTManager(**jwt_settings)
    
    elif hasattr(jwt_settings, 'secret_key'):
        # JWTSettings 或类似对象
        return JWTManager(
            secret_key=jwt_settings.secret_key,
            algorithm=getattr(jwt_settings, 'algorithm', 'HS256'),
            access_token_expire_minutes=getattr(jwt_settings, 'access_token_expire_minutes', 30),
            refresh_token_expire_days=getattr(jwt_settings, 'refresh_token_expire_days', 7),
            refresh_token_sliding_days=getattr(jwt_settings, 'refresh_token_sliding_days', 2),
        )
    
    else:
        raise ValueError(
            f"jwt_settings 类型不支持: {type(jwt_settings)}。"
            "请传入 None（自动读取）、dict 或 JWTSettings 实例。"
        )


def _create_user_getter(
    user_model: Type,
    active_field: Optional[str],
    cache_ttl: int,
):
    """创建用户获取函数（可选缓存 + 活跃检查）
    
    Returns:
        (user_getter, cached_func) 元组。cached_func 在无缓存时为 None。
    """
    def _get_user(user_id: int):
        user = user_model.get(user_id)
        if user is None:
            return None
        if active_field and not getattr(user, active_field, True):
            return None
        return user
    
    if cache_ttl > 0:
        try:
            from yweb.cache import cached, cache_invalidator
        except ImportError:
            logger.warning("yweb.cache 不可用，跳过缓存配置")
            return _get_user, None
        
        # 用 cached 装饰器包装
        cached_get_user = cached(
            ttl=cache_ttl,
            key_prefix="user:auth",
        )(_get_user)
        
        # 注册自动缓存失效
        cache_invalidator.register(user_model, cached_get_user)
        
        return cached_get_user, cached_get_user
    
    return _get_user, None


def _create_auth_dependencies(
    jwt_manager: JWTManager,
    user_getter: Callable,
    token_url: str,
):
    """创建认证依赖函数对（必须认证 + 可选认证）
    
    Returns:
        (get_current_user, get_current_user_optional) 元组
    """
    from fastapi import Depends
    from fastapi.security import OAuth2PasswordBearer
    from yweb.exceptions import AuthenticationException, ErrorCode
    
    # 创建自定义 token_url 的 OAuth2 scheme
    oauth2 = OAuth2PasswordBearer(tokenUrl=token_url, auto_error=False)
    
    def _make_dependency(auto_error: bool):
        def dependency(token: Optional[str] = Depends(oauth2)):
            if not token:
                if auto_error:
                    raise AuthenticationException(
                        "未提供认证凭证",
                        code=ErrorCode.AUTHENTICATION_FAILED,
                    )
                return None
            
            # raise_on_expired=auto_error：必须认证时区分过期/无效，
            # 可选认证时静默返回 None
            # Token 过期 → AuthenticationException(TOKEN_EXPIRED)
            # Token 无效 → 返回 None，下面统一处理
            token_data = jwt_manager.verify_token(
                token, raise_on_expired=auto_error
            )
            if not token_data or not token_data.user_id:
                if auto_error:
                    raise AuthenticationException(
                        "无效的访问令牌",
                        code=ErrorCode.INVALID_TOKEN,
                    )
                return None
            
            if token_data.token_type != "access":
                if auto_error:
                    raise AuthenticationException(
                        "无效的访问令牌",
                        code=ErrorCode.INVALID_TOKEN,
                    )
                return None
            
            user = user_getter(token_data.user_id)
            if not user:
                if auto_error:
                    raise AuthenticationException(
                        "无法验证凭证",
                        code=ErrorCode.AUTHENTICATION_FAILED,
                    )
                return None
            
            return user
        
        return dependency
    
    return _make_dependency(auto_error=True), _make_dependency(auto_error=False)
