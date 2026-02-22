"""工具模块

提供通用工具函数：
- 密码加密与验证
- 文件大小解析
- ID 生成
- IP 地址处理
- 轻量级测试收集器

日志相关功能已移动到 yweb.log 模块。

使用示例:
    from yweb.utils import (
        hash_password, verify_password,
        parse_file_size, format_file_size,
        generate_id,
        get_client_ip, ip_in_list,
        TestCollector, create_test_collector,
    )
"""

from .encryption import EncryptionUtil, hash_password, verify_password
from .file_size import (
    parse_file_size,
    format_file_size,
    human_readable_size,
    validate_file_size,
    SIZE_UNITS,
)
from .generate_id import generate_id
from .ip import get_client_ip, get_client_ip_from_scope, ip_in_list
from .test_collector import (
    TestStatus,
    TestResult,
    TestCollector,
    create_test_collector,
)

__all__ = [
    # 加密工具
    "EncryptionUtil",
    "hash_password",
    "verify_password",
    
    # 文件大小工具
    "parse_file_size",
    "format_file_size",
    "human_readable_size",
    "validate_file_size",
    "SIZE_UNITS",
    
    # ID 生成
    "generate_id",
    
    # IP 地址工具
    "get_client_ip",
    "get_client_ip_from_scope",
    "ip_in_list",
    
    # 测试收集器
    "TestStatus",
    "TestResult",
    "TestCollector",
    "create_test_collector",
]
