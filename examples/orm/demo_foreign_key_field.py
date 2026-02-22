#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
fields.ManyToOne（Django 风格，最简洁，推荐！）

本脚本演示如何使用 fields.ManyToOne 简化外键定义。

================================================================================
                        fields.ManyToOne 自动完成以下工作
================================================================================

只需一行代码：
    order = fields.ManyToOne(OrderModel, on_delete=fields.DELETE)

自动创建：
    ✓ 外键列：fk_test_order_id（基于表名 fk_test_orders 生成）
    ✓ relationship：order（指向 OrderModel）
    ✓ backref：order_items（在 OrderModel 上创建反向引用）
    ✓ 级联软删除配置

================================================================================
"""

from sqlalchemy import Column, String, Integer
from yweb.orm import BaseModel, CoreModel, init_database, fields
from yweb.orm.orm_extensions import configure_cascade_soft_delete
from yweb.utils import TestCollector


# 配置级联软删除（必须在定义模型之前调用）
configure_cascade_soft_delete()


# ==============================================================================
#                    示例：使用 fields.ManyToOne
# ==============================================================================

# 父模型：只需定义业务字段，无需定义 relationship
class OrderModel(BaseModel):
    """订单模型
    
    使用 fields.ManyToOne 时，父模型只需定义自己的业务字段。
    order_items 反向引用由子模型的 fields.ManyToOne 自动创建。
    """
    __tablename__ = "fk_test_orders"
    __table_args__ = {'extend_existing': True}
    
    order_no = Column(String(50))
    total_amount = Column(Integer, default=0)
    
    # 注意：order_items 属性由 OrderItemModel 的 fields.ManyToOne 自动创建


# 子模型：使用 fields.ManyToOne 一行定义完整关系
class OrderItemModel(BaseModel):
    """订单项模型
    
    使用 fields.ManyToOne 定义与父模型的关系：
    - 自动创建外键列：fk_test_order_id（基于父表名生成）
    - 自动创建 relationship：order
    - 自动在父模型创建 backref：order_items
    - 配置级联软删除：on_delete=fields.DELETE
    """
    __tablename__ = "fk_test_order_items"
    __table_args__ = {'extend_existing': True}
    
    # Django 风格：一行定义完整的外键关系！
    order = fields.ManyToOne(OrderModel, on_delete=fields.DELETE)
    # 等价于以下传统写法：
    #   fk_test_order_id = Column(Integer, ForeignKey("fk_test_orders.id"))
    #   order = relationship(OrderModel, foreign_keys=[fk_test_order_id],
    #                        backref=backref("order_items", info={...}))
    
    # 业务字段
    product_name = Column(String(100))
    quantity = Column(Integer, default=1)
    price = Column(Integer, default=0)


def main():
    """主函数，演示 fields.ManyToOne 的使用"""
    # 创建测试收集器
    tc = TestCollector(title="fields.ManyToOne 测试")
    
    print("=" * 60)
    print("测试 Django 风格的 fields.ManyToOne")
    print("=" * 60)
    
    # 初始化数据库
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, "demo_foreign_key_field.db")
    engine, session_scope = init_database(f"sqlite:///{db_path}", echo=False)
    
    # 设置 Model.query 属性
    CoreModel.query = session_scope.query_property()
    
    # 重建数据表
    print("\n清空并重建数据表...")
    BaseModel.metadata.drop_all(engine)
    BaseModel.metadata.create_all(engine)
    
    print("\n--- 1. 验证自动创建的列和关系 ---")
    
    # 检查 OrderItemModel 是否有 order_id 列
    from sqlalchemy import inspect
    mapper = inspect(OrderItemModel)
    columns = [c.key for c in mapper.columns]
    relationships = list(mapper.relationships.keys())
    
    print(f"OrderItemModel 的列: {columns}")
    print(f"OrderItemModel 的关系: {relationships}")
    
    # 外键列名基于目标表名生成：fk_test_orders -> fk_test_order_id
    assert 'fk_test_order_id' in columns, "应该自动创建 fk_test_order_id 列（基于表名）"
    assert 'order' in relationships, "应该自动创建 order relationship"
    print("[OK] 外键列和关系自动创建成功！")
    print(f"    外键列名: fk_test_order_id（基于表名 fk_test_orders 生成）")
    
    print("\n--- 2. 创建订单和订单项 ---")
    
    # 创建订单
    order = OrderModel(
        order_no="ORD-FK-001",
        total_amount=1500,
        name="fields.ManyToOne测试订单",
        code="FK_ORDER_001"
    )
    order.add(True)
    print(f"创建订单: ID={order.id}, 订单号={order.order_no}")
    
    # 创建订单项（通过 relationship 的 append）
    item1 = OrderItemModel(
        product_name="iPhone 15",
        quantity=1,
        price=1000
    )
    order.order_items.append(item1)  # 通过父对象的集合添加，外键会自动设置
    item1.add(True)
    
    # 创建订单项（也通过 relationship 添加，确保级联删除正常工作）
    item2 = OrderItemModel(
        product_name="AirPods Pro",
        quantity=1,
        price=500
    )
    order.order_items.append(item2)  # 同样通过 relationship 添加
    item2.add(True)
    
    print(f"创建订单项1: {item1.product_name}, order_id={item1.fk_test_order_id}")
    print(f"创建订单项2: {item2.product_name}, order_id={item2.fk_test_order_id}")
    
    print("\n--- 3. 验证关系查询 ---")
    
    # 检查 OrderModel 是否有 backref（order_items）
    order_mapper = inspect(OrderModel)
    order_relationships = list(order_mapper.relationships.keys())
    print(f"OrderModel 的关系: {order_relationships}")
    
    # 从订单访问订单项（通过 backref）
    if hasattr(order, 'order_items'):
        print(f"订单 {order.order_no} 包含 {len(order.order_items)} 个商品:")
        for item in order.order_items:
            print(f"  - {item.product_name}: {item.quantity} x {item.price}")
    
    # 从订单项访问订单
    print(f"\n订单项1关联的订单: {item1.order.order_no}")
    
    tc.section("4. 验证级联软删除")
    
    # 重新查询订单以确保关系正确加载
    order = OrderModel.query.filter(OrderModel.id == order.id).first()
    
    # 查询删除前的数量
    items_before = OrderItemModel.query.count()
    tc.check_equal("删除前订单项数量", items_before, 2)
    tc.check_equal("订单关联的订单项数量", len(order.order_items), 2)
    
    # 保存 ID，因为 delete 后对象属性会过期
    order_id = order.id
    item_ids = [item.id for item in order.order_items]
    
    # 删除订单（应该级联软删除订单项）
    order.delete(True)
    
    # 验证订单软删除是否成功
    deleted_order = OrderModel.query.execution_options(include_deleted=True).filter_by(id=order_id).first()
    tc.check_not_none("能查询到已删除的订单", deleted_order)
    tc.check("订单已被软删除", deleted_order and deleted_order.is_deleted)
    
    # 查询删除后的数量
    items_after = OrderItemModel.query.count()
    items_all = OrderItemModel.query.execution_options(include_deleted=True).count()
    
    tc.check_equal("删除后活跃订单项数量", items_after, 0)
    tc.check_equal("包含已删除的订单项总数", items_all, 2)
    
    # 验证被级联删除的订单项
    deleted_items = OrderItemModel.query.execution_options(include_deleted=True).filter(
        OrderItemModel.id.in_(item_ids)
    ).all()
    tc.check_equal("被级联删除的订单项数量", len(deleted_items), 2)
    tc.check("所有订单项都被软删除", all(item.is_deleted for item in deleted_items))
    
    print("\n" + "=" * 60)
    print("fields.ManyToOne 测试完成！")
    print("=" * 60)
    
    session_scope.remove()
    
    # 输出测试汇总
    return tc.summary()


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
