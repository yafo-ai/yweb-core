"""树形结构工具函数

提供树形数据处理的通用工具函数。

使用示例:
    from yweb.orm.tree import build_tree_list, flatten_tree
    
    # 将扁平列表构建为嵌套树
    flat_list = [
        {"id": 1, "parent_id": None, "name": "根节点"},
        {"id": 2, "parent_id": 1, "name": "子节点1"},
        {"id": 3, "parent_id": 1, "name": "子节点2"},
    ]
    tree = build_tree_list(flat_list)
    
    # 将嵌套树展平为列表
    flat = flatten_tree(tree)
"""

from typing import List, Dict, Any, Optional, Union, Callable


def build_tree_list(
    nodes: List[Dict[str, Any]],
    id_field: str = "id",
    parent_field: str = "parent_id",
    children_field: str = "children",
    root_parent_value: Any = None,
    sort_key: Optional[Callable[[Dict], Any]] = None,
) -> List[Dict[str, Any]]:
    """将扁平列表构建为嵌套树结构
    
    Args:
        nodes: 扁平的节点列表，每个节点是一个字典
        id_field: ID 字段名
        parent_field: 父节点 ID 字段名
        children_field: 子节点列表字段名（输出中使用）
        root_parent_value: 根节点的父节点值（通常是 None）
        sort_key: 排序函数，用于对同级节点排序
        
    Returns:
        嵌套的树形结构列表
        
    使用示例:
        flat_list = [
            {"id": 1, "parent_id": None, "name": "A"},
            {"id": 2, "parent_id": 1, "name": "A-1"},
            {"id": 3, "parent_id": 1, "name": "A-2"},
            {"id": 4, "parent_id": 2, "name": "A-1-1"},
        ]
        
        tree = build_tree_list(flat_list)
        # 结果:
        # [
        #     {
        #         "id": 1, "parent_id": None, "name": "A",
        #         "children": [
        #             {"id": 2, "parent_id": 1, "name": "A-1", "children": [
        #                 {"id": 4, "parent_id": 2, "name": "A-1-1", "children": []}
        #             ]},
        #             {"id": 3, "parent_id": 1, "name": "A-2", "children": []},
        #         ]
        #     }
        # ]
    """
    if not nodes:
        return []
    
    # 创建 ID 到节点的映射
    node_map: Dict[Any, Dict[str, Any]] = {}
    for node in nodes:
        # 复制节点，避免修改原始数据
        node_copy = dict(node)
        node_copy[children_field] = []
        node_map[node_copy[id_field]] = node_copy
    
    # 构建树
    roots: List[Dict[str, Any]] = []
    
    for node in node_map.values():
        parent_id = node.get(parent_field)
        
        if parent_id == root_parent_value or parent_id is None:
            # 根节点
            roots.append(node)
        elif parent_id in node_map:
            # 添加到父节点的 children
            node_map[parent_id][children_field].append(node)
    
    # 递归排序
    if sort_key:
        _sort_tree_recursive(roots, children_field, sort_key)
    
    return roots


def _sort_tree_recursive(
    nodes: List[Dict[str, Any]],
    children_field: str,
    sort_key: Callable[[Dict], Any],
):
    """递归排序树节点"""
    nodes.sort(key=sort_key)
    for node in nodes:
        children = node.get(children_field, [])
        if children:
            _sort_tree_recursive(children, children_field, sort_key)


def flatten_tree(
    tree: List[Dict[str, Any]],
    children_field: str = "children",
    include_children_field: bool = False,
    level_field: Optional[str] = None,
    _current_level: int = 1,
) -> List[Dict[str, Any]]:
    """将嵌套树结构展平为列表
    
    Args:
        tree: 嵌套的树形结构列表
        children_field: 子节点列表字段名
        include_children_field: 是否在结果中保留 children 字段
        level_field: 如果指定，将添加层级信息到该字段
        _current_level: 内部使用，当前层级
        
    Returns:
        扁平的节点列表
        
    使用示例:
        tree = [
            {"id": 1, "name": "A", "children": [
                {"id": 2, "name": "A-1", "children": []},
            ]},
        ]
        
        flat = flatten_tree(tree)
        # 结果: [{"id": 1, "name": "A"}, {"id": 2, "name": "A-1"}]
        
        flat_with_level = flatten_tree(tree, level_field="level")
        # 结果: [{"id": 1, "name": "A", "level": 1}, {"id": 2, "name": "A-1", "level": 2}]
    """
    result: List[Dict[str, Any]] = []
    
    for node in tree:
        # 复制节点
        node_copy = dict(node)
        
        # 处理 children 字段
        children = node_copy.pop(children_field, [])
        if include_children_field:
            node_copy[children_field] = children
        
        # 添加层级信息
        if level_field:
            node_copy[level_field] = _current_level
        
        result.append(node_copy)
        
        # 递归处理子节点
        if children:
            result.extend(flatten_tree(
                children,
                children_field=children_field,
                include_children_field=include_children_field,
                level_field=level_field,
                _current_level=_current_level + 1,
            ))
    
    return result


