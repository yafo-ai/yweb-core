"""
树形结构 TreeMixin 使用示例

演示 yweb.orm.tree 模块的使用方法，包括：
1. 基本的树形模型定义
2. 树形结构的 CRUD 操作
3. 树形查询方法
4. 节点移动和路径更新
5. 工具函数使用

运行方式:
    python -m examples.orm.demo_tree_mixin
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import Integer, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from yweb.orm import BaseModel, init_database
from yweb.orm.tree import (
    TreeMixin,
    TreeFieldsMixin,
    build_tree_list,
    flatten_tree,
    find_node_in_tree,
    calculate_tree_depth,
    filter_tree,
)


# ============================================================
# 方式1：自定义字段的树形模型
# ============================================================

class Menu(BaseModel, TreeMixin):
    """菜单模型 - 自定义字段方式
    
    适用于需要完全控制字段定义的场景。
    """
    __tablename__ = "demo_menu"
    
    # 树形结构必需字段
    parent_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("demo_menu.id"),
        nullable=True,
        comment="父菜单ID"
    )
    path: Mapped[str] = mapped_column(
        String(500),
        nullable=True,
        comment="菜单路径"
    )
    level: Mapped[int] = mapped_column(
        Integer,
        default=1,
        comment="菜单层级"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="排序序号"
    )
    
    # 业务字段
    title: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="菜单标题"
    )
    icon: Mapped[str] = mapped_column(
        String(50),
        nullable=True,
        comment="图标"
    )
    url: Mapped[str] = mapped_column(
        String(200),
        nullable=True,
        comment="链接地址"
    )


# ============================================================
# 方式2：使用 TreeFieldsMixin 简化定义
# ============================================================

class Category(BaseModel, TreeFieldsMixin, TreeMixin):
    """分类模型 - 使用 TreeFieldsMixin 简化字段定义
    
    TreeFieldsMixin 自动提供 path, level, sort_order 字段。
    只需要自己定义 parent_id（因为外键目标表名不同）。
    """
    __tablename__ = "demo_category"
    
    # parent_id 需要自行定义外键
    parent_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("demo_category.id"),
        nullable=True,
        comment="父分类ID"
    )
    
    # 业务字段
    title: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="分类名称"
    )
    is_active: Mapped[bool] = mapped_column(
        default=True,
        comment="是否启用"
    )


# ============================================================
# 示例函数
# ============================================================

def demo_basic_operations():
    """演示基本的树形操作"""
    print("\n" + "=" * 60)
    print("1. 基本树形操作")
    print("=" * 60)
    
    # 创建根节点
    # 注意：需要先 save 获取 id，然后再更新 path
    root = Menu(title="系统管理", icon="setting", sort_order=1)
    root.save(commit=True)  # 先保存获取 id
    root.update_path_and_level()  # 然后更新路径
    root.save(commit=True)  # 再次保存
    print(f"创建根节点: {root.title}, path={root.path}, level={root.level}")
    
    # 创建子节点
    user_mgmt = Menu(title="用户管理", icon="user", parent_id=root.id, sort_order=1)
    user_mgmt.save(commit=True)
    user_mgmt.update_path_and_level()
    user_mgmt.save(commit=True)
    print(f"创建子节点: {user_mgmt.title}, path={user_mgmt.path}, level={user_mgmt.level}")
    
    role_mgmt = Menu(title="角色管理", icon="role", parent_id=root.id, sort_order=2)
    role_mgmt.save(commit=True)
    role_mgmt.update_path_and_level()
    role_mgmt.save(commit=True)
    print(f"创建子节点: {role_mgmt.title}, path={role_mgmt.path}, level={role_mgmt.level}")
    
    # 创建三级节点
    user_list = Menu(title="用户列表", url="/user/list", parent_id=user_mgmt.id, sort_order=1)
    user_list.save(commit=True)
    user_list.update_path_and_level()
    user_list.save(commit=True)
    print(f"创建三级节点: {user_list.title}, path={user_list.path}, level={user_list.level}")
    
    user_add = Menu(title="添加用户", url="/user/add", parent_id=user_mgmt.id, sort_order=2)
    user_add.save(commit=True)
    user_add.update_path_and_level()
    user_add.save(commit=True)
    print(f"创建三级节点: {user_add.title}, path={user_add.path}, level={user_add.level}")
    
    return root, user_mgmt, role_mgmt, user_list, user_add


def demo_query_methods(root, user_mgmt, user_list):
    """演示查询方法"""
    print("\n" + "=" * 60)
    print("2. 树形查询方法")
    print("=" * 60)
    
    # 获取直接子节点
    children = root.get_children()
    print(f"\n根节点的直接子节点: {[c.title for c in children]}")
    
    # 获取所有子孙节点
    descendants = root.get_descendants()
    print(f"根节点的所有子孙节点: {[d.title for d in descendants]}")
    
    # 获取祖先节点
    ancestors = user_list.get_ancestors()
    print(f"'{user_list.title}' 的祖先节点: {[a.title for a in ancestors]}")
    
    # 获取父节点
    parent = user_list.get_parent()
    print(f"'{user_list.title}' 的父节点: {parent.title if parent else 'None'}")
    
    # 获取兄弟节点
    siblings = user_mgmt.get_siblings()
    print(f"'{user_mgmt.title}' 的兄弟节点: {[s.title for s in siblings]}")
    
    # 获取根节点
    root_node = user_list.get_root()
    print(f"'{user_list.title}' 的根节点: {root_node.title}")
    
    # 节点状态判断
    print(f"\n'{root.title}' 是根节点: {root.is_root()}")
    print(f"'{user_list.title}' 是叶子节点: {user_list.is_leaf()}")
    print(f"'{root.title}' 是 '{user_list.title}' 的祖先: {root.is_ancestor_of(user_list)}")
    print(f"'{user_list.title}' 是 '{root.title}' 的子孙: {user_list.is_descendant_of(root)}")
    
    # 统计方法
    print(f"\n'{root.title}' 的子孙数量: {root.get_descendant_count()}")
    print(f"'{root.title}' 的直接子节点数量: {root.get_children_count()}")
    print(f"'{root.title}' 子树深度: {root.get_depth()}")


def demo_path_methods(user_list):
    """演示路径相关方法"""
    print("\n" + "=" * 60)
    print("3. 路径相关方法")
    print("=" * 60)
    
    # 获取完整路径名称
    path_names = user_list.get_path_names(separator=" > ", name_field="title")
    print(f"'{user_list.title}' 的完整路径: {path_names}")
    
    # 获取路径 ID 列表
    path_ids = user_list.get_path_ids()
    print(f"'{user_list.title}' 的路径 ID 列表: {path_ids}")


def demo_move_node():
    """演示节点移动"""
    print("\n" + "=" * 60)
    print("4. 节点移动操作")
    print("=" * 60)
    
    # 创建测试数据
    root1 = Menu(title="目录A", sort_order=10)
    root1.save(commit=True)
    root1.update_path_and_level()
    root1.save(commit=True)
    
    root2 = Menu(title="目录B", sort_order=20)
    root2.save(commit=True)
    root2.update_path_and_level()
    root2.save(commit=True)
    
    child = Menu(title="子目录", parent_id=root1.id, sort_order=1)
    child.save(commit=True)
    child.update_path_and_level()
    child.save(commit=True)
    
    grandchild = Menu(title="孙子目录", parent_id=child.id, sort_order=1)
    grandchild.save(commit=True)
    grandchild.update_path_and_level()
    grandchild.save(commit=True)
    
    print(f"移动前:")
    print(f"  {child.title}: parent_id={child.parent_id}, path={child.path}")
    print(f"  {grandchild.title}: parent_id={grandchild.parent_id}, path={grandchild.path}")
    
    # 移动节点
    child.move_to(root2.id)
    child.save(commit=True)
    
    # 刷新孙子节点
    grandchild = Menu.get(grandchild.id)
    
    print(f"\n移动后（将 '{child.title}' 从 '{root1.title}' 移动到 '{root2.title}'）:")
    print(f"  {child.title}: parent_id={child.parent_id}, path={child.path}")
    print(f"  {grandchild.title}: parent_id={grandchild.parent_id}, path={grandchild.path}")


def demo_class_methods():
    """演示类方法"""
    print("\n" + "=" * 60)
    print("5. 类方法")
    print("=" * 60)
    
    # 获取所有根节点
    roots = Menu.get_roots()
    print(f"所有根节点: {[r.title for r in roots]}")
    
    # 获取树形结构列表
    tree = Menu.get_tree_list()
    print(f"\n树形结构（嵌套格式）:")
    _print_tree(tree, indent=2)


def demo_utility_functions():
    """演示工具函数"""
    print("\n" + "=" * 60)
    print("6. 工具函数")
    print("=" * 60)
    
    # 准备测试数据
    flat_data = [
        {"id": 1, "parent_id": None, "title": "根1", "is_active": True},
        {"id": 2, "parent_id": 1, "title": "子1-1", "is_active": True},
        {"id": 3, "parent_id": 1, "title": "子1-2", "is_active": False},
        {"id": 4, "parent_id": 2, "title": "孙1-1-1", "is_active": True},
        {"id": 5, "parent_id": None, "title": "根2", "is_active": True},
    ]
    
    # build_tree_list: 将扁平列表构建为嵌套树
    tree = build_tree_list(flat_data)
    print("\nbuild_tree_list - 将扁平列表构建为嵌套树:")
    _print_tree(tree, indent=2, title_field="title")
    
    # flatten_tree: 将嵌套树展平为列表
    flat = flatten_tree(tree, level_field="depth")
    print("\nflatten_tree - 将嵌套树展平为列表:")
    for item in flat:
        print(f"  {item['title']} (depth={item.get('depth', '?')})")
    
    # find_node_in_tree: 在树中查找节点
    found = find_node_in_tree(tree, target_id=4)
    print(f"\nfind_node_in_tree - 查找 id=4 的节点: {found['title'] if found else 'Not found'}")
    
    # calculate_tree_depth: 计算树的深度
    depth = calculate_tree_depth(tree)
    print(f"\ncalculate_tree_depth - 树的最大深度: {depth}")
    
    # filter_tree: 过滤树节点
    filtered = filter_tree(tree, lambda n: n.get("is_active", False))
    print("\nfilter_tree - 只保留 is_active=True 的节点:")
    _print_tree(filtered, indent=2, title_field="title")


def demo_category_model():
    """演示使用 TreeFieldsMixin 的模型"""
    print("\n" + "=" * 60)
    print("7. 使用 TreeFieldsMixin 的模型（Category）")
    print("=" * 60)
    
    # 创建分类树
    electronics = Category(title="电子产品")
    electronics.save(commit=True)
    electronics.update_path_and_level()
    electronics.save(commit=True)
    
    phones = Category(title="手机", parent_id=electronics.id)
    phones.save(commit=True)
    phones.update_path_and_level()
    phones.save(commit=True)
    
    computers = Category(title="电脑", parent_id=electronics.id)
    computers.save(commit=True)
    computers.update_path_and_level()
    computers.save(commit=True)
    
    iphone = Category(title="iPhone", parent_id=phones.id)
    iphone.save(commit=True)
    iphone.update_path_and_level()
    iphone.save(commit=True)
    
    print(f"创建分类树:")
    print(f"  {electronics.title} (level={electronics.level})")
    print(f"    ├── {phones.title} (level={phones.level})")
    print(f"    │   └── {iphone.title} (level={iphone.level})")
    print(f"    └── {computers.title} (level={computers.level})")
    
    # 获取树形结构
    tree = Category.get_tree_list()
    print(f"\n分类树形结构:")
    _print_tree(tree, indent=2, title_field="title")


def _print_tree(nodes, indent=0, title_field="title"):
    """打印树形结构"""
    for node in nodes:
        title = node.get(title_field) or node.get("name") or f"ID:{node.get('id')}"
        print(" " * indent + f"- {title}")
        children = node.get("children", [])
        if children:
            _print_tree(children, indent + 2, title_field)


def main():
    """主函数"""
    print("=" * 60)
    print("TreeMixin 使用示例")
    print("=" * 60)
    
    # 初始化内存数据库
    # init_database 返回 engine 和 session_scope
    from yweb.orm import Base
    engine, session_scope = init_database("sqlite:///:memory:", echo=False)
    
    # 创建表
    Base.metadata.create_all(engine)
    
    try:
        # 运行示例
        root, user_mgmt, role_mgmt, user_list, user_add = demo_basic_operations()
        demo_query_methods(root, user_mgmt, user_list)
        demo_path_methods(user_list)
        demo_move_node()
        demo_class_methods()
        demo_utility_functions()
        demo_category_model()
        
        print("\n" + "=" * 60)
        print("示例完成!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n[Error] {e}")
        import traceback
        traceback.print_exc()
        session_scope.rollback()
    finally:
        session_scope.remove()


if __name__ == "__main__":
    main()
