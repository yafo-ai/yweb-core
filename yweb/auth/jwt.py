"""JWT 工具模块

提供 JWT Token 的创建和验证功能。

使用示例:
    from yweb.auth import JWTManager, TokenPayload
    
    # 创建 JWT 管理器
    jwt_manager = JWTManager(
        secret_key="your-secret-key",
        algorithm="HS256",
        access_token_expire_minutes=30,
        refresh_token_expire_days=7
    )
    
    # 创建 Token
    payload = TokenPayload(
        sub="john",
        user_id=1,
        username="john",
        roles=["admin"]
    )
    access_token = jwt_manager.create_access_token(payload)
    refresh_token = jwt_manager.create_refresh_token(payload)
    
    # 验证 Token
    decoded = jwt_manager.verify_token(access_token)
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Union
from dataclasses import asdict

from .schemas import TokenPayload, TokenData

# 尝试导入 jose，如果没有安装则提供友好提示
try:
    from jose import jwt, JWTError, ExpiredSignatureError
    JOSE_AVAILABLE = True
except ImportError:
    JOSE_AVAILABLE = False
    JWTError = Exception  # 占位符
    ExpiredSignatureError = Exception  # 占位符


class JWTManager:
    """JWT 管理器
    
    提供 JWT Token 的创建、验证和刷新功能。
    
    Args:
        secret_key: JWT 密钥
        algorithm: 加密算法，默认 HS256
        access_token_expire_minutes: 访问令牌过期时间（分钟）
        refresh_token_expire_days: 刷新令牌过期时间（天）
        refresh_token_sliding_days: Refresh Token 滑动过期阈值（天），
                                    当用 Refresh Token 换取新 Access Token 时，
                                    如果剩余时间少于此值，也会返回新的 Refresh Token
    
    使用示例:
        jwt_manager = JWTManager(
            secret_key="your-secret-key",
            algorithm="HS256",
            access_token_expire_minutes=30,
            refresh_token_expire_days=7,
            refresh_token_sliding_days=2  # Refresh Token 剩余 2 天时自动续期
        )
        
        # 创建 Token
        access_token = jwt_manager.create_access_token(payload)
        refresh_token = jwt_manager.create_refresh_token(payload)
        
        # 使用 Refresh Token 换取新 Access Token（带滑动过期）
        result = jwt_manager.refresh_tokens(refresh_token)
        if result:
            new_access_token = result['access_token']
            new_refresh_token = result.get('refresh_token')  # 如果需要续期才有值
    """
    
    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 30,
        refresh_token_expire_days: int = 7,
        refresh_token_sliding_days: int = 2,
    ):
        if not JOSE_AVAILABLE:
            raise ImportError(
                "python-jose 未安装。请运行: pip install python-jose[cryptography]"
            )
        
        # 参数校验
        if access_token_expire_minutes <= 0:
            raise ValueError("access_token_expire_minutes 必须大于 0")
        
        if refresh_token_expire_days <= 0:
            raise ValueError("refresh_token_expire_days 必须大于 0")
        
        if refresh_token_sliding_days >= refresh_token_expire_days:
            raise ValueError(
                f"refresh_token_sliding_days ({refresh_token_sliding_days}) 必须小于 "
                f"refresh_token_expire_days ({refresh_token_expire_days})，"
                f"否则每次刷新都会返回新的 Refresh Token。"
            )
        
        if refresh_token_sliding_days < 0:
            raise ValueError("refresh_token_sliding_days 必须大于等于 0（0 表示禁用滑动过期）")
        
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_expire_minutes = access_token_expire_minutes
        self.refresh_token_expire_days = refresh_token_expire_days
        self.refresh_token_sliding_days = refresh_token_sliding_days
    
    def create_access_token(
        self,
        payload: Union[TokenPayload, Dict[str, Any]],
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """创建访问令牌
        
        Args:
            payload: Token 载荷，可以是 TokenPayload 或字典
            expires_delta: 自定义过期时间
            
        Returns:
            JWT Token 字符串
        """
        # 转换 payload 为字典
        if isinstance(payload, TokenPayload):
            data = {
                "sub": payload.sub,
                "user_id": payload.user_id,
                "username": payload.username,
                "email": payload.email,
                "roles": payload.roles,
                "token_type": "access",
                **payload.extra
            }
        else:
            data = payload.copy()
            data["token_type"] = "access"
        
        # 设置过期时间
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=self.access_token_expire_minutes)
        
        data["exp"] = expire
        data["iat"] = datetime.now(timezone.utc)
        
        return jwt.encode(data, self.secret_key, algorithm=self.algorithm)
    
    def create_refresh_token(
        self,
        payload: Union[TokenPayload, Dict[str, Any]],
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """创建刷新令牌
        
        Args:
            payload: Token 载荷
            expires_delta: 自定义过期时间
            
        Returns:
            JWT Token 字符串
        """
        # 转换 payload 为字典（刷新令牌只需要基本信息）
        if isinstance(payload, TokenPayload):
            data = {
                "sub": payload.sub,
                "user_id": payload.user_id,
                "token_type": "refresh",
            }
        else:
            data = {
                "sub": payload.get("sub"),
                "user_id": payload.get("user_id"),
                "token_type": "refresh",
            }
        
        # 设置过期时间
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(days=self.refresh_token_expire_days)
        
        data["exp"] = expire
        data["iat"] = datetime.now(timezone.utc)
        
        return jwt.encode(data, self.secret_key, algorithm=self.algorithm)
    
    def verify_token(
        self, token: str, raise_on_expired: bool = False
    ) -> Optional[TokenData]:
        """验证令牌
        
        Args:
            token: JWT Token 字符串
            raise_on_expired: 为 True 时，Token 过期抛出 AuthenticationException(TOKEN_EXPIRED)
                而非返回 None。用于认证依赖中区分「过期」和「无效」。
            
        Returns:
            TokenData 对象，验证失败返回 None
            
        Raises:
            AuthenticationException: 当 raise_on_expired=True 且 Token 已过期时
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )
            
            return TokenData(
                sub=payload.get("sub"),
                user_id=payload.get("user_id"),
                username=payload.get("username"),
                email=payload.get("email"),
                roles=payload.get("roles", []),
                token_type=payload.get("token_type", "access"),
                exp=payload.get("exp"),
                iat=payload.get("iat"),
            )
        except ExpiredSignatureError:
            if raise_on_expired:
                from yweb.exceptions import AuthenticationException, ErrorCode
                raise AuthenticationException(
                    "访问令牌已过期",
                    code=ErrorCode.TOKEN_EXPIRED,
                )
            return None
        except JWTError:
            return None
        except Exception:
            return None
    
    def decode_token(self, token: str) -> Optional[Dict[str, Any]]:
        """解码令牌（返回原始字典）
        
        Args:
            token: JWT Token 字符串
            
        Returns:
            解码后的字典，验证失败返回 None
        """
        try:
            return jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )
        except JWTError:
            return None
        except Exception:
            return None
    
    def is_token_expired(self, token: str) -> bool:
        """检查令牌是否过期
        
        Args:
            token: JWT Token 字符串
            
        Returns:
            是否过期
        """
        payload = self.decode_token(token)
        if not payload:
            return True
        
        exp = payload.get("exp")
        if not exp:
            return True
        
        return datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc)
    
    def get_token_type(self, token: str) -> Optional[str]:
        """获取令牌类型
        
        Args:
            token: JWT Token 字符串
            
        Returns:
            令牌类型（access/refresh），失败返回 None
        """
        payload = self.decode_token(token)
        if not payload:
            return None
        return payload.get("token_type")
    
    def get_remaining_seconds(self, token: str) -> Optional[int]:
        """获取 Token 剩余有效秒数
        
        Args:
            token: JWT Token 字符串
            
        Returns:
            剩余秒数，Token 无效或已过期返回 None
        """
        payload = self.decode_token(token)
        if not payload or "exp" not in payload:
            return None
        
        exp_time = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        remaining = (exp_time - datetime.now(timezone.utc)).total_seconds()
        
        if remaining <= 0:
            return None
        
        return int(remaining)
    
    def get_remaining_days(self, token: str) -> Optional[float]:
        """获取 Token 剩余有效天数
        
        Args:
            token: JWT Token 字符串
            
        Returns:
            剩余天数，Token 无效或已过期返回 None
        """
        remaining_seconds = self.get_remaining_seconds(token)
        if remaining_seconds is None:
            return None
        return remaining_seconds / 86400  # 86400 = 24 * 60 * 60
    
    def should_renew_refresh_token(self, refresh_token: str) -> bool:
        """判断 Refresh Token 是否需要续期
        
        当 Refresh Token 剩余时间少于 refresh_token_sliding_days 时返回 True。
        
        Args:
            refresh_token: Refresh Token 字符串
            
        Returns:
            是否需要续期
        """
        if self.refresh_token_sliding_days <= 0:
            return False  # 禁用滑动过期
        
        remaining_days = self.get_remaining_days(refresh_token)
        if remaining_days is None:
            return False
        
        return remaining_days < self.refresh_token_sliding_days
    
    def refresh_tokens(
        self,
        refresh_token: str,
        user_getter: Optional[callable] = None
    ) -> Optional[Dict[str, Any]]:
        """使用 Refresh Token 换取新的 Token
        
        这是刷新 Token 的主要方法。返回新的 Access Token，
        如果 Refresh Token 即将过期（剩余时间少于 sliding_days），也会返回新的 Refresh Token。
        
        Args:
            refresh_token: Refresh Token 字符串
            user_getter: 可选的用户获取函数，用于验证用户状态
                        接收 user_id，返回用户对象或 None
            
        Returns:
            字典格式:
            {
                "access_token": "new_access_token",
                "refresh_token": "new_refresh_token" | None,  # 仅当需要续期时返回
                "token_type": "bearer",
                "refresh_token_renewed": True | False  # 标识 Refresh Token 是否已续期
            }
            失败返回 None
        """
        token_data = self.verify_token(refresh_token)
        if not token_data:
            return None
        
        # 验证是 refresh 类型
        if token_data.token_type != "refresh":
            return None
        
        if not token_data.user_id:
            return None
        
        # 构建 payload
        if user_getter:
            user = user_getter(token_data.user_id)
            if not user:
                return None
            # 检查用户是否激活
            if hasattr(user, "is_active") and not user.is_active:
                return None
            
            # 从用户对象获取最新信息
            username = getattr(user, "username", token_data.sub)
            email = getattr(user, "email", None)
            roles = []
            if hasattr(user, "roles"):
                roles = [r.code if hasattr(r, "code") else str(r) for r in user.roles]
            
            payload = TokenPayload(
                sub=username,
                user_id=token_data.user_id,
                username=username,
                email=email,
                roles=roles,
            )
        else:
            payload = TokenPayload(
                sub=token_data.sub,
                user_id=token_data.user_id,
                username=token_data.sub,
                email=None,
                roles=[],
            )
        
        # 创建新的 Access Token
        new_access_token = self.create_access_token(payload)
        
        # 检查是否需要续期 Refresh Token
        should_renew = self.should_renew_refresh_token(refresh_token)
        new_refresh_token = None
        
        if should_renew:
            new_refresh_token = self.create_refresh_token(payload)
        
        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
            "refresh_token_renewed": should_renew,
        }
    
    # ==================== 兼容旧 API ====================
    
    def refresh_from_refresh_token(
        self,
        refresh_token: str,
        user_getter: Optional[callable] = None
    ) -> Optional[str]:
        """从 Refresh Token 获取新的 Access Token（兼容旧 API）
        
        注意：此方法仅返回 Access Token，不支持 Refresh Token 滑动过期。
        推荐使用 refresh_tokens() 方法获取完整的刷新结果。
        
        Args:
            refresh_token: Refresh Token 字符串
            user_getter: 可选的用户获取函数
            
        Returns:
            新的 Access Token，失败返回 None
        """
        result = self.refresh_tokens(refresh_token, user_getter)
        if not result:
            return None
        return result["access_token"]