def find_node_in_tree(
    tree: List[Dict[str, Any]],
    target_id: Any,
    id_field: str = "id",
    children_field: str = "children",
) -> Optional[Dict[str, Any]]:
    """在树中查找指定 ID 的节点
    
    Args:
        tree: 嵌套的树形结构列表
        target_id: 目标节点 ID
        id_field: ID 字段名
        children_field: 子节点列表字段名
        
    Returns:
        找到的节点，未找到返回 None
    """
    for node in tree:
        if node.get(id_field) == target_id:
            return node
        
        children = node.get(children_field, [])
        if children:
            found = find_node_in_tree(children, target_id, id_field, children_field)
            if found:
                return found
    
    return None


def get_node_path(
    tree: List[Dict[str, Any]],
    target_id: Any,
    id_field: str = "id",
    children_field: str = "children",
) -> List[Dict[str, Any]]:
    """获取从根到目标节点的路径
    
    Args:
        tree: 嵌套的树形结构列表
        target_id: 目标节点 ID
        id_field: ID 字段名
        children_field: 子节点列表字段名
        
    Returns:
        从根到目标节点的路径列表，未找到返回空列表
    """
    for node in tree:
        if node.get(id_field) == target_id:
            return [node]
        
        children = node.get(children_field, [])
        if children:
            path = get_node_path(children, target_id, id_field, children_field)
            if path:
                return [node] + path
    
    return []


def validate_no_circular_reference(
    node_id: Any,
    new_parent_id: Any,
    get_ancestors_func: Callable[[Any], List[Any]],
) -> bool:
    """验证移动不会造成循环引用
    
    Args:
        node_id: 要移动的节点 ID
        new_parent_id: 新父节点 ID
        get_ancestors_func: 获取祖先节点 ID 列表的函数
        
    Returns:
        True 表示没有循环引用，可以移动
        
    使用示例:
        def get_ancestors(node_id):
            node = Node.get(node_id)
            return [a.id for a in node.get_ancestors()]
        
        if validate_no_circular_reference(1, 5, get_ancestors):
            # 可以移动
            pass
    """
    if new_parent_id is None:
        return True
    
    if node_id == new_parent_id:
        return False
    
    # 获取新父节点的所有祖先
    new_parent_ancestors = get_ancestors_func(new_parent_id)
    
    # 如果要移动的节点在新父节点的祖先中，会造成循环
    return node_id not in new_parent_ancestors


def calculate_tree_depth(
    tree: List[Dict[str, Any]],
    children_field: str = "children",
    _current_depth: int = 1,
) -> int:
    """计算树的最大深度
    
    Args:
        tree: 嵌套的树形结构列表
        children_field: 子节点列表字段名
        _current_depth: 内部使用，当前深度
        
    Returns:
        树的最大深度
    """
    if not tree:
        return _current_depth - 1
    
    max_depth = _current_depth
    
    for node in tree:
        children = node.get(children_field, [])
        if children:
            child_depth = calculate_tree_depth(
                children,
                children_field=children_field,
                _current_depth=_current_depth + 1,
            )
            max_depth = max(max_depth, child_depth)
    
    return max_depth


def filter_tree(
    tree: List[Dict[str, Any]],
    predicate: Callable[[Dict[str, Any]], bool],
    children_field: str = "children",
    keep_ancestors: bool = True,
) -> List[Dict[str, Any]]:
    """过滤树中的节点
    
    Args:
        tree: 嵌套的树形结构列表
        predicate: 过滤条件函数，返回 True 表示保留
        children_field: 子节点列表字段名
        keep_ancestors: 是否保留匹配节点的祖先（即使祖先不匹配）
        
    Returns:
        过滤后的树
        
    使用示例:
        # 只保留 is_active=True 的节点
        filtered = filter_tree(tree, lambda n: n.get("is_active", False))
    """
    result: List[Dict[str, Any]] = []
    
    for node in tree:
        node_copy = dict(node)
        children = node_copy.pop(children_field, [])
        
        # 递归过滤子节点
        filtered_children = filter_tree(
            children,
            predicate,
            children_field=children_field,
            keep_ancestors=keep_ancestors,
        ) if children else []
        
        node_copy[children_field] = filtered_children
        
        # 判断是否保留当前节点
        node_matches = predicate(node)
        has_matching_descendants = len(filtered_children) > 0
        
        if node_matches or (keep_ancestors and has_matching_descendants):
            result.append(node_copy)
    
    return result


__all__ = [
    "build_tree_list",
    "flatten_tree",
    "find_node_in_tree",
    "get_node_path",
    "validate_no_circular_reference",
    "calculate_tree_depth",
    "filter_tree",
]
