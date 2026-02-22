"""场景4：使用 yweb.orm 集成自定义 Transaction

本脚本演示如何在 yweb.orm 框架中使用自定义 Transaction 表

运行方式：
    python demo_custom_transaction_scenario4.py
"""

import os
from sqlalchemy import Column, BigInteger, Integer, String, Sequence
from sqlalchemy.orm import configure_mappers, Mapped, mapped_column, declarative_base
from yweb.orm import init_versioning

# ==================== 辅助函数 ====================

def print_section(title: str):
    """打印章节标题"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def print_success(message: str):
    """打印成功消息"""
    print(f"[OK] {message}")


def print_error(message: str):
    """打印错误消息"""
    print(f"[ERROR] {message}")


def print_info(message: str):
    """打印信息"""
    print(f"[INFO] {message}")


# ==================== 场景4：使用 yweb.orm 集成自定义 Transaction ====================

def main():
    """主函数"""
    print_section("场景4：yweb.orm 集成自定义 Transaction")
    print_info("使用 init_versioning() 的 transaction_cls 参数\n")
    
    # 创建独立的 Base（用于定义 Transaction 类）
    TxBase = declarative_base()
    
    from sqlalchemy_history.transaction import TransactionBase
    
    # 自定义 Transaction 类
    class YWebTransaction(TxBase, TransactionBase):
        """YWeb 框架的自定义事务表"""
        __tablename__ = "yweb_audit_log"
        
        id = Column(
            BigInteger,
            Sequence("yweb_audit_log_id_seq", start=1),
            primary_key=True,
            autoincrement=True,
        )
        remote_addr = Column(String(50))
        request_id = Column(String(64), index=True, comment="请求ID")
        user_id = Column(String(64), comment="操作用户ID")
        tenant_id = Column(String(64), comment="租户ID")
    
    # 使用 yweb.orm 的 init_versioning，传入自定义 transaction_cls
    from yweb.orm import init_database, CoreModel, BaseModel
    
    try:
        init_versioning(transaction_cls=YWebTransaction)
        print_success("使用自定义 Transaction 类初始化版本化功能")
    except Exception as e:
        print_info(f"版本化已初始化: {e}")
    
    # 使用 yweb.orm 的 BaseModel
    class Product(BaseModel):
        """产品模型"""
        __tablename__ = "demo_product_v4"
        __table_args__ = {'extend_existing': True}
        
        enable_history = True  # 启用版本历史
        
        product_name: Mapped[str] = mapped_column(String(200), nullable=True)
        price: Mapped[int] = mapped_column(Integer, default=0, comment="价格(分)")
        stock: Mapped[int] = mapped_column(Integer, default=0, comment="库存")
    
    # 配置 mappers
    configure_mappers()
    
    # 初始化数据库
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, "demo_custom_transaction_v4.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    
    engine, session_scope = init_database(f"sqlite:///{db_path}", echo=False)
    
    # 同时创建 TxBase 的表
    TxBase.metadata.create_all(engine)
    BaseModel.metadata.create_all(engine)
    
    CoreModel.query = session_scope.query_property()
    session = session_scope()
    
    try:
        # 创建产品
        product = Product(
            name="iPhone 15",
            code="IPHONE15",
            product_name="Apple iPhone 15 128GB",
            price=599900,
            stock=100
        )
        product.add(True)
        print_success(f"创建产品: ID={product.id}")
        
        # 更新产品价格
        product.price = 549900
        product.save(True)
        print_success("更新产品价格")
        
        # 更新库存
        product.stock = 95
        product.save(True)
        print_success("更新产品库存")
        
        # 查询历史
        from yweb.orm import get_history_count, get_history
        count = get_history_count(Product, product.id, session=session)
        print_info(f"产品历史记录数: {count}")
        
        history = get_history(Product, product.id, session=session)
        if history:
            print_info("历史记录详情:")
            for i, h in enumerate(history, 1):
                print(f"  [{i}] 价格={h.get('price')}, 库存={h.get('stock')}, transaction_id={h.get('transaction_id')}")
        
        print()
        print_success("场景4演示完成！")
        return True
        
    except Exception as e:
        print_error(f"场景4失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        session_scope.remove()
        print_info(f"数据库文件: {db_path}")


if __name__ == "__main__":
    main()
