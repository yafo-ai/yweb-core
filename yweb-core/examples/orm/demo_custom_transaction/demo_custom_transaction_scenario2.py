"""场景2：不同模型使用不同的 Transaction 表

本脚本演示如何为订单模块和用户模块分别创建独立的 Transaction 表

运行方式：
    python demo_custom_transaction_scenario2.py
"""

import os
from datetime import datetime
from sqlalchemy import Column, BigInteger, Integer, String, DateTime, Sequence
from sqlalchemy.orm import configure_mappers, declarative_base
from yweb.orm import init_versioning
from yweb.orm import CoreModel, BaseModel

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


# ==================== 场景2：不同模型使用不同的 Transaction 表 ====================

def main():
    """主函数"""
    print_section("场景2：不同模型使用不同的 Transaction 表")
    print_info("订单模块使用 'order_audit_log'，用户模块使用 'user_audit_log'\n")
    

    
    from sqlalchemy_history import make_versioned
    from sqlalchemy_history.transaction import TransactionBase
    from sqlalchemy_history.manager import VersioningManager
    
    # ========== 订单模块的 Transaction 表 ==========
    class OrderAuditLog(CoreModel, TransactionBase):
        """订单模块审计日志"""
        __tablename__ = "order_audit_log"
        
        id = Column(
            BigInteger,
            Sequence("order_audit_log_id_seq", start=1),
            primary_key=True,
            autoincrement=True,
        )
        remote_addr = Column(String(50))
        # 订单特有字段
        order_source = Column(String(50), comment="订单来源(web/app/api)")
    
    # ========== 用户模块的 Transaction 表 ==========
    class UserAuditLog(CoreModel, TransactionBase):
        """用户模块审计日志"""
        __tablename__ = "user_audit_log"
        
        id = Column(
            BigInteger,
            Sequence("user_audit_log_id_seq", start=1),
            primary_key=True,
            autoincrement=True,
        )
        remote_addr = Column(String(50))
        # 用户特有字段
        login_session = Column(String(100), comment="登录会话ID")
    
    # 创建两个独立的 manager
    order_manager = VersioningManager(transaction_cls=OrderAuditLog)
    user_manager = VersioningManager(transaction_cls=UserAuditLog)
    
    # 初始化版本化 建议使用 init_versioning() 而不是原生的 make_versioned()
    # 因为：make_versioned 只能调用一次设置全局 manager，否则会报错
    # 这里我们使用全局 manager，然后通过 __versioned__ 配置来分离
    # 但 sqlalchemy-history 的设计限制是所有模型共享一个 Transaction 表
    
    # 实际上，要实现真正的分离，需要使用不同的方式：
    # 方案A：使用不同的数据库
    # 方案B：使用 schema 分离
    # 方案C：在模型的 __versioned__ 中配置不同的 table_name 模板
    
    # 这里演示方案C：使用不同的历史表名前缀来区分
    init_versioning(
        manager=order_manager,
        options={'table_name': '%s_version'}
    )
    
    # 定义订单模型
    class Order(CoreModel):
        """订单模型 - 使用订单审计日志"""
        __tablename__ = "demo_order"
        __versioned__ = {
            'table_name': 'order_%s_history'  # 订单模块历史表前缀
        }
        
        id = Column(Integer, primary_key=True, autoincrement=True)
        order_no = Column(String(50), comment="订单号")
        amount = Column(Integer, comment="金额(分)")
        status = Column(String(20), default="pending", comment="状态")
        created_at = Column(DateTime, default=datetime.now)
    
    # 定义用户模型 - 注意：由于 make_versioned 只能调用一次，
    # 这里用户模型也会使用同一个 Transaction 表
    class User(CoreModel):
        """用户模型"""
        __tablename__ = "demo_user"
        __versioned__ = {
            'table_name': 'user_%s_history'  # 用户模块历史表前缀
        }
        
        id = Column(Integer, primary_key=True, autoincrement=True)
        username = Column(String(50), comment="用户名")
        email = Column(String(100), comment="邮箱")
        created_at = Column(DateTime, default=datetime.now)
    
    # 配置 mappers
    configure_mappers()
    
    # 初始化数据库
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, "demo_custom_transaction_v2.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    CoreModel.metadata.create_all(engine)
    
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # 创建订单
        order = Order(order_no="ORD20240101001", amount=9900, status="pending")
        session.add(order)
        session.commit()
        print_success(f"创建订单: ID={order.id}, 订单号={order.order_no}")
        
        # 更新订单状态
        order.status = "paid"
        session.commit()
        print_success("更新订单状态为 'paid'")
        
        # 创建用户
        user = User(username="zhangsan", email="zhangsan@example.com")
        session.add(user)
        session.commit()
        print_success(f"创建用户: ID={user.id}, 用户名={user.username}")
        
        # 更新用户信息
        user.email = "zhangsan_new@example.com"
        session.commit()
        print_success("更新用户邮箱")
        
        # 查询审计日志
        audit_logs = session.query(OrderAuditLog).all()
        print_info(f"审计日志表中有 {len(audit_logs)} 条记录")
        
        # 查询订单历史
        from sqlalchemy_history import version_class
        OrderVersion = version_class(Order)
        order_versions = session.query(OrderVersion).all()
        print_info(f"订单历史表 'order_demo_order_history' 中有 {len(order_versions)} 条记录")
        for v in order_versions:
            print(f"  - ID={v.id}, 订单号={v.order_no}, 状态={v.status}, transaction_id={v.transaction_id}")
        
        # 查询用户历史
        UserVersion = version_class(User)
        user_versions = session.query(UserVersion).all()
        print_info(f"用户历史表 'user_demo_user_history' 中有 {len(user_versions)} 条记录")
        for v in user_versions:
            print(f"  - ID={v.id}, 用户名={v.username}, 邮箱={v.email}, transaction_id={v.transaction_id}")
        
        print()
        print_success("场景2演示完成！")
        print_info("注意：由于 sqlalchemy-history 的设计限制，所有模型共享一个 Transaction 表")
        print_info("但可以通过不同的历史表名前缀来区分不同模块的历史记录")
        return True
        
    except Exception as e:
        print_error(f"场景2失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        session.close()
        print_info(f"数据库文件: {db_path}")


if __name__ == "__main__":
    main()
