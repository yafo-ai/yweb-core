"""排序管理 Mixin 使用示例

演示 SortableMixin 的各种使用场景：
1. 简单列表排序（无分组）
2. 单字段分组排序
3. 多字段分组排序
4. 与 TreeMixin 结合使用
"""

import sys
from pathlib import Path

# 添加 yweb-core 到 path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import Integer, String, ForeignKey, create_engine
from sqlalchemy.orm import Mapped, mapped_column, Session

from yweb.orm import (
    BaseModel,
    Base,
    init_database,
    SortFieldMixin,
    SortableMixin,
)
from yweb.orm.tree import TreeFieldsMixin, TreeMixin


# ==================== 示例 1: 简单列表排序 ====================

class Banner(BaseModel, SortFieldMixin, SortableMixin):
    """轮播图模型 - 简单排序示例
    
    无分组，所有记录共用一个排序序列。
    """
    __tablename__ = "demo_banner"
    
    title: Mapped[str] = mapped_column(String(100), comment="标题")
    image_url: Mapped[str] = mapped_column(String(500), comment="图片地址")


# ==================== 示例 2: 单字段分组排序 ====================

class Product(BaseModel, SortFieldMixin, SortableMixin):
    """产品模型 - 按分类分组排序示例
    
    同一分类内的产品共用一个排序序列。
    """
    __tablename__ = "demo_product"
    __sort_group_by__ = "category_id"  # 按分类分组
    
    category_id: Mapped[int] = mapped_column(Integer, comment="分类ID")
    name: Mapped[str] = mapped_column(String(100), comment="产品名称")
    price: Mapped[int] = mapped_column(Integer, default=0, comment="价格（分）")


# ==================== 示例 3: 多字段分组排序 ====================

class MenuItem(BaseModel, SortFieldMixin, SortableMixin):
    """菜单项 - 多字段分组排序示例
    
    按 (menu_id, parent_id) 组合分组，实现菜单内同级项排序。
    """
    __tablename__ = "demo_menu_item"
    __sort_group_by__ = ["menu_id", "parent_id"]  # 多字段分组
    
    menu_id: Mapped[int] = mapped_column(Integer, comment="所属菜单ID")
    parent_id: Mapped[int] = mapped_column(Integer, nullable=True, default=None, comment="父级ID")
    title: Mapped[str] = mapped_column(String(100), comment="标题")
    url: Mapped[str] = mapped_column(String(500), nullable=True, comment="链接")


# ==================== 示例 4: 与 TreeMixin 结合 ====================

class Category(BaseModel, TreeFieldsMixin, TreeMixin, SortableMixin):
    """分类模型 - 树形结构 + 排序示例
    
    TreeFieldsMixin 已继承 SortFieldMixin，自动包含 sort_order 字段。
    配置 __sort_group_by__ = "parent_id" 实现同级节点排序。
    """
    __tablename__ = "demo_category"
    __sort_group_by__ = "parent_id"  # 按父节点分组
    
    parent_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("demo_category.id"), 
        nullable=True, 
        default=None,
        comment="父分类ID"
    )
    name: Mapped[str] = mapped_column(String(100), comment="分类名称")


# ==================== 演示函数 ====================

def demo_simple_sorting(session: Session):
    """演示简单列表排序"""
    print("\n" + "=" * 60)
    print("Demo 1: Simple List Sorting (Banner)")
    print("=" * 60)
    
    # 创建测试数据
    banners = [
        Banner(title="Banner 1", image_url="/img/1.jpg"),
        Banner(title="Banner 2", image_url="/img/2.jpg"),
        Banner(title="Banner 3", image_url="/img/3.jpg"),
    ]
    
    for i, banner in enumerate(banners, 1):
        banner.sort_order = i
        session.add(banner)
    session.commit()
    
    print("\n[Initial order]")
    for b in Banner.get_sorted():
        print(f"  {b.sort_order}. {b.title}")
    
    # 上移 Banner 3
    banner3 = session.query(Banner).filter_by(title="Banner 3").first()
    print(f"\n[Move up: {banner3.title}]")
    banner3.move_up()
    session.commit()
    
    for b in Banner.get_sorted():
        print(f"  {b.sort_order}. {b.title}")
    
    # 置顶 Banner 3
    print(f"\n[Move to top: {banner3.title}]")
    banner3.move_to_top()
    session.commit()
    
    for b in Banner.get_sorted():
        print(f"  {b.sort_order}. {b.title}")
    
    # 批量重排序
    print("\n[Bulk reorder: [Banner 1, Banner 2, Banner 3]]")
    ids = [b.id for b in session.query(Banner).filter(Banner.title.in_(["Banner 1", "Banner 2", "Banner 3"])).all()]
    # 按标题排序获取正确顺序
    ordered_ids = []
    for title in ["Banner 1", "Banner 2", "Banner 3"]:
        b = session.query(Banner).filter_by(title=title).first()
        ordered_ids.append(b.id)
    
    Banner.reorder(ordered_ids)
    session.commit()
    
    for b in Banner.get_sorted():
        print(f"  {b.sort_order}. {b.title}")


