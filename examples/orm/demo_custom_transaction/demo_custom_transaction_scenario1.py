"""场景1：自定义 Transaction 表名

本脚本演示如何将默认的 "transaction" 表名改为自定义的名称，如 "audit_log"

运行方式：
    python demo_custom_transaction_scenario1.py
"""

import os
from datetime import datetime
from sqlalchemy import Column, BigInteger, Integer, String, Text, DateTime, Sequence
from sqlalchemy.orm import configure_mappers, declarative_base
from yweb.orm import init_versioning
from yweb.orm import BaseModel,CoreModel

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


# ==================== 场景1：自定义 Transaction 表名 ====================

def main():
    """主函数"""
    print_section("场景1：自定义 Transaction 表名")
    print_info("将默认的 'transaction' 表名改为 'audit_log'\n")
    
    # 创建独立的 declarative base
    
    # 导入 sqlalchemy-history 组件
    from sqlalchemy_history.transaction import TransactionBase
    from sqlalchemy_history.manager import VersioningManager
    
    from yweb.orm import configure_primary_key, IdType,IdModel
    # 设置全局配置为 SNOWFLAKE， transaction 表 主键会自动 使用全局配置
    configure_primary_key(strategy=IdType.SNOWFLAKE)
    
   # 创建自定义 Transaction 类
    class AuditLog(IdModel, TransactionBase):
        """自定义审计日志表 - 替代默认的 transaction 表"""
        __tablename__ = "audit_log"  # 自定义表名
        
        # id会自动根据 IdModel的设置生成
        # 这里指定无效，如果类型不一直还会冲突，这里只是演示
        # IdModel 本质上是为了 自动生成所有的model 和 transaction 表 的主键类型
        id = Column(  
            BigInteger,
            Sequence("audit_log_id_seq", start=1),
            primary_key=True,
            autoincrement=True,
        )
        # 可以添加自定义字段
        remote_addr = Column(String(50), comment="客户端IP")
        request_id = Column(String(64), comment="请求ID")
        operation_reason = Column(String(500), comment="操作原因")
    
    # 创建自定义 manager
    custom_manager = VersioningManager(transaction_cls=AuditLog)
    
    # 初始化版本化 建议使用 init_versioning() 而不是原生的 make_versioned()
    init_versioning(manager=custom_manager)
    
    # 定义带版本历史的模型
    class Document(CoreModel):
        """文档模型"""
        __tablename__ = "demo_document_v1"
        enable_history = True  # 启用版本历史
        
        id = Column(Integer, primary_key=True, autoincrement=True)
        title = Column(String(200))
        content = Column(Text)
        created_at = Column(DateTime, default=datetime.now)
    
    # 配置 mappers
    configure_mappers()
    
    # 初始化数据库
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, "demo_custom_transaction_v1.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    BaseModel.metadata.create_all(engine)
    
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # 测试
    try:
        # 创建文档
        doc = Document(title="测试文档", content="测试内容")
        session.add(doc)
        session.commit()
        print_success(f"创建文档: ID={doc.id}")
        
        # 更新文档
        doc.title = "更新后的标题"
        doc.content = "更新后的内容"
        session.commit()
        print_success("更新文档成功")
        
        # 查询审计日志表
        audit_logs = session.query(AuditLog).all()
        print_info(f"审计日志表 'audit_log' 中有 {len(audit_logs)} 条记录")
        for log in audit_logs:
            print(f"  - ID={log.id}, 时间={log.issued_at}")
        
        # 查询历史表
        from sqlalchemy_history import version_class
        DocumentVersion = version_class(Document)
        versions = session.query(DocumentVersion).all()
        print_info(f"文档历史表中有 {len(versions)} 条记录")
        
        print()
        print_success("场景1演示完成！")
        return True
        
    except Exception as e:
        print_error(f"场景1失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        session.close()
        print_info(f"数据库文件: {db_path}")


if __name__ == "__main__":
    main()
