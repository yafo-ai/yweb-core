"""认证服务抽象与默认实现

提供 AbstractAuthService 接口和 BaseAuthService 默认实现，
消除每个项目重复编写认证流程代码的问题。

设计原则:
    - AbstractAuthService 定义标准认证操作接口
    - BaseAuthService 提供基于 JWTManager + PasswordHelper + TokenBlacklist 的默认实现
    - 项目可直接使用 BaseAuthService，或继承后覆写特定方法
    - 通过 AuthSetup.create_auth_service() 便捷创建

使用示例:

    直接使用（最简）::
    
        from yweb.auth import setup_auth
        
        auth = setup_auth(User)
        auth_service = auth.create_auth_service()
        
        # 认证用户
        user = auth_service.authenticate("admin", "password")
        
        # 创建令牌
        access_token = auth_service.create_access_token(user)
        refresh_token = auth_service.create_refresh_token(user)
        
        # 登出
        auth_service.logout(user.id)
    
    独立构造::
    
        from yweb.auth import BaseAuthService, JWTManager, TokenBlacklist
        
        auth_service = BaseAuthService(
            user_model=User,
            jwt_manager=jwt_manager,
            token_blacklist=token_blacklist,
        )
    
    继承自定义::
    
        class MyAuthService(BaseAuthService):
            def get_user_roles(self, user) -> list:
                # 自定义角色提取逻辑
                return [r.code for r in user.custom_roles]
            
            def on_authenticate_failure(self, username, **kwargs):
                super().on_authenticate_failure(username, **kwargs)
                # 额外的失败处理逻辑（如发送告警）
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable, List, Optional, Type

from yweb.log import get_logger

logger = get_logger("yweb.auth.service")


class AbstractAuthService(ABC):
    """认证服务抽象接口
    
    定义标准的认证操作，项目实现此接口即可获得一致的认证行为。
    推荐直接使用 BaseAuthService 默认实现，仅在需要完全自定义时才实现此接口。
    """
    
    @abstractmethod
    def authenticate(self, username: str, password: str) -> Optional[Any]:
        """认证用户
        
        Args:
            username: 用户名
            password: 明文密码
            
        Returns:
            认证成功返回用户对象，失败返回 None
        """
        pass
    
    @abstractmethod
    def create_access_token(self, user) -> str:
        """创建访问令牌
        
        Args:
            user: 用户对象
            
        Returns:
            JWT access token 字符串
        """
        pass
    
    @abstractmethod
    def create_refresh_token(self, user) -> str:
        """创建刷新令牌
        
        Args:
            user: 用户对象
            
        Returns:
            JWT refresh token 字符串
        """
        pass
    
    @abstractmethod
    def verify_token(self, token: str) -> Optional[Any]:
        """验证令牌
        
        Args:
            token: JWT token 字符串
            
        Returns:
            验证成功返回 TokenData，失败返回 None
        """
        pass
    
    @abstractmethod
    def refresh_token(self, refresh_token: str) -> Optional[str]:
        """刷新访问令牌
        
        Args:
            refresh_token: 刷新令牌
            
        Returns:
            新的 access token，失败返回 None
        """
        pass
    
    @abstractmethod
    def logout(self, user_id: int) -> None:
        """用户登出
        
        Args:
            user_id: 用户 ID
        """
        pass
    
    def lock_user(self, user_id: int) -> None:
        """锁定用户（可选实现）
        
        默认不执行任何操作，子类可覆写。
        
        Args:
            user_id: 用户 ID
        """
        pass
    
    def unlock_user(self, user_id: int) -> None:
        """解锁用户（可选实现）
        
        默认不执行任何操作，子类可覆写。
        
        Args:
            user_id: 用户 ID
        """
        pass
    
    def update_last_login(self, user_id: int, **kwargs) -> None:
        """更新最后登录时间（可选实现）
        
        默认不执行任何操作，子类可覆写。
        
        Args:
            user_id: 用户 ID
            **kwargs: 额外参数（如 ip_address, user_agent 等）
        """
        pass


class BaseAuthService(AbstractAuthService):
    """认证服务默认实现
    
    基于 JWTManager + PasswordHelper + TokenBlacklist 提供完整的认证流程。
    覆盖了 80% 项目的常见需求，项目只需覆写特定方法即可。
    
    构造参数:
        user_model: 用户模型类，需继承 AbstractUser 或至少有
            get_by_username()、get()、is_active、username、password_hash 等
        jwt_manager: JWTManager 实例
        token_blacklist: TokenBlacklist 实例（可选，不传则不支持令牌撤销）
        audit_service: LoginAuditService 实例（可选，不传则不记录审计日志）
        roles_getter: 角色提取回调 (user) -> List[str]（可选，也可覆写 get_user_roles 方法）
        login_record_model: 登录记录模型类（可选，传入后自动记录登录成功/失败）
        max_login_attempts: 账户级别最大失败次数，二级防线（默认 20，需 LockableMixin）
        lock_duration_minutes: 账户锁定时长（分钟，默认 30，需 LockableMixin）
        rate_limiter: IP 频率限制器（可选，一级防线，推荐启用）
    
    可覆写的方法:
        - get_user_roles(user): 自定义角色提取逻辑
        - get_failure_reason(username): 自定义认证失败原因判断
        - update_last_login(user_id, **kwargs): 自定义登录记录逻辑
        - on_authenticate_success(user, **kwargs): 认证成功后的钩子
        - on_authenticate_failure(username, **kwargs): 认证失败后的钩子
    
    使用示例:
        # 最简用法
        auth_service = BaseAuthService(
            user_model=User,
            jwt_manager=jwt_manager,
        )
        
        user = auth_service.authenticate("admin", "password123")
        if user:
            token = auth_service.create_access_token(user)
    """
    
    def __init__(
        self,
        user_model: Type,
        jwt_manager: "JWTManager",
        token_blacklist: Optional["TokenBlacklist"] = None,
        audit_service: Optional["LoginAuditService"] = None,
        roles_getter: Optional[Callable] = None,
        login_record_model: Optional[Type] = None,
        max_login_attempts: int = 20,
        lock_duration_minutes: int = 30,
        rate_limiter: Optional["LoginRateLimiter"] = None,
    ):
        self.user_model = user_model
        self.jwt_manager = jwt_manager
        self.token_blacklist = token_blacklist
        self.audit_service = audit_service
        self._roles_getter = roles_getter
        self.login_record_model = login_record_model
        self.max_login_attempts = max_login_attempts
        self.lock_duration_minutes = lock_duration_minutes
        self.rate_limiter = rate_limiter
    
    # ==================== 核心认证方法 ====================
    
    def authenticate(self, username: str, password: str) -> Optional[Any]:
        """认证用户
        
        流程：查找用户 -> 检查账户状态 -> 验证密码
        
        自动检测 LockableMixin：
        - 若用户模型含 LockableMixin，优先使用 can_login 综合判断（含自动解锁过期锁定）
        - 否则仅检查 is_active
        
        Args:
            username: 用户名
            password: 明文密码
            
        Returns:
            认证成功返回用户对象，失败返回 None
        """
        user = self.user_model.get_by_username(username)
        if not user:
            logger.debug(f"认证失败: 用户 '{username}' 不存在")
            return None
        
        # 检查账户状态（锁定检查优先于密码验证，避免无意义的计算）
        if hasattr(user, 'can_login'):
            # LockableMixin: 自动解锁过期的锁定，再判断是否可登录
            if hasattr(user, 'auto_unlock_if_expired'):
                user.auto_unlock_if_expired()
            if not user.can_login:
                reason = "账户已锁定" if getattr(user, 'is_locked', False) else "账户已禁用"
                logger.debug(f"认证失败: 用户 '{username}' {reason}")
                return None
        elif hasattr(user, 'is_active') and not user.is_active:
            logger.debug(f"认证失败: 用户 '{username}' 已被禁用")
            return None
        
        from .password import PasswordHelper
        if not PasswordHelper.verify(password, user.password_hash):
            logger.debug(f"认证失败: 用户 '{username}' 密码错误")
            return None
        
        return user
    
    def get_failure_reason(self, username: str) -> str:
        """判断认证失败的具体原因（仅用于内部日志和登录记录）
        
        当 authenticate() 返回 None 后，调用此方法获取具体失败原因。
        子类可覆写以添加自定义的失败原因判断（如账户锁定、密码过期等）。
        
        注意：此方法会额外查询一次数据库，仅在认证失败时调用。
        返回结果仅用于内部记录，不会暴露给客户端。
        
        Args:
            username: 尝试登录的用户名
            
        Returns:
            失败原因字符串
        """
        try:
            user = self.user_model.get_by_username(username)
            if not user:
                return "用户不存在"
            if hasattr(user, 'is_locked') and user.is_locked:
                return "账户已锁定"
            if hasattr(user, 'is_active') and not user.is_active:
                return "账户已禁用"
            return "密码错误"
        except Exception:
            return "认证失败"
    
    # ==================== 令牌操作 ====================
    
    def create_access_token(self, user) -> str:
        """创建访问令牌
        
        自动提取用户角色并构造 TokenPayload。
        
        Args:
            user: 用户对象
            
        Returns:
            JWT access token 字符串
        """
        from .schemas import TokenPayload
        
        roles = self.get_user_roles(user)
        payload = TokenPayload(
            sub=user.username,
            user_id=user.id,
            username=user.username,
            email=getattr(user, 'email', None),
            roles=roles,
        )
        return self.jwt_manager.create_access_token(payload)
    
    def create_refresh_token(self, user) -> str:
        """创建刷新令牌
        
        Args:
            user: 用户对象
            
        Returns:
            JWT refresh token 字符串
        """
        from .schemas import TokenPayload
        
        payload = TokenPayload(
            sub=user.username,
            user_id=user.id,
            username=user.username,
        )
        return self.jwt_manager.create_refresh_token(payload)
    
    def verify_token(self, token: str) -> Optional[Any]:
        """验证令牌
        
        先检查黑名单（如已配置），再验证 JWT 签名和有效期。
        
        Args:
            token: JWT token 字符串
            
        Returns:
            验证成功返回 TokenData，失败返回 None
        """
        try:
            # 检查黑名单
            if self.token_blacklist and self.token_blacklist.is_revoked(token):
                logger.debug("令牌已被撤销")
                return None
            
            return self.jwt_manager.verify_token(token)
        except Exception as e:
            logger.error(f"验证令牌失败: {e}")
            return None
    
    def refresh_token(self, refresh_token: str) -> Optional[str]:
        """刷新访问令牌
        
        验证 refresh token 有效性，获取用户，创建新的 access token。
        
        Args:
            refresh_token: 刷新令牌
            
        Returns:
            新的 access token，失败返回 None
        """
        try:
            # 验证 refresh token
            token_data = self.verify_token(refresh_token)
            if not token_data:
                return None
            
            # 检查是否是 refresh token 类型
            if getattr(token_data, 'token_type', None) != "refresh":
                return None
            
            # 获取用户
            user = self.user_model.get(token_data.user_id)
            if not user:
                return None
            if hasattr(user, 'is_active') and not user.is_active:
                return None
            
            # 创建新的访问令牌
            return self.create_access_token(user)
        except Exception as e:
            logger.error(f"刷新令牌失败: {e}")
            return None
    
    # ==================== 用户状态管理 ====================
    
    def logout(self, user_id: int) -> None:
        """用户登出
        
        撤销用户的所有令牌。
        
        Args:
            user_id: 用户 ID
        """
        if self.token_blacklist:
            self.token_blacklist.revoke_all_user_tokens(user_id, reason="user_logout")
            logger.info(f"用户登出成功: user_id={user_id}")
        else:
            logger.warning(f"未配置 token_blacklist，无法撤销用户令牌: user_id={user_id}")
    
    def lock_user(self, user_id: int) -> None:
        """锁定用户
        
        设置 is_active=False 并撤销所有令牌。
        
        Args:
            user_id: 用户 ID
        """
        try:
            user = self.user_model.get(user_id)
            if user:
                user.is_active = False
                user.update()
                # 撤销令牌
                if self.token_blacklist:
                    self.token_blacklist.revoke_all_user_tokens(user_id, reason="user_locked")
                logger.info(f"用户已锁定: user_id={user_id}")
        except Exception as e:
            logger.error(f"锁定用户失败: {e}")
    
    def unlock_user(self, user_id: int) -> None:
        """解锁用户
        
        设置 is_active=True。
        
        Args:
            user_id: 用户 ID
        """
        try:
            user = self.user_model.get(user_id)
            if user:
                user.is_active = True
                user.update()
                logger.info(f"用户已解锁: user_id={user_id}")
        except Exception as e:
            logger.error(f"解锁用户失败: {e}")
    
    def update_last_login(self, user_id: int, **kwargs) -> None:
        """更新最后登录时间并创建登录成功记录
        
        若配置了 login_record_model，自动创建登录成功记录。
        若配置了 audit_service，同时记录审计日志。
        子类可覆写此方法添加自定义逻辑。
        
        Args:
            user_id: 用户 ID
            **kwargs: 额外参数，常用的有：
                - ip_address: 客户端 IP
                - user_agent: 客户端 User-Agent
                - status: 登录状态（默认 "success"）
                - failure_reason: 失败原因
        """
        try:
            user = self.user_model.get(user_id)
            if user:
                user.last_login_at = datetime.now()
                user.update()
                
                # 创建登录记录
                if self.login_record_model:
                    status = kwargs.get('status', 'success')
                    record = self.login_record_model(
                        user_id=user_id,
                        username=user.username,
                        ip_address=kwargs.get('ip_address') or '未知',
                        user_agent=kwargs.get('user_agent') or '未知',
                        status=status,
                        failure_reason=kwargs.get('failure_reason'),
                    )
                    self.login_record_model.create_record(record)
                    logger.info(
                        f"登录记录已创建: user_id={user_id}, "
                        f"username={user.username}, status={status}"
                    )
                
                # 记录审计日志
                if self.audit_service:
                    self.audit_service.record_login(
                        user_id=user_id,
                        username=user.username,
                        ip_address=kwargs.get('ip_address', '未知'),
                        user_agent=kwargs.get('user_agent'),
                        status=kwargs.get('status', 'success'),
                        failure_reason=kwargs.get('failure_reason'),
                    )
                
                logger.debug(f"更新最后登录时间: user_id={user_id}")
            else:
                logger.warning(f"更新最后登录时间失败: 未找到用户ID={user_id}")
        except Exception as e:
            logger.error(f"更新最后登录时间失败: {e}", exc_info=True)
    
    # ==================== 可覆写的钩子方法 ====================
    
    def get_user_roles(self, user) -> List[str]:
        """获取用户角色列表
        
        默认行为：
        1. 如果构造时传入了 roles_getter 回调，使用回调
        2. 否则尝试从 user.roles 提取 code 属性
        3. 如果 user 没有 roles 属性，返回空列表
        
        子类可覆写此方法实现自定义角色提取逻辑。
        
        Args:
            user: 用户对象
            
        Returns:
            角色代码列表，如 ["admin", "user"]
        """
        if self._roles_getter:
            return self._roles_getter(user)
        return self._default_roles_getter(user)
    
    @staticmethod
    def _default_roles_getter(user) -> List[str]:
        """默认角色提取逻辑"""
        roles = getattr(user, 'roles', None)
        if roles is None:
            return []
        try:
            return [getattr(r, 'code', str(r)) for r in roles]
        except (TypeError, AttributeError):
            return []
    
    def on_authenticate_success(self, user, **kwargs) -> None:
        """认证成功后的钩子 - 重置失败计数
        
        若用户模型含 LockableMixin，自动重置登录失败计数。
        子类可覆写以添加额外逻辑。
        
        Args:
            user: 认证成功的用户对象
            **kwargs: 额外参数
        """
        # LockableMixin: 登录成功，重置失败计数
        if hasattr(user, 'reset_failed_attempts'):
            user.reset_failed_attempts()
    
    def on_authenticate_failure(self, username: str, **kwargs) -> None:
        """认证失败后的钩子 - 创建失败登录记录 + 累计失败计数
        
        若配置了 login_record_model，自动创建登录失败记录。
        若用户模型含 LockableMixin，自动累计失败次数并在达到阈值时锁定账户。
        子类可覆写以添加额外逻辑（如发送告警等）。
        
        Args:
            username: 尝试登录的用户名
            **kwargs: 额外参数，常用的有：
                - ip_address: 客户端 IP
                - user_agent: 客户端 User-Agent
                - reason: 失败原因（由框架自动传入）
        """
        reason = kwargs.get('reason', '认证失败')
        ip_address = kwargs.get('ip_address') or '未知'
        user_agent = kwargs.get('user_agent') or '未知'
        
        try:
            user = self.user_model.get_by_username(username)
            user_id = user.id if user else 0
            
            # LockableMixin: 累计失败次数，达到阈值自动锁定
            if user and hasattr(user, 'record_failed_login'):
                was_locked = user.record_failed_login(
                    max_attempts=self.max_login_attempts,
                    lock_duration_minutes=self.lock_duration_minutes,
                )
                if was_locked:
                    reason = f"账户已锁定（连续失败{user.failed_login_attempts}次）"
                    logger.warning(f"账户已被自动锁定: username={username}")
            
            # 创建登录失败记录
            if self.login_record_model:
                record = self.login_record_model(
                    user_id=user_id,
                    username=username,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    status='failed',
                    failure_reason=reason,
                )
                self.login_record_model.create_record(record)
                logger.info(
                    f"登录失败记录已创建: username={username}, reason={reason}"
                )
        except Exception as e:
            logger.error(f"认证失败后处理异常: {e}", exc_info=True)


__all__ = [
    "AbstractAuthService",
    "BaseAuthService",
]
