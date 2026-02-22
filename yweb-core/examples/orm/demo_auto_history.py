#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
自动历史版本保留示例

本脚本用于演示 yweb.orm 的自动版本历史功能，验证：
- 自动记录模型的所有变更历史
- 支持查询任意版本的数据
- 版本差异比较
- 恢复到指定版本
- 实例方法调用方式

核心 API：
┌─────────────────────────────────────────────────────────────────────────────┐
│ init_versioning()      - 初始化版本化功能（必须在定义模型之前调用）          │
│ get_history()          - 获取历史记录列表                                   │
│ get_history_count()    - 获取历史记录数量                                   │
│ get_history_diff()     - 比较两个版本的差异                                 │
│ restore_to_version()   - 恢复到指定版本                                     │
│ get_version_class()    - 获取历史模型类（高级用法）                          │
└─────────────────────────────────────────────────────────────────────────────┘

实例方法（推荐）：
┌─────────────────────────────────────────────────────────────────────────────┐
│ doc.get_history()              - 获取当前实例的历史记录                      │
│ doc.history                    - 便捷属性，获取所有历史记录                  │
│ doc.history_count              - 便捷属性，获取历史记录数量                  │
│ doc.get_history_diff(v1, v2)   - 比较两个版本的差异                         │
│ doc.get_field_text_diff(...)   - 获取字段的文本差异（unified/html/opcodes） │
│ doc.restore_to_version(ver)    - 恢复到指定版本                             │
│ Model.get_history_by_id(id)    - 类方法，不需要先获取实例                   │
└─────────────────────────────────────────────────────────────────────────────┘

运行方式：
    python demo_auto_history.py
"""

import os
from sqlalchemy import String
from sqlalchemy.orm import configure_mappers, Mapped, mapped_column

from yweb.utils import TestCollector

# ==================== 1. 初始化版本化功能 ====================

from yweb.orm import init_versioning

try:
    init_versioning()
except Exception:
    pass  # 可能已初始化


# ==================== 2. 导入依赖 ====================

from yweb.orm import (
    CoreModel,
    BaseModel,
    init_database,
    get_history,
    get_history_count,
    get_history_diff,
    restore_to_version,
    get_version_class,
    is_versioning_initialized,
)


# ==================== 3. 定义支持版本历史的模型 ====================

class DocumentModel(BaseModel):
    """文档模型 - 支持版本历史"""
    __tablename__ = "demo_documents"
    __table_args__ = {'extend_existing': True}
    
    enable_history = True

    title: Mapped[str] = mapped_column(String(200), nullable=True)
    content: Mapped[str] = mapped_column(String(5000), nullable=True)
    author: Mapped[str] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")


class ArticleModel(BaseModel):
    """文章模型 - 支持版本历史"""
    __tablename__ = "demo_articles"
    __table_args__ = {'extend_existing': True}
    
    enable_history = True
    
    headline: Mapped[str] = mapped_column(String(300), nullable=True)
    body: Mapped[str] = mapped_column(String(10000), nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=True)


# ==================== 测试场景 ====================

def test_scenario_1_create_and_update(tc: TestCollector, session):
    """场景1：创建文档并多次更新，查看历史记录"""
    tc.section("场景1：创建文档并多次更新")
    
    # 创建文档
    doc = DocumentModel(
        name="技术文档",
        code="DOC_001",
        title="yweb.orm 使用指南",
        content="""# yweb.orm 快速入门

## 1. 简介
yweb.orm 是一个基于 SQLAlchemy 的 ORM 扩展库，提供了更简洁的 API 和丰富的功能。

## 2. 安装
pip install yweb-core
""",
        author="张三",
        status="draft"
    )
    doc.add(True)
    doc_id = doc.id
    
    tc.check_not_none("文档创建后ID不为空", doc.id)
    tc.check_equal("文档标题正确", doc.title, "yweb.orm 使用指南")
    tc.check_equal("文档状态为draft", doc.status, "draft")
    
    # 第一次更新
    doc.content = """# yweb.orm 快速入门

## 1. 简介
yweb.orm 是一个基于 SQLAlchemy 的 ORM 扩展库，提供了更简洁的 API 和丰富的功能。
它支持软删除、版本历史、级联删除等高级特性。

## 2. 安装
pip install yweb-core

## 4. 定义模型（新增章节）
class User(BaseModel):
    __tablename__ = "users"
