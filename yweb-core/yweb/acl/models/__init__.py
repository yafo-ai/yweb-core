"""
ACL 模块 - 抽象模型

提供 ACL 规则和资源树的抽象基类，应用层通过 setup_acl() 工厂动态生成具体模型。
"""

from .acl_rule import AbstractAclRule
from .acl_resource import AbstractAclResource

__all__ = [
    "AbstractAclRule",
    "AbstractAclResource",
]
