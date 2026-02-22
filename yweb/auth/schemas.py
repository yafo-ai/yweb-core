"""认证相关 Schema

定义 Token 载荷和认证相关的数据结构。
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from pydantic import BaseModel


@dataclass
class TokenPayload:
    """Token 载荷数据类
    
    用于存储 JWT Token 中的用户信息。
    
    Attributes:
        sub: 主题（通常是用户名或用户ID）
        user_id: 用户ID
        username: 用户名
        email: 用户邮箱
        roles: 用户角色列表
        token_type: Token类型（access/refresh）
        extra: 额外数据
    
    使用示例:
        payload = TokenPayload(
            sub="john",
            user_id=1,
            username="john",
            email="john@example.com",
            roles=["admin", "user"]
        )
    """
    sub: str  # JWT标准字段：subject
    user_id: int
    username: str
    email: Optional[str] = None
    roles: List[str] = field(default_factory=list)
    token_type: str = "access"
    extra: Dict[str, Any] = field(default_factory=dict)


class TokenResponse(BaseModel):
    """Token 响应模型
    
    用于 API 返回 Token 信息。
    """
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # 过期时间（秒）
    refresh_token: Optional[str] = None


class TokenData(BaseModel):
    """Token 数据模型
    
    用于从 Token 中解析的数据。
    """
    sub: Optional[str] = None
    user_id: Optional[int] = None
    username: Optional[str] = None
    email: Optional[str] = None
    roles: List[str] = []
    token_type: str = "access"
    exp: Optional[int] = None
    iat: Optional[int] = None

