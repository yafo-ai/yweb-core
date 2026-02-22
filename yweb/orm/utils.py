"""ORM 工具函数

提供通用的字符串处理和命名转换工具。
"""
import re


def to_snake_case(name: str, remove_model_suffix: bool = False) -> str:
    """驼峰命名转下划线命名（支持连续大写缩写如 E2E、API、URL）
    
    Args:
        name: 类名或字符串
        remove_model_suffix: 是否移除 Model 后缀（用于生成 backref 名称）
        
    Returns:
        下划线格式的字符串
        
    Examples:
        >>> to_snake_case("OrderItem")
        'order_item'
        >>> to_snake_case("E2EOrder")
        'e2e_order'
        >>> to_snake_case("APIClient")
        'api_client'
        >>> to_snake_case("UserID")
        'user_id'
        >>> to_snake_case("OrderModel", remove_model_suffix=True)
        'order'
        >>> to_snake_case("E2EOrderItemModel", remove_model_suffix=True)
        'e2e_order_item'
    """
    if remove_model_suffix and name.endswith('Model'):
        name = name[:-5]
    # 处理连续大写+数字后跟大写+小写：E2EOrder → E2E_Order, APIClient → API_Client
    result = re.sub(r'([A-Z\d]+)([A-Z][a-z])', r'\1_\2', name)
    # 处理小写字母后跟大写：orderItem → order_Item
    result = re.sub(r'([a-z])([A-Z])', r'\1_\2', result)
    return result.lower()


def pluralize(name: str) -> str:
    """简单的英文复数形式
    
    Args:
        name: 单数形式的名称
        
    Returns:
        复数形式的名称
        
    Examples:
        >>> pluralize("order")
        'orders'
        >>> pluralize("items")
        'items'
    
    Note:
        这是一个简化实现，仅处理基本情况。
        对于复杂的英文复数规则（如 category→categories）不做特殊处理。
    """
    if not name.endswith('s'):
        return name + 's'
    return name


def singularize(name: str) -> str:
    """简单的英文单数形式（去复数化）
    
    Args:
        name: 复数形式的名称（通常是表名）
        
    Returns:
        单数形式的名称
        
    Examples:
        >>> singularize("orders")
        'order'
        >>> singularize("categories")
        'category'
        >>> singularize("users")
        'user'
        >>> singularize("address")
        'address'
        >>> singularize("fk_test_orders")
        'fk_test_order'
    
    Note:
        这是一个简化实现，处理常见的复数后缀：
        - ies → y (categories → category)
        - s → 去掉 (orders → order)
        - ss 结尾不处理 (address → address)
    """
    if name.endswith('ies'):
        return name[:-3] + 'y'
    elif name.endswith('s') and not name.endswith('ss'):
        return name[:-1]
    return name


__all__ = [
    "to_snake_case",
    "pluralize",
    "singularize",
]
