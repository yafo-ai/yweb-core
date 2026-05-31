"""
ACL 模块 - 类型定义

定义 IdentityProvider 协议和 IdentitySet 类型别名。
框架只定义协议，不提供实现——应用层根据自己的用户/组织模型实现。
"""

from typing import Any, Protocol, runtime_checkable

IdentitySet = set[str]


@runtime_checkable
class IdentityProvider(Protocol):
    """身份展开协议

    应用层实现此接口，将用户对象转换为身份标签集合。

    身份标签格式示例::

        {"user:123", "dept:456", "role:admin", "everyone"}

    使用示例::

        class MyIdentityProvider:
            def get_identities(self, user) -> set[str]:
                return {"everyone", f"user:{user.id}"}
    """

    def get_identities(self, user: Any) -> IdentitySet: ...


__all__ = ["IdentitySet", "IdentityProvider"]
