"""调试 PROTECT 行为"""

from sqlalchemy import Column, String
from yweb.orm import (
    CoreModel,
    BaseModel,
    init_database,
    fields,
    configure_cascade_soft_delete,
    activate_soft_delete_hook,
)


class DebugCategoryModel(BaseModel):
    """分类模型"""
    __tablename__ = "debug_categories"
    __table_args__ = {'extend_existing': True}

    category_name = Column(String(100))
    # products 属性由 DebugProductModel 的 backref 自动创建


class DebugProductModel(BaseModel):
    """产品模型"""
    __tablename__ = "debug_products"
    __table_args__ = {'extend_existing': True}

    product_name = Column(String(100))

    # PROTECT：有产品时禁止删除分类
    category = fields.ManyToOne(DebugCategoryModel, on_delete=fields.PROTECT, nullable=True)


def main():
    # 初始化
    activate_soft_delete_hook()
    configure_cascade_soft_delete()
    # 初始化数据库（使用SQLite文件数据库，保存在当前脚本运行的目录）
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, "demo_protect_debug.db")
    engine, session_scope = init_database(f"sqlite:///{db_path}", echo=False)

    CoreModel.query = session_scope.query_property()
    BaseModel.metadata.create_all(engine)

    print("=== 测试 PROTECT 行为 ===\n")

    # 创建分类
    category = DebugCategoryModel(
        category_name="电子产品",
        name="分类1",
        code="CAT_001"
    )
    category.add(True)
    print(f"[OK] 创建分类: ID={category.id}")

    # 添加产品
    product = DebugProductModel(
        product_name="iPhone",
        name="产品1",
        code="PROD_001"
    )
    category.debug_products.append(product)
    category.save(True)
    print(f"[OK] 添加产品: ID={product.id}")

    category_id = category.id
    product_id = product.id

    # 尝试删除分类
    print("\n尝试删除有产品的分类...")
    delete_blocked = False
    try:
        category.delete(True)  # 这里应该抛出异常
        print("[FAIL] 没有抛出异常！分类被删除了")
    except ValueError as e:
        print(f"[OK] PROTECT 生效，捕获到 ValueError: {e}")
        delete_blocked = True
        # 重要：异常后需要回滚 session，否则后续查询会有问题
        session_scope.rollback()
    except Exception as e:
        print(f"[FAIL] 捕获到非预期异常 {type(e).__name__}: {e}")
        session_scope.rollback()

    # 检查状态
    print("\n检查删除后的状态...")
    try:
        category_check = DebugCategoryModel.query.execution_options(include_deleted=True).filter_by(id=category_id).first()
        product_check = DebugProductModel.query.execution_options(include_deleted=True).filter_by(id=product_id).first()

        if category_check:
            if category_check.is_deleted:
                print(f"[FAIL] 分类被删除了: is_deleted={category_check.is_deleted}")
            else:
                print(f"[OK] 分类未被删除: is_deleted={category_check.is_deleted}")
        else:
            print("[FAIL] 分类不存在")

        if product_check:
            if product_check.is_deleted:
                print(f"[FAIL] 产品被删除了: is_deleted={product_check.is_deleted}")
            else:
                print(f"[OK] 产品未被删除: is_deleted={product_check.is_deleted}")
        else:
            print("[FAIL] 产品不存在")
            
        # 最终结果
        if delete_blocked and category_check and not category_check.is_deleted:
            print("\n[OK] PROTECT 测试通过！有子记录时成功阻止了删除")
        else:
            print("\n[FAIL] PROTECT 测试失败")
            
    except Exception as e:
        print(f"[FAIL] 查询时发生异常: {type(e).__name__}: {e}")

    session_scope.remove()


if __name__ == "__main__":
    main()