# 便捷函数
def create_jwt_token(
    data: Dict[str, Any],
    secret_key: str,
    algorithm: str = "HS256",
    expires_delta: Optional[timedelta] = None,
    expires_minutes: int = 30
) -> str:
    """创建 JWT Token（便捷函数）
    
    Args:
        data: Token 数据
        secret_key: 密钥
        algorithm: 算法
        expires_delta: 过期时间增量
        expires_minutes: 过期分钟数（当 expires_delta 为 None 时使用）
        
    Returns:
        JWT Token 字符串
    """
    if not JOSE_AVAILABLE:
        raise ImportError("python-jose 未安装。请运行: pip install python-jose[cryptography]")
    
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    
    to_encode["exp"] = expire
    to_encode["iat"] = datetime.now(timezone.utc)
    
    return jwt.encode(to_encode, secret_key, algorithm=algorithm)


def verify_jwt_token(
    token: str,
    secret_key: str,
    algorithm: str = "HS256"
) -> Optional[Dict[str, Any]]:
    """验证 JWT Token（便捷函数）
    
    Args:
        token: JWT Token 字符串
        secret_key: 密钥
        algorithm: 算法
        
    Returns:
        解码后的数据字典，失败返回 None
    """
    if not JOSE_AVAILABLE:
        raise ImportError("python-jose 未安装。请运行: pip install python-jose[cryptography]")
    
    try:
        return jwt.decode(token, secret_key, algorithms=[algorithm])
    except JWTError:
        return None
    except Exception:
        return None

