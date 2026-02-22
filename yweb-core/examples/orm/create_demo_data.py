#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ORM 外键关系定义示例

重要：使用 from __future__ import annotations 可以让类型注解延迟评估，
这样就可以在父类中引用还未定义的子类，且无需使用字符串引号。

本脚本演示了 yweb.orm 支持的两种外键定义方式：
- 方式1: 传统 SQLAlchemy 写法（繁琐但灵活）
- 方式2: fields.* API（Django 风格，推荐）

================================================================================
                            外键定义方式对比
================================================================================

┌─────────────────────────────────────────────────────────────────────────────┐
│ 方式1: 传统 SQLAlchemy 写法（最繁琐）                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   # 子模型：需要手动定义外键列                                                │
│   class OrderItemModel(BaseModel):                                          │
│       order_id = Column(Integer, ForeignKey("orders.id"))  # 手动定义外键    │
│       order = relationship("OrderModel", back_populates="items")            │
│                                                                             │
│   # 父模型：需要双向定义 relationship                                        │
│   class OrderModel(BaseModel):                                              │
│       __tablename__ = "orders"                                              │
│       items = relationship(                                                 │
│           "OrderItemModel",                                                 │
│           back_populates="order",                                           │
│           info={'on_delete': 'delete'}  # 级联软删除配置                    │
│       )                                                                     │
│                                                                             │
│   缺点：代码冗长，需要两边都定义，外键列名需要手动与表名匹配                    │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ 方式2: fields.ManyToOne + HasMany 类型标记（Django风格，推荐！）             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   from __future__ import annotations  # 必须放在文件最前面                  │
│   from yweb.orm import fields                                               │
│   from yweb.orm.fields import HasMany  # 类型标记，用于 IDE 提示            │
│                                                                             │
│   # 父模型：定义业务字段 + HasMany 类型标记                                  │
│   class OrderModel(BaseModel):                                              │
│       order_no = Column(String(50))                                         │
│                                                                             │
│       # HasMany 类型标记：提供 IDE 自动补全（无需双引号！）                   │
│       order_items: HasMany[OrderItemModel]                                  │
│                                                                             │
│   # 子模型：一行搞定外键 + relationship                                      │
│   class OrderItemModel(BaseModel):                                          │
│       order = fields.ManyToOne(OrderModel, on_delete=fields.DELETE)         │
│       # 自动创建：                                                          │
│       #   - order_id 列（基于表名自动生成）                                  │
│       #   - order relationship                                              │
│       #   - 父模型的 order_items backref（自动探测 HasMany 注解）            │
│                                                                             │
│   优点：                                                                    │
│   ✓ 代码简洁优雅，无需字符串引号                                             │
│   ✓ 外键列名自动基于表名生成（orders -> order_id）                           │
│   ✓ 自动创建双向 relationship                                               │
│   ✓ 支持级联软删除配置                                                      │
│   ✓ 类似 Django ORM 风格，学习成本低                                        │
│   ✓ HasMany 类型标记提供完整 IDE 自动补全                                   │
└─────────────────────────────────────────────────────────────────────────────┘

================================================================================
                          fields.ManyToOne 参数说明
================================================================================

fields.ManyToOne(
    target_model,              # 目标模型类（必须是类引用，不支持字符串）
    on_delete=fields.DELETE,   # 级联策略：
                               #   fields.DELETE     - 级联软删除子记录
                               #   fields.SET_NULL   - 清空外键（设为NULL）
                               #   fields.UNLINK     - 解除多对多关联
                               #   fields.PROTECT    - 有子记录时禁止删除
                               #   fields.DO_NOTHING - 不处理
    nullable=True,             # 外键是否可为空
    backref=True,              # 反向引用：
                               #   True  - 自动生成（order_items）
                               #   "xxx" - 自定义名称
                               #   False - 不创建
)

================================================================================
                              外键列名生成规则
================================================================================

fields.ManyToOne 会根据目标模型的 __tablename__ 自动生成外键列名：

  表名               ->    外键列名
  ─────────────────────────────────
  orders             ->    order_id        (去掉 s)
  users              ->    user_id         (去掉 s)
  categories         ->    category_id     (ies -> y)
  test_orders        ->    test_order_id   (去掉 s)
  address            ->    address_id      (保持原样)

