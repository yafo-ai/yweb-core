"""限流 Key 提取函数

提供从请求中提取限流标识的函数，用于 slowapi 的 key_func 参数。

内置策略:
    - get_user_or_ip: 优先从 JWT 提取 user_id，fallback 到客户端 IP（默认）
    - get_remote_address: 纯 IP 限流（re-export slowapi 内置函数）
"""

from typing import Optional

from starlette.requests import Request

from yweb.log import get_logger

logger = get_logger("yweb.ratelimit")


def _get_client_ip(request: Request) -> str:
    """从请求中提取客户端 IP

    优先读取反向代理头 X-Forwarded-For / X-Real-IP，
    fallback 到 request.client.host。
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    if request.client:
        return request.client.host

    return "unknown"


def _try_extract_user_id(request: Request) -> Optional[str]:
    """尝试从 JWT Bearer Token 中提取用户标识

    不做完整认证校验，仅尽力解码 token 以获取 sub / user_id。
    解码失败时静默返回 None，不抛异常。
    """
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return None

    token = auth_header[7:].strip()
    if not token:
        return None

    try:
        from jose import jwt as jose_jwt

        payload = jose_jwt.decode(
            token, "", options={"verify_signature": False, "verify_exp": False}
        )
        user_id = payload.get("sub") or payload.get("user_id")
        return f"user:{user_id}" if user_id else None
    except Exception:
        return None


def get_user_or_ip(request: Request) -> str:
    """优先按用户身份限流，匿名时按 IP 限流

    策略:
        1. 尝试从 Authorization Bearer Token 解析 JWT，提取 sub/user_id
        2. 解析失败（无 token / 格式错误 / 匿名） → fallback 到客户端 IP

    不做认证校验，不抛异常——仅用于限流分桶。
    """
    user_id = _try_extract_user_id(request)
    if user_id:
        return user_id
    return f"ip:{_get_client_ip(request)}"


def get_remote_address(request: Request) -> str:
    """纯 IP 限流（与 slowapi.util.get_remote_address 行为一致，增加代理头支持）"""
    return _get_client_ip(request)


__all__ = [
    "get_user_or_ip",
    "get_remote_address",
]
