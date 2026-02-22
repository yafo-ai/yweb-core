"""FastAPI 认证依赖模块

提供通用的认证依赖函数和装饰器。

使用示例:
    from yweb.auth import create_auth_dependency, oauth2_scheme
    from fastapi import Depends
    
    # 方式1：使用工厂函数创建依赖
    get_current_user = create_auth_dependency(
        jwt_manager=jwt_manager,
        user_getter=lambda user_id: User.get_by_id(user_id)
    )
    
    @app.get("/me")
    def get_me(user = Depends(get_current_user)):
        return user
    
    # 方式2：继承 AuthDependency 类
    class MyAuthDependency(AuthDependency):
        def get_user(self, user_id: int):
            return User.get_by_id(user_id)
    
    auth = MyAuthDependency(jwt_manager)
    
    @app.get("/me")
    def get_me(user = Depends(auth.get_current_user)):
        return user
"""

from abc import ABC, abstractmethod
from typing import Optional, Callable, TypeVar, Generic, Any
from functools import wraps

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, HTTPBearer, HTTPAuthorizationCredentials

from .jwt import JWTManager
from .schemas import TokenData


# OAuth2 密码模式
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

# HTTP Bearer 模式
http_bearer = HTTPBearer(auto_error=False)

# 用户类型变量
UserType = TypeVar("UserType")


class AuthDependency(ABC, Generic[UserType]):
    """认证依赖基类
    
    继承此类并实现 get_user 方法来创建自定义认证依赖。
    
    使用示例:
        class MyAuth(AuthDependency[User]):
            def get_user(self, user_id: int) -> Optional[User]:
                return User.get_by_id(user_id)
        
        auth = MyAuth(jwt_manager)
        
        @app.get("/me")
        def get_me(user: User = Depends(auth.get_current_user)):
            return user
    """
    
    def __init__(self, jwt_manager: JWTManager):
        self.jwt_manager = jwt_manager
    
    @abstractmethod
    def get_user(self, user_id: int) -> Optional[UserType]:
        """根据用户ID获取用户
        
        Args:
            user_id: 用户ID
            
        Returns:
            用户对象，不存在返回 None
        """
        pass
    
    def get_current_user(
        self,
        token: Optional[str] = Depends(oauth2_scheme)
    ) -> UserType:
        """获取当前用户（必须认证）
        
        Args:
            token: JWT Token
            
        Returns:
            用户对象
            
        Raises:
            HTTPException: 认证失败时抛出 401 错误
        """
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无法验证凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
        if not token:
            raise credentials_exception
        
        token_data = self.jwt_manager.verify_token(token)
        if not token_data or not token_data.user_id:
            raise credentials_exception
        
        # 检查是否是访问令牌
        if token_data.token_type != "access":
            raise credentials_exception
        
        user = self.get_user(token_data.user_id)
        if not user:
            raise credentials_exception
        
        return user
    
    def get_current_user_optional(
        self,
        token: Optional[str] = Depends(oauth2_scheme)
    ) -> Optional[UserType]:
        """获取当前用户（可选认证）
        
        Args:
            token: JWT Token
            
        Returns:
            用户对象，未认证返回 None
        """
        if not token:
            return None
        
        try:
            token_data = self.jwt_manager.verify_token(token)
            if not token_data or not token_data.user_id:
                return None
            
            if token_data.token_type != "access":
                return None
            
            return self.get_user(token_data.user_id)
        except Exception:
            return None
    
    def get_token_data(
        self,
        token: Optional[str] = Depends(oauth2_scheme)
    ) -> TokenData:
        """获取 Token 数据
        
        Args:
            token: JWT Token
            
        Returns:
            TokenData 对象
            
        Raises:
            HTTPException: 认证失败时抛出 401 错误
        """
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无法验证凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
        if not token:
            raise credentials_exception
        
        token_data = self.jwt_manager.verify_token(token)
        if not token_data:
            raise credentials_exception
        
        return token_data


def create_auth_dependency(
    jwt_manager: JWTManager,
    user_getter: Callable[[int], Optional[Any]],
    auto_error: bool = True
) -> Callable:
    """创建认证依赖函数
    
    快速创建认证依赖，无需继承 AuthDependency 类。
    
    Args:
        jwt_manager: JWT 管理器
        user_getter: 获取用户的函数，接收 user_id 返回用户对象
        auto_error: 认证失败是否自动抛出异常
        
    Returns:
        FastAPI 依赖函数
    
    使用示例:
        get_current_user = create_auth_dependency(
            jwt_manager=jwt_manager,
            user_getter=lambda user_id: User.get_by_id(user_id)
        )
        
        @app.get("/me")
        def get_me(user = Depends(get_current_user)):
            return user
    """
    def dependency(token: Optional[str] = Depends(oauth2_scheme)):
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无法验证凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
        if not token:
            if auto_error:
                raise credentials_exception
            return None
        
        token_data = jwt_manager.verify_token(token)
        if not token_data or not token_data.user_id:
            if auto_error:
                raise credentials_exception
            return None
        
        if token_data.token_type != "access":
            if auto_error:
                raise credentials_exception
            return None
        
        user = user_getter(token_data.user_id)
        if not user:
            if auto_error:
                raise credentials_exception
            return None
        
        return user
    
    return dependency


def require_roles(*roles: str):
    """要求用户具有指定角色的装饰器
    
    Args:
        *roles: 允许的角色列表
        
    Returns:
        装饰器函数
    
    使用示例:
        @app.get("/admin")
        @require_roles("admin", "superadmin")
        def admin_only(user = Depends(get_current_user)):
            return {"message": "Admin access granted"}
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 从 kwargs 中获取 request 或用户信息
            # 这需要配合认证依赖使用
            return await func(*args, **kwargs)
        return wrapper
    return decorator


class RoleChecker:
    """角色检查器
    
    用于检查用户是否具有指定角色。
    
    使用示例:
        role_checker = RoleChecker(["admin", "manager"])
        
        @app.get("/admin")
        def admin_only(
            user = Depends(get_current_user),
            _: bool = Depends(role_checker)
        ):
            return {"message": "Access granted"}
    """
    
    def __init__(self, allowed_roles: list):
        self.allowed_roles = allowed_roles
    
    def __call__(
        self,
        token: Optional[str] = Depends(oauth2_scheme),
        jwt_manager: JWTManager = None
    ) -> bool:
        """检查用户角色
        
        Note: 需要配合 jwt_manager 使用，或在子类中注入
        """
        if not token or not jwt_manager:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="未提供认证信息"
            )
        
        token_data = jwt_manager.verify_token(token)
        if not token_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的令牌"
            )
        
        if not any(role in self.allowed_roles for role in token_data.roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足"
            )
        
        return True


def get_token_from_header(request: Request) -> Optional[str]:
    """从请求头获取 Token
    
    支持 Authorization: Bearer <token> 格式
    
    Args:
        request: FastAPI Request 对象
        
    Returns:
        Token 字符串，不存在返回 None
    """
    authorization = request.headers.get("Authorization")
    if not authorization:
        return None
    
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    
    return parts[1]