================================================================================
"""

from __future__ import annotations  # 必须放在最前面，让类型注解延迟评估

import sys
import os
# 添加 examples 目录到路径，以便导入 test_collector
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from yweb.orm import BaseModel, CoreModel, init_database, fields
from yweb.orm.fields import HasMany  # 类型标记，用于 IDE 提示
from yweb.orm.orm_extensions import configure_cascade_soft_delete
from yweb.utils import (
    TestCollector, create_test_collector,
)


# 配置级联软删除（必须在定义模型之前调用）
configure_cascade_soft_delete()


# ==============================================================================
#                    示例：使用 fields.ManyToOne（Django 风格）
# ==============================================================================
# 
# 这里演示的是 fields.ManyToOne：在子模型定义外键关系，自动创建外键列和双向关系。
#

# 父模型：定义业务字段 + HasMany 类型标记（用于 IDE 提示）
class OrderModel(BaseModel):
    """订单模型
    
    使用 fields.ManyToOne 时，父模型无需定义 relationship。
    order_items 属性由 OrderItemModel 的 backref 自动创建。
    
    HasMany 类型标记的作用：
    - 提供 IDE 自动补全（order.order_items 会有类型提示）
    - 框架自动探测：ManyToOne 会使用 "order_items" 作为 backref 名称
    """
    __tablename__ = "test_orders"
    __table_args__ = {'extend_existing': True}
    
    # 业务字段（使用 Mapped[T] 提供 IDE 类型提示）
    order_no: Mapped[str] = mapped_column(String(50), comment="订单号")
    total_amount: Mapped[int] = mapped_column(Integer, default=0, comment="订单总金额")
    
    # HasMany 类型标记：提供 IDE 自动补全
    # 使用 from __future__ import annotations 后，无需双引号
    order_items: HasMany[OrderItemModel]


# 子模型：使用 fields.ManyToOne 定义关系
class OrderItemModel(BaseModel):
    """订单项模型
    
    使用 fields.ManyToOne 定义与父模型的关系：
    - 自动创建外键列（基于目标表名，如 test_order_id）
    - 自动创建 order relationship
    - 自动在 OrderModel 上创建 order_items backref
    - on_delete=fields.DELETE：删除订单时，级联软删除所有订单项
    
    IDE 提示说明：
    - item.order → OrderModel 类型（自动推导）
    - item.order.id → int 类型（通过 order 访问）
    - item.order.order_no → str 类型（通过 order 访问）
    """
    __table_args__ = {'extend_existing': True}
    
    # 使用 fields.ManyToOne 定义关系
    # 通过描述符协议，IDE 自动知道 order 是 OrderModel 类型
    order = fields.ManyToOne(OrderModel, on_delete=fields.DELETE)
    
    # 业务字段（使用 Mapped[T] 提供 IDE 类型提示）
    product_name: Mapped[str] = mapped_column(String(100), comment="商品名称")
    quantity: Mapped[int] = mapped_column(Integer, default=1, comment="商品数量")
    price: Mapped[int] = mapped_column(Integer, default=0, comment="商品单价")


def main():
    """主函数，演示数据库操作"""
    print("正在初始化数据库...")
    
    # 初始化数据库（使用SQLite文件数据库，保存在当前脚本运行的目录）
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, "create_demo_data.db")
    engine, session_scope = init_database(f"sqlite:///{db_path}", echo=False)
    
    # 设置 Model.query 属性（必须在 init_database 之后）
    CoreModel.query = session_scope.query_property()
    
    print("清空并重建数据表...")
    # 先删除所有表，再重新创建（确保每次运行都是干净的数据）
    BaseModel.metadata.drop_all(engine)
    BaseModel.metadata.create_all(engine)
    
    # 创建测试收集器
    tc = TestCollector(title="ORM 外键关系演示")
    
    print("开始数据库操作演示...")
    
    try:
        # ============================================================
        # 1. 创建订单和订单项
        # ============================================================
        tc.section("1. 创建订单和订单项")
        
        order = OrderModel(
            order_no="ORD20231201001",
            total_amount=1500,
            name="测试订单1",
            code="ORDER_001"
        )
        order.add(True)
        
        # 验证订单创建
        tc.check_not_none("订单创建后ID不为空", order.id)
        tc.check_equal("订单号正确", order.order_no, "ORD20231201001")
        tc.check_equal("订单总金额正确", order.total_amount, 1500)
        
        # 为订单添加订单项（通过 relationship append，外键会自动设置）
        item1 = OrderItemModel(
            product_name="iPhone 15",
            quantity=1,
            price=1000
        )
        item2 = OrderItemModel(
            product_name="AirPods Pro",
            quantity=1,
            price=500
        )
        order.order_items.append(item1)
        order.order_items.append(item2)
        order.save(True)
        
        
        # 验证订单项创建
        tc.check_not_none("订单项1的ID不为空", item1.id)
        tc.check_not_none("订单项2的ID不为空", item2.id)
        tc.check_equal("订单项1的外键指向订单", item1.order.id , order.id)
        tc.check_equal("订单项2的外键指向订单", item2.order.id, order.id)
        tc.check_equal("订单包含2个订单项", len(order.order_items), 2)
        
        # ============================================================
        # 2. 查询验证关系
        # ============================================================
        tc.section("2. 查询验证关系")
        
        order_with_items = OrderModel.query.filter(OrderModel.id == order.id).first()
        
        tc.check_not_none("能够查询到订单", order_with_items)
        tc.check_equal("查询到的订单号正确", order_with_items.order_no, "ORD20231201001")
        tc.check_equal("查询到的订单包含2个商品", len(order_with_items.order_items), 2)
        
        # 验证反向关系（通过 run_test 捕获可能的属性错误）
        def check_item1_order():
            assert hasattr(item1, 'order'), "OrderItemModel 没有 order 属性"
            assert item1.order == order, f"期望 order={order.id}, 实际 order={item1.order}"
        
        def check_item2_order():
            assert hasattr(item2, 'order'), "OrderItemModel 没有 order 属性"
            assert item2.order == order, f"期望 order={order.id}, 实际 order={item2.order}"
        
        tc.run_test("订单项1的order属性指向正确的订单", check_item1_order)
        tc.run_test("订单项2的order属性指向正确的订单", check_item2_order)
        
        # ============================================================
        # 3. 修改数据
        # ============================================================
        tc.section("3. 修改数据")
        
        # 修改订单总金额
        order.total_amount = 2000
        order.save(True)
        
        tc.check_equal("订单总金额修改成功", order.total_amount, 2000)
        
        # 修改订单项数量
        item1.quantity = 2
        item1.price = 950  # 打折
        item1.save(True)
        
        tc.check_equal("订单项1数量修改成功", item1.quantity, 2)
        tc.check_equal("订单项1价格修改成功", item1.price, 950)
        
        # 重新计算总金额
        total = sum(item.quantity * item.price for item in order.order_items)
        order.total_amount = total
        order.save(True)
        
        expected_total = 2 * 950 + 1 * 500  # 2400
        tc.check_equal("重新计算的总金额正确", order.total_amount, expected_total)
        
        # ============================================================
        # 4. 创建第二个订单
        # ============================================================
        tc.section("4. 创建第二个订单")
        
        order2 = OrderModel(
            order_no="ORD20231201002",
            total_amount=800,
            name="测试订单2",
            code="ORDER_002"
        )
        item3 = OrderItemModel(
            product_name="MacBook Air",
            quantity=1,
            price=800
        )
        
        order2.order_items.append(item3)
        order2.add(True)
        
        tc.check_not_none("第二个订单ID不为空", order2.id)
        tc.check_equal("第二个订单号正确", order2.order_no, "ORD20231201002")
        tc.check_not_none("订单项3的ID不为空", item3.id)
        tc.check_equal("订单项3的外键指向订单2", item3.order.id, order2.id)
        
        # ============================================================
        # 5. 查询所有订单
        # ============================================================
        tc.section("5. 查询所有订单")
        
        all_orders = OrderModel.query.all()
        
        tc.check_equal("共有2个订单", len(all_orders), 2)
        
        # 验证每个订单的商品数量
        order1_items = [o for o in all_orders if o.order_no == "ORD20231201001"][0]
        order2_items = [o for o in all_orders if o.order_no == "ORD20231201002"][0]
        
        tc.check_equal("订单1有2个商品", len(order1_items.order_items), 2)
        tc.check_equal("订单2有1个商品", len(order2_items.order_items), 1)
        
        # ============================================================
        # 6. 演示级联软删除
        # ============================================================
        tc.section("6. 演示级联软删除")
        
        order1_id = order.id
        items_before_delete = len(order.order_items)
        
        tc.check_equal("删除前订单1有2个订单项", items_before_delete, 2)
        
        # 从session中删除订单（由于配置了级联软删除，订单项也会被软删除）
        order.delete(True)
        
        # ============================================================
        # 7. 验证软删除效果
        # ============================================================
        tc.section("7. 验证软删除效果")
        
        # 正常查询应该看不到已删除的订单
        remaining_orders = OrderModel.query.all()
        tc.check_equal("软删除后剩余1个订单", len(remaining_orders), 1)
        tc.check_equal("剩余的是订单2", remaining_orders[0].order_no, "ORD20231201002")
        
        # 查询包含已删除记录
        all_orders_including_deleted = OrderModel.query.execution_options(include_deleted=True).all()
        tc.check_equal("包含已删除订单共2个", len(all_orders_including_deleted), 2)
        
        # 查询订单项表，验证级联软删除
        active_items_count = OrderItemModel.query.count()
        all_items_count = OrderItemModel.query.execution_options(include_deleted=True).count()
        
        tc.check_equal("活跃订单项数量为1", active_items_count, 1)
        tc.check_equal("包含已删除订单项共3个", all_items_count, 3)
        
        # 验证被级联删除的是订单1的订单项
        deleted_items = OrderItemModel.query.execution_options(include_deleted=True).filter(
            OrderItemModel.order.has(id=order1_id)
        ).all()
        tc.check_equal("订单1的订单项有2个", len(deleted_items), 2)
        tc.check("订单1的订单项都被软删除", all(item.is_deleted for item in deleted_items))
        
    except Exception as e:
        tc.check(False, f"发生未预期的错误: {e}")
        import traceback
        traceback.print_exc()
        session_scope.rollback()
    finally:
        session_scope.remove()
    
    # 输出测试汇总
    return tc.summary()


if __name__ == "__main__":
    main()
