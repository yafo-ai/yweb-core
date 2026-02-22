"""文件大小解析工具

提供文件大小字符串的解析功能，支持 B, KB, MB, GB, TB 等单位。

使用示例:
    from yweb.utils import parse_file_size, format_file_size
    
    # 解析文件大小字符串
    size = parse_file_size("10MB")  # 返回 10485760
    size = parse_file_size("512KB")  # 返回 524288
    size = parse_file_size("1.5GB")  # 返回 1610612736
    
    # 格式化字节数为可读字符串
    text = format_file_size(10485760)  # 返回 "10.00 MB"
"""

from typing import Union


# 单位转换表（按长度降序排列）
SIZE_UNITS = [
    ('TB', 1024 ** 4),
    ('GB', 1024 ** 3),
    ('MB', 1024 ** 2),
    ('KB', 1024),
    ('B', 1),
]

# 单位别名
SIZE_UNIT_ALIASES = {
    'T': 'TB',
    'G': 'GB',
    'M': 'MB',
    'K': 'KB',
    'BYTES': 'B',
    'BYTE': 'B',
}


def parse_file_size(size_str: Union[str, int, float]) -> int:
    """解析文件大小字符串
    
    支持的单位：B, KB, MB, GB, TB（不区分大小写）
    
    Args:
        size_str: 文件大小字符串，如 "10MB", "512KB", "1.5GB"
                  也可以直接传入数字（字节数）
        
    Returns:
        int: 文件大小的字节数
        
    Raises:
        ValueError: 当格式无效时抛出异常
    
    使用示例:
        >>> parse_file_size("10MB")
        10485760
        >>> parse_file_size("512KB")
        524288
        >>> parse_file_size("1.5GB")
        1610612736
        >>> parse_file_size(1024)
        1024
    """
    # 如果是数字，直接返回
    if isinstance(size_str, (int, float)):
        return int(size_str)
    
    size_str = str(size_str).strip().upper()
    
    if not size_str:
        raise ValueError("文件大小字符串不能为空")
    
    # 处理单位别名
    for alias, unit in SIZE_UNIT_ALIASES.items():
        if size_str.endswith(alias) and not size_str.endswith(unit):
            size_str = size_str[:-len(alias)] + unit
            break
    
    # 查找单位
    for unit, multiplier in SIZE_UNITS:
        if size_str.endswith(unit):
            number_str = size_str[:-len(unit)].strip()
            if not number_str:
                raise ValueError(f"无法解析文件大小: {size_str}")
            try:
                number = float(number_str)
                return int(number * multiplier)
            except ValueError:
                raise ValueError(f"无法解析文件大小: {size_str}")
    
    # 如果没有找到单位，尝试解析为纯数字（字节）
    try:
        return int(float(size_str))
    except ValueError:
        raise ValueError(f"无法解析文件大小: {size_str}")


def format_file_size(
    size_bytes: Union[int, float],
    precision: int = 2,
    binary: bool = True
) -> str:
    """格式化字节数为可读字符串
    
    Args:
        size_bytes: 字节数
        precision: 小数位数
        binary: 是否使用二进制单位（1024），否则使用十进制（1000）
        
    Returns:
        格式化后的字符串，如 "10.00 MB"
    
    使用示例:
        >>> format_file_size(10485760)
        '10.00 MB'
        >>> format_file_size(1536)
        '1.50 KB'
        >>> format_file_size(1073741824)
        '1.00 GB'
    """
    if size_bytes < 0:
        return f"-{format_file_size(-size_bytes, precision, binary)}"
    
    base = 1024 if binary else 1000
    
    units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB']
    
    for unit in units:
        if abs(size_bytes) < base:
            return f"{size_bytes:.{precision}f} {unit}"
        size_bytes /= base
    
    return f"{size_bytes:.{precision}f} EB"


def human_readable_size(size_bytes: Union[int, float]) -> str:
    """返回人类可读的文件大小（简化版）
    
    Args:
        size_bytes: 字节数
        
    Returns:
        格式化后的字符串
    
    使用示例:
        >>> human_readable_size(1024)
        '1 KB'
        >>> human_readable_size(1048576)
        '1 MB'
    """
    for unit, threshold in SIZE_UNITS:
        if abs(size_bytes) >= threshold:
            value = size_bytes / threshold
            if value == int(value):
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
    return f"{size_bytes} B"


def validate_file_size(
    size_str: str,
    min_size: Union[str, int] = None,
    max_size: Union[str, int] = None
) -> bool:
    """验证文件大小是否在范围内
    
    Args:
        size_str: 要验证的文件大小字符串
        min_size: 最小大小（可选）
        max_size: 最大大小（可选）
        
    Returns:
        是否在有效范围内
    
    使用示例:
        >>> validate_file_size("5MB", min_size="1MB", max_size="10MB")
        True
        >>> validate_file_size("15MB", max_size="10MB")
        False
    """
    try:
        size = parse_file_size(size_str)
        
        if min_size is not None:
            min_bytes = parse_file_size(min_size)
            if size < min_bytes:
                return False
        
        if max_size is not None:
            max_bytes = parse_file_size(max_size)
            if size > max_bytes:
                return False
        
        return True
    except ValueError:
        return False