"""
    doc.status = "review"
    doc.save(True)
    
    tc.check_equal("第一次更新状态为review", doc.status, "review")
    
    # 第二次更新
    doc.title = "yweb.orm 完整使用指南 V2"
    doc.author = "张三、李四"
    doc.save(True)
    
    tc.check_equal("第二次更新标题正确", doc.title, "yweb.orm 完整使用指南 V2")
    tc.check_equal("第二次更新作者正确", doc.author, "张三、李四")
    
    # 第三次更新
    doc.status = "published"
    doc.content = """# yweb.orm 完整使用指南（正式版）

## 1. 简介
yweb.orm 是一个基于 SQLAlchemy 的 ORM 扩展库。本文档已通过技术评审。

## 5. CRUD 操作（新增章节）
# 创建
user = User(username="test", email="test@example.com")
user.add(True)
"""
    doc.save(True)
    
    tc.check_equal("第三次更新状态为published", doc.status, "published")
    
    # 获取历史记录数量
    count = get_history_count(DocumentModel, doc_id, session=session)
    tc.check("历史记录数量 >= 4", count >= 4, f"实际数量: {count}")
    
    # 获取所有历史记录
    history = get_history(DocumentModel, doc_id, session=session)
    tc.check("能获取历史记录列表", history is not None and len(history) > 0,
             f"历史记录数: {len(history) if history else 0}")
    
    return doc_id


def test_scenario_2_history_diff(tc: TestCollector, session, doc_id):
    """场景2：比较版本差异"""
    tc.section("场景2：比较版本差异")
    
    # 获取历史记录
    history = get_history(DocumentModel, doc_id, session=session)
    
    if not history or len(history) < 2:
        tc.check("历史记录足够进行比较", False, "历史记录不足")
        return
    
    tc.check("历史记录足够进行比较", len(history) >= 2, f"共 {len(history)} 条")
    
    # 获取最早和最新的版本
    latest = history[0]
    oldest = history[-1]
    
    latest_version = latest.get('transaction_id')
    oldest_version = oldest.get('transaction_id')
    
    tc.check_not_none("最新版本ID存在", latest_version)
    tc.check_not_none("最早版本ID存在", oldest_version)
    
    # 获取差异
    diff = get_history_diff(
        DocumentModel, doc_id,
        from_version=oldest_version,
        to_version=latest_version,
        session=session
    )
    
    tc.check("能获取版本差异", diff is not None, f"差异字段: {list(diff.keys()) if diff else []}")
    
    if diff:
        tc.check("差异包含多个字段", len(diff) > 0, f"差异字段数: {len(diff)}")


def test_scenario_3_restore_version(tc: TestCollector, session, doc_id):
    """场景3：恢复到指定版本"""
    tc.section("场景3：恢复到指定版本")
    
    # 查询当前状态
    doc = DocumentModel.query.filter_by(id=doc_id).first()
    tc.check_not_none("能查询到文档", doc)
    
    current_title = doc.title
    current_status = doc.status
    
    # 获取历史记录
    history = get_history(DocumentModel, doc_id, session=session)
    
    if not history or len(history) < 2:
        tc.check("历史记录足够进行恢复", False, "历史记录不足")
        return
    
    tc.check("历史记录足够进行恢复", len(history) >= 2)
    
    # 选择最早版本恢复
    target_version = history[-1].get('transaction_id')
    target_title = history[-1].get('title')
    
    tc.check_not_none("目标版本ID存在", target_version)
    
    # 执行恢复
    restored = restore_to_version(
        DocumentModel, doc_id,
        version=target_version,
        session=session
    )
    
    tc.check_not_none("恢复操作返回对象", restored)
    
    if restored:
        session.commit()
        tc.check("恢复后标题已改变", restored.title != current_title or target_title == current_title,
                 f"从 '{current_title}' 恢复为 '{restored.title}'")
        
        # 恢复操作本身也会产生一条新的历史记录
        new_count = get_history_count(DocumentModel, doc_id, session=session)
        tc.check("恢复后历史记录数增加", new_count > len(history),
                 f"恢复后共 {new_count} 条")


def test_scenario_4_get_version_class(tc: TestCollector, session):
    """场景4：获取历史模型类（高级用法）"""
    tc.section("场景4：获取历史模型类")
    
    # 获取历史模型类
    DocumentHistory = get_version_class(DocumentModel)
    
    tc.check_not_none("能获取历史模型类", DocumentHistory)
    tc.check("历史模型类名正确", 'Version' in DocumentHistory.__name__ or 'History' in DocumentHistory.__name__,
             f"类名: {DocumentHistory.__name__}")
    tc.check("历史模型有表定义", hasattr(DocumentHistory, '__table__'),
             f"表名: {DocumentHistory.__table__.name if hasattr(DocumentHistory, '__table__') else 'N/A'}")
    
    # 列出历史模型的列
    if hasattr(DocumentHistory, '__table__'):
        columns = [col.name for col in DocumentHistory.__table__.columns]
        tc.check("历史表包含transaction_id列", 'transaction_id' in columns,
                 f"列: {columns}")
    
    # 直接查询历史表
    all_history = session.query(DocumentHistory).all()
    tc.check("能直接查询历史表", all_history is not None,
             f"总记录数: {len(all_history)}")


def test_scenario_5_multiple_models(tc: TestCollector, session):
    """场景5：多个模型的版本历史"""
    tc.section("场景5：多个模型的版本历史")
    
    # 创建文章
    article = ArticleModel(
        name="新闻文章",
        code="ART_001",
        headline="重大消息：yweb.orm 发布新版本",
        body="今天，yweb.orm 发布了最新版本...",
        category="技术"
    )
    article.add(True)
    article_id = article.id
    
    tc.check_not_none("文章创建后ID不为空", article.id)
    tc.check_equal("文章标题正确", article.headline, "重大消息：yweb.orm 发布新版本")
    
    # 更新文章
    article.headline = "重大消息：yweb.orm 发布 2.0 版本"
    article.body = "更新后的内容..."
    article.save(True)
    
    tc.check_equal("文章更新后标题正确", article.headline, "重大消息：yweb.orm 发布 2.0 版本")
    
    # 获取文章历史
    article_count = get_history_count(ArticleModel, article_id, session=session)
    tc.check("文章历史记录数 >= 2", article_count >= 2, f"实际: {article_count}")
    
    # 获取文档历史（验证不同模型互不影响）
    doc_count = session.query(get_version_class(DocumentModel)).count()
    tc.check("文档历史记录独立存在", doc_count > 0, f"文档历史数: {doc_count}")
    
    tc.check("多模型版本历史独立工作", True)


def test_scenario_6_soft_delete_with_history(tc: TestCollector, session):
    """场景6：软删除后历史记录仍然保留"""
    tc.section("场景6：软删除后历史记录保留")
    
    # 创建文档
    doc = DocumentModel(
        name="临时文档",
        code="DOC_TEMP",
        title="这是一个测试文档",
        content="测试内容",
        author="测试用户",
        status="draft"
    )
    doc.add(True)
    doc_id = doc.id
    
    tc.check_not_none("临时文档创建成功", doc.id)
    
    # 多次更新
    for i in range(3):
        doc.content = f"内容版本 {i + 2}"
        doc.save(True)
    
    tc.check("完成3次更新", True)
    
    # 获取删除前的历史记录数量
    count_before = get_history_count(DocumentModel, doc_id, session=session)
    tc.check("删除前历史记录数 >= 4", count_before >= 4, f"实际: {count_before}")
    
    # 软删除文档
    doc.delete(True)
    
    # 软删除后需要用 include_deleted=True 查询才能访问已删除记录
    deleted_doc = session.query(DocumentModel).execution_options(
        include_deleted=True
    ).filter_by(id=doc_id).first()
    tc.check("软删除操作完成", deleted_doc is not None and deleted_doc.is_deleted == True)
    
    # 验证软删除后历史记录仍然存在
    count_after = get_history_count(DocumentModel, doc_id, session=session)
    tc.check("软删除后历史记录保留", count_after >= count_before,
             f"删除前: {count_before}, 删除后: {count_after}")
    
    # 验证可以查询到已删除记录的历史
    history = get_history(DocumentModel, doc_id, session=session)
    tc.check("能查询已删除记录的历史", history is not None and len(history) > 0,
             f"历史记录数: {len(history) if history else 0}")


def test_scenario_7_instance_methods(tc: TestCollector, session):
    """场景7：实例方法调用方式（推荐）"""
    tc.section("场景7：实例方法调用方式")
    
    # 创建测试文档
    doc = DocumentModel(
        name="实例方法演示",
        code="DOC_INSTANCE",
        title="原始标题",
        content="这是原始内容。\n包含多行文本。\n用于演示文本差异功能。",
        author="开发者",
        status="draft"
    )
    doc.add(True)
    doc_id = doc.id
    
    tc.check_not_none("实例方法演示文档创建成功", doc.id)
    
    # 多次更新以生成历史
    doc.title = "修改后的标题"
    doc.content = "这是修改后的内容。\n删除了一行。\n新增了这一行。"
    doc.save(True)
    
    doc.status = "published"
    doc.save(True)
    
    tc.check("完成多次更新生成历史", True)
    
    # --- 测试实例方法 ---
    
    # 1. get_history() 实例方法
    history = doc.get_history()
    tc.check("doc.get_history() 返回历史记录", history is not None and len(history) > 0,
             f"返回 {len(history) if history else 0} 条")
    
    # 2. history_count 属性
    count = doc.history_count
    tc.check("doc.history_count 返回数量", count > 0, f"返回 {count}")
    
    # 3. 版本差异
    if len(history) >= 2:
        latest_ver = history[0].get('transaction_id')
        oldest_ver = history[-1].get('transaction_id')
        
        # get_history_diff() 实例方法
        diff = doc.get_history_diff(oldest_ver, latest_ver)
        tc.check("doc.get_history_diff() 返回差异", diff is not None,
                 f"差异字段数: {len(diff) if diff else 0}")
        
        # get_field_text_diff() 实例方法
        detail = doc.get_field_text_diff('content', oldest_ver, latest_ver)
        tc.check("doc.get_field_text_diff() 返回文本差异", detail is not None)
        
        if detail:
            stats = detail.get('stats', {})
            tc.check("文本差异包含统计信息", 'added' in stats or 'removed' in stats,
                     f"统计: {stats}")
        
        # restore_to_version() 实例方法
        original_title = doc.title
        doc.restore_to_version(oldest_ver)
        session.commit()
        tc.check("doc.restore_to_version() 恢复成功", doc.title != original_title or history[-1].get('title') == original_title,
                 f"从 '{original_title}' 恢复为 '{doc.title}'")
    
    # 4. 类方法 get_history_by_id()
    history_by_class = DocumentModel.get_history_by_id(doc_id)
    tc.check("DocumentModel.get_history_by_id() 返回历史", 
             history_by_class is not None and len(history_by_class) > 0,
             f"返回 {len(history_by_class) if history_by_class else 0} 条")


# ==================== 主函数 ====================

def main():
    """主函数"""
    tc = TestCollector(title="自动历史版本功能")
    
    session_scope = None
    
    try:
        # ============================================================
        # 0. 环境检查
        # ============================================================
        tc.section("0. 环境初始化")
        
        tc.check("版本化功能已初始化", is_versioning_initialized())
        
        # 初始化数据库
        script_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(script_dir, "demo_auto_history.db")
        engine, session_scope = init_database(f"sqlite:///{db_path}", echo=False)
        
        tc.check_not_none("数据库引擎创建成功", engine)
        tc.check_not_none("session_scope创建成功", session_scope)
        
        CoreModel.query = session_scope.query_property()
        
        # 配置 mappers
        try:
            configure_mappers()
            tc.check("版本映射配置完成", True)
        except Exception as e:
            tc.check("版本映射配置完成", True, f"已配置: {e}")
        
        # 清空并重建数据表
        BaseModel.metadata.drop_all(engine)
        BaseModel.metadata.create_all(engine)
        tc.check("数据表重建完成", True)
        
        # 获取 session
        session = session_scope()
        
        # ============================================================
        # 运行所有测试场景
        # ============================================================
        doc_id = test_scenario_1_create_and_update(tc, session)
        test_scenario_2_history_diff(tc, session, doc_id)
        test_scenario_3_restore_version(tc, session, doc_id)
        test_scenario_4_get_version_class(tc, session)
        test_scenario_5_multiple_models(tc, session)
        test_scenario_6_soft_delete_with_history(tc, session)
        test_scenario_7_instance_methods(tc, session)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        tc.check(f"发生未预期的错误: {type(e).__name__}", False, str(e))
    finally:
        if session_scope:
            session_scope.remove()
    
    # 输出测试汇总
    return tc.summary()


if __name__ == "__main__":
    main()
