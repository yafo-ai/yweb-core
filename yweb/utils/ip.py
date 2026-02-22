"""IP 地址工具模块

提供统一的客户端 IP 提取和 IP/CIDR 匹配功能。

使用示例:
    from yweb.utils.ip import get_client_ip, ip_in_list

    # 从请求中提取客户端真实 IP
    client_ip = get_client_ip(request, trusted_proxies=["127.0.0.1", "10.0.0.0/8"])

    # 检查 IP 是否在列表中（支持单 IP 和 CIDR 网段）
    if ip_in_list("192.168.1.100", ["192.168.0.0/16", "10.0.0.1"]):
        ...
"""

from ipaddress import ip_address, ip_network, IPv4Address, IPv6Address
from typing import List, Optional, Union

from starlette.requests import Request


def get_client_ip(
    request: Request,
    trusted_proxies: Optional[List[str]] = None,
) -> str:
    """从请求中提取客户端真实 IP

    提取优先级：
    1. 如果直连 IP 是受信任代理 → 从 X-Forwarded-For 第一个 IP 获取
    2. 如果直连 IP 是受信任代理 → 从 X-Real-IP 获取
    3. 直接使用连接 IP（request.client.host）

    Args:
        request: Starlette/FastAPI Request 对象
        trusted_proxies: 受信任的代理 IP 列表（支持 CIDR，如 ["127.0.0.1", "10.0.0.0/8"]）

    Returns:
        客户端 IP 地址字符串
    """
    # 获取直连 IP
    direct_ip = request.client.host if request.client else "unknown"

    if not trusted_proxies or direct_ip == "unknown":
        return direct_ip

    # 检查直连 IP 是否是受信任代理
    if not ip_in_list(direct_ip, trusted_proxies):
        return direct_ip

    # 从 X-Forwarded-For 获取（取第一个，即最原始的客户端 IP）
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
        if client_ip:
            return client_ip

    # 从 X-Real-IP 获取
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    return direct_ip


def get_client_ip_from_scope(
    scope: dict,
    trusted_proxies: Optional[List[str]] = None,
) -> str:
    """从 ASGI scope 中提取客户端真实 IP（供中间件使用）

    逻辑与 get_client_ip 一致，但直接操作 ASGI scope，
    避免中间件中构造 Request 对象的开销。

    Args:
        scope: ASGI scope 字典
        trusted_proxies: 受信任的代理 IP 列表

    Returns:
        客户端 IP 地址字符串
    """
    # 获取直连 IP
    client = scope.get("client")
    direct_ip = client[0] if client else "unknown"

    if not trusted_proxies or direct_ip == "unknown":
        return direct_ip

    # 检查直连 IP 是否是受信任代理
    if not ip_in_list(direct_ip, trusted_proxies):
        return direct_ip

    # 从 headers 中提取（ASGI headers 是 [(name_bytes, value_bytes), ...] 格式）
    headers = dict(scope.get("headers", []))

    # X-Forwarded-For
    xff = headers.get(b"x-forwarded-for")
    if xff:
        client_ip = xff.decode("utf-8", errors="replace").split(",")[0].strip()
        if client_ip:
            return client_ip

    # X-Real-IP
    xri = headers.get(b"x-real-ip")
    if xri:
        return xri.decode("utf-8", errors="replace").strip()

    return direct_ip


def ip_in_list(ip: str, ip_list: List[str]) -> bool:
    """检查 IP 是否匹配列表中的任意一项

    列表项支持：
    - 单 IP: "192.168.1.100"
    - CIDR 网段: "192.168.0.0/16"
    - 通配符: "*"（匹配所有）

    Args:
        ip: 要检查的 IP 地址
        ip_list: IP/CIDR 列表

    Returns:
        是否匹配
    """
    if not ip_list:
        return False

    # 先尝试解析 IP；无效 IP 只能被通配符 * 匹配
    try:
        addr = ip_address(ip)
    except ValueError:
        return any(item.strip() == "*" for item in ip_list)

    for item in ip_list:
        item = item.strip()
        if item == "*":
            return True
        try:
            if "/" in item:
                # CIDR 网段匹配
                if addr in ip_network(item, strict=False):
                    return True
            else:
                # 单 IP 精确匹配
                if addr == ip_address(item):
                    return True
        except ValueError:
            # 无效的 IP/CIDR 格式，跳过
            continue

    return False
