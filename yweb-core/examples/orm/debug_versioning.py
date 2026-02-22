#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
调试版本化状态

本脚本用于测试 ORM 版本化功能，验证：
- 模型定义后 __versioned__ 属性
- configure_mappers 后的版本化状态
- 事务表和版本表的创建
- 历史记录的正确记录
"""

from yweb.orm import (
    CoreModel, BaseModel, init_database, configure_primary_key, 
    PrimaryKeyConfig, init_versioning, IdType
)
from sqlalchemy_history import versioning_manager
from sqlalchemy.orm import configure_mappers, Mapped, mapped_column
from sqlalchemy import String
from yweb.utils import TestCollector


def main():
    """主函数"""
    tc = TestCollector(title="版本化功能调试")
    
    try:
        # ============================================================
        # 1. 初始化配置
        # ============================================================
        tc.section("1. 初始化配置")
        
        # 重置
        PrimaryKeyConfig.reset()
        tc.check("PrimaryKeyConfig 重置成功", True)
        
        # 配置主键策略（在 init_versioning 之前）
        configure_primary_key(strategy=IdType.SHORT_UUID, short_uuid_length=10)
        tc.check("主键策略配置为 SHORT_UUID", PrimaryKeyConfig._strategy == IdType.SHORT_UUID)
        
        # 初始化版本化
        init_versioning()
        tc.check("版本化初始化完成", True)
        
        # ============================================================
        # 2. 定义模型
        # ============================================================
        tc.section("2. 定义模型")
        
        # 定义一个带历史记录的模型（在 init_versioning 之后）
        class TestHistoryModel(BaseModel):
            __tablename__ = 'test_history_model'
            __pk_strategy__ = IdType.SHORT_UUID
            enable_history = True
            content: Mapped[str] = mapped_column(String(200), nullable=True)
        
        tc.check("模型定义成功", TestHistoryModel is not None)
        tc.check("模型具有 __versioned__ 属性", hasattr(TestHistoryModel, '__versioned__'))
        
        pending_before = versioning_manager.pending_classes
        tc.check("pending_classes 已注册", len(pending_before) > 0, 
                 f"pending_classes: {pending_before}")
        
        # ============================================================
        # 3. 配置 Mappers
        # ============================================================
        tc.section("3. 配置 Mappers")
        
        # 配置 mappers（这会触发版本化模型的检测）
        configure_mappers()
        
        tc.check_not_none("declarative_base 已设置", versioning_manager.declarative_base)
        tc.check("transaction_cls 不是 Factory", 
                 versioning_manager.transaction_cls and 
                 hasattr(versioning_manager.transaction_cls, '__table__'))
        
        version_class_keys = [k.__name__ for k in versioning_manager.version_class_map.keys()]
        tc.check("version_class_map 包含模型", 'TestHistoryModel' in version_class_keys,
                 f"keys: {version_class_keys}")
        
        tc.check("pending_classes 已清空", len(versioning_manager.pending_classes) == 0)
        
        # ============================================================
        # 4. 检查事务表配置
        # ============================================================
        tc.section("4. 检查事务表配置")
        
        if versioning_manager.transaction_cls and hasattr(versioning_manager.transaction_cls, '__table__'):
            transaction_table = versioning_manager.transaction_cls.__table__
            tc.check_not_none("事务表存在", transaction_table)
            
            id_column_type = str(transaction_table.c.id.type)
            tc.check("事务表 id 列类型正确", id_column_type is not None,
                     f"类型: {id_column_type}")
        else:
            tc.check("transaction_cls 已初始化", False, 
                     f"仍然是 Factory: {versioning_manager.transaction_cls}")
        
        # ============================================================
        # 5. 创建数据库和表
        # ============================================================
        tc.section("5. 创建数据库和表")
        
        engine, session_scope = init_database('sqlite:///:memory:', echo=False)
        CoreModel.query = session_scope.query_property()
        
        tc.check_not_none("数据库引擎创建成功", engine)
        tc.check_not_none("session_scope 创建成功", session_scope)
        
        BaseModel.metadata.create_all(bind=engine)
        tc.check("主模型表创建成功", True)
        
        # 创建版本化表
        version_tables_created = []
        if versioning_manager.transaction_cls and hasattr(versioning_manager.transaction_cls, '__table__'):
            versioning_manager.transaction_cls.__table__.create(bind=engine, checkfirst=True)
            version_tables_created.append('transaction')
        
        for key, version_cls in versioning_manager.version_class_map.items():
            if version_cls and hasattr(version_cls, '__table__'):
                version_cls.__table__.create(bind=engine, checkfirst=True)
                version_tables_created.append(version_cls.__name__)
        
        tc.check("版本化表创建成功", len(version_tables_created) > 0,
                 f"已创建: {version_tables_created}")
        
        # ============================================================
        # 6. 测试创建记录
        # ============================================================
        tc.section("6. 测试创建记录")
        
        session = session_scope()
        model = TestHistoryModel(name='Test', content='test content')
        session.add(model)
        session.commit()
        
        tc.check_not_none("模型 ID 已生成", model.id)
        tc.check_equal("ID 类型为字符串", type(model.id).__name__, 'str')
        tc.check("ID 长度为 10", len(model.id) == 10, f"实际长度: {len(model.id)}")
        
        # ============================================================
        # 7. 验证历史记录
        # ============================================================
        tc.section("7. 验证历史记录")
        
        from yweb.orm import get_history_count
        count = get_history_count(TestHistoryModel, model.id, session=session)
        
        tc.check("历史记录数量 >= 1", count >= 1, f"实际数量: {count}")
        
    except Exception as e:
        tc.check(False, f"发生未预期的错误: {e}")
        import traceback
        traceback.print_exc()
    
    # 输出测试汇总
    return tc.summary()


if __name__ == "__main__":
    main()
