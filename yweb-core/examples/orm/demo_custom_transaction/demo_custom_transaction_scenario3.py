"""场景3：扩展 Transaction 表字段

本脚本演示如何添加更多业务相关的元数据字段到 Transaction 表

运行方式：
    python demo_custom_transaction_scenario3.py
"""

import os
from datetime import datetime
from sqlalchemy import Column, BigInteger, Integer, String, Text, DateTime, Sequence
from sqlalchemy.orm import configure_mappers, declarative_base
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


# ==================== 场景3：扩展 Transaction 表字段 ====================

def main():
    """主函数"""
    print_section("场景3：扩展 Transaction 表字段")
    print_info("添加 request_id, user_agent, operation_type 等字段\n")
    
    # 创建独立的 declarative base
    Base = declarative_base()
    
    from sqlalchemy_history.transaction import TransactionBase
    from sqlalchemy_history.manager import VersioningManager
    
    # 创建扩展的 Transaction 类
    class ExtendedTransaction(Base, TransactionBase):
        """扩展的事务记录表"""
        __tablename__ = "extended_transaction"
        
        id = Column(
            BigInteger,
            Sequence("extended_transaction_id_seq", start=1),
            primary_key=True,
            autoincrement=True,
        )
        
        # 基础字段
        remote_addr = Column(String(50), comment="客户端IP地址")
        
        # 扩展字段
        request_id = Column(String(64), index=True, comment="请求追踪ID")
        user_agent = Column(String(500), comment="用户代理")
        referer = Column(String(500), comment="来源页面")
        operation_module = Column(String(100), comment="操作模块")
        operation_action = Column(String(100), comment="操作动作")
        operation_reason = Column(Text, comment="操作原因/备注")
        extra_data = Column(Text, comment="扩展数据(JSON)")
    
    # 创建 manager
    extended_manager = VersioningManager(transaction_cls=ExtendedTransaction)
    
    # 初始化版本化
    init_versioning(manager=extended_manager)
    
    # 定义模型
    class Article(Base):
        """文章模型"""
        __tablename__ = "demo_article"
        __versioned__ = {}
        
        id = Column(Integer, primary_key=True, autoincrement=True)
        title = Column(String(200), comment="标题")
        content = Column(Text, comment="内容")
        author = Column(String(100), comment="作者")
        status = Column(String(20), default="draft", comment="状态")
        created_at = Column(DateTime, default=datetime.now)
    
    # 配置 mappers
    configure_mappers()
    
    # 初始化数据库
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, "demo_custom_transaction_v3.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    Base.metadata.create_all(engine)
    
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # 创建文章
        article = Article(
            title="Python 最佳实践",
            content="这是一篇关于 Python 最佳实践的文章...",
            author="张三",
            status="draft"
        )
        session.add(article)
        session.commit()
        print_success(f"创建文章: ID={article.id}")
        
        # 手动设置事务扩展字段（在实际应用中，可以通过中间件自动设置）
        # 注意：这需要在 commit 之前获取并设置 transaction 对象
        # 由于 sqlalchemy-history 的工作流程，这需要特殊处理
        
        # 更新文章
        article.title = "Python 最佳实践（修订版）"
        article.status = "published"
        session.commit()
        print_success("更新文章状态为 'published'")
        
        # 再次更新
        article.content = "更新后的内容..."
        session.commit()
        print_success("更新文章内容")
        
        # 查询事务表
        transactions = session.query(ExtendedTransaction).order_by(ExtendedTransaction.id).all()
        print_info(f"扩展事务表中有 {len(transactions)} 条记录：")
        for tx in transactions:
            print(f"  - ID={tx.id}")
            print(f"    时间: {tx.issued_at}")
            print(f"    IP: {tx.remote_addr}")
            print(f"    请求ID: {tx.request_id}")
            print(f"    模块: {tx.operation_module}")
            print(f"    动作: {tx.operation_action}")
        
        # 查询历史表
        from sqlalchemy_history import version_class
        ArticleVersion = version_class(Article)
        versions = session.query(ArticleVersion).order_by(ArticleVersion.transaction_id).all()
        print_info(f"文章历史表中有 {len(versions)} 条记录：")
        for v in versions:
            print(f"  - ID={v.id}, 标题={v.title}, 状态={v.status}, transaction_id={v.transaction_id}")
        
        print()
        print_success("场景3演示完成！")
        print_info("提示：扩展字段可以通过中间件或事件监听器自动填充")
        return True
        
    except Exception as e:
        print_error(f"场景3失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        session.close()
        print_info(f"数据库文件: {db_path}")


if __name__ == "__main__":
    main()