def demo_grouped_sorting(session: Session):
    """演示分组排序"""
    print("\n" + "=" * 60)
    print("Demo 2: Grouped Sorting (Product by Category)")
    print("=" * 60)
    
    # 创建测试数据：两个分类，每个分类3个产品
    products = [
        # 分类 1
        Product(category_id=1, name="Product A1", price=100, sort_order=1),
        Product(category_id=1, name="Product A2", price=200, sort_order=2),
        Product(category_id=1, name="Product A3", price=300, sort_order=3),
        # 分类 2
        Product(category_id=2, name="Product B1", price=150, sort_order=1),
        Product(category_id=2, name="Product B2", price=250, sort_order=2),
    ]
    
    for p in products:
        session.add(p)
    session.commit()
    
    print("\n[Initial order by category]")
    print("  Category 1:")
    for p in Product.get_sorted({"category_id": 1}):
        print(f"    {p.sort_order}. {p.name}")
    print("  Category 2:")
    for p in Product.get_sorted({"category_id": 2}):
        print(f"    {p.sort_order}. {p.name}")
    
    # 在分类1中移动 A3 到顶部
    a3 = session.query(Product).filter_by(name="Product A3").first()
    print(f"\n[Move to top in Category 1: {a3.name}]")
    a3.move_to_top()
    session.commit()
    
    print("  Category 1:")
    for p in Product.get_sorted({"category_id": 1}):
        print(f"    {p.sort_order}. {p.name}")
    print("  Category 2 (unchanged):")
    for p in Product.get_sorted({"category_id": 2}):
        print(f"    {p.sort_order}. {p.name}")


def demo_tree_sorting(session: Session):
    """演示树形结构排序"""
    print("\n" + "=" * 60)
    print("Demo 3: Tree Structure Sorting (Category)")
    print("=" * 60)
    
    # 创建树形分类
    # 根分类
    root1 = Category(name="Electronics", parent_id=None, sort_order=1)
    root2 = Category(name="Clothing", parent_id=None, sort_order=2)
    session.add_all([root1, root2])
    session.commit()
    
    # 更新路径
    root1.update_path_and_level()
    root2.update_path_and_level()
    session.commit()
    
    # 子分类
    sub1 = Category(name="Phones", parent_id=root1.id, sort_order=1)
    sub2 = Category(name="Laptops", parent_id=root1.id, sort_order=2)
    sub3 = Category(name="Tablets", parent_id=root1.id, sort_order=3)
    session.add_all([sub1, sub2, sub3])
    session.commit()
    
    # 更新子分类路径
    sub1.update_path_and_level()
    sub2.update_path_and_level()
    sub3.update_path_and_level()
    session.commit()
    
    print("\n[Initial tree structure]")
    print_tree(session)
    
    # 在 Electronics 子分类中移动 Tablets 到顶部
    tablets = session.query(Category).filter_by(name="Tablets").first()
    print(f"\n[Move to top in Electronics children: {tablets.name}]")
    tablets.move_to_top()
    session.commit()
    
    print_tree(session)
    
    # 交换根分类顺序
    electronics = session.query(Category).filter_by(name="Electronics").first()
    clothing = session.query(Category).filter_by(name="Clothing").first()
    print(f"\n[Swap root categories: {electronics.name} <-> {clothing.name}]")
    electronics.swap_with(clothing)
    session.commit()
    
    print_tree(session)


def print_tree(session: Session):
    """打印分类树"""
    def print_node(node, indent=0):
        print(f"  {'  ' * indent}{node.sort_order}. {node.name} (level={node.level}, path={node.path})")
        children = session.query(Category).filter_by(parent_id=node.id).order_by(Category.sort_order).all()
        for child in children:
            print_node(child, indent + 1)
    
    roots = session.query(Category).filter_by(parent_id=None).order_by(Category.sort_order).all()
    for root in roots:
        print_node(root)


def demo_utility_methods(session: Session):
    """演示工具方法"""
    print("\n" + "=" * 60)
    print("Demo 4: Utility Methods")
    print("=" * 60)
    
    # 获取位置信息
    b1 = session.query(Banner).filter_by(title="Banner 1").first()
    if b1:
        position = b1.get_sort_position()
        prev_item = b1.get_previous()
        next_item = b1.get_next()
        
        print(f"\n[Banner 1 position info]")
        print(f"  Position: {position}")
        print(f"  Previous: {prev_item.title if prev_item else 'None'}")
        print(f"  Next: {next_item.title if next_item else 'None'}")
    
    # 获取最大/最小排序号
    max_order = Banner.get_max_sort_order()
    min_order = Banner.get_min_sort_order()
    print(f"\n[Banner sort order range]")
    print(f"  Min: {min_order}")
    print(f"  Max: {max_order}")
    
    # 分组的最大排序号
    max_cat1 = Product.get_max_sort_order({"category_id": 1})
    max_cat2 = Product.get_max_sort_order({"category_id": 2})
    print(f"\n[Product max sort order by category]")
    print(f"  Category 1: {max_cat1}")
    print(f"  Category 2: {max_cat2}")


def main():
    """主函数"""
    print("=" * 60)
    print("SortableMixin Demo")
    print("=" * 60)
    
    # 初始化数据库（内存数据库）
    # init_database 返回 engine 和 session_scope
    engine, session_scope = init_database("sqlite:///:memory:", echo=False)
    
    # 创建所有表
    Base.metadata.create_all(engine)
    
    # 获取会话
    session = Banner.query.session
    
    try:
        # 运行演示
        demo_simple_sorting(session)
        demo_grouped_sorting(session)
        demo_tree_sorting(session)
        demo_utility_methods(session)
        
        print("\n" + "=" * 60)
        print("All demos completed successfully!")
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
