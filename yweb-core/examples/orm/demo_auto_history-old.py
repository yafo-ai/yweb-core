"""自动历史版本保留示例

本脚本演示了 yweb.orm 的自动版本历史功能，使用 sqlalchemy-history 实现。

================================================================================
                          版本历史功能概述
================================================================================

主要功能：
- 自动记录模型的所有变更历史
- 支持查询任意版本的数据
- 版本差异比较
- 恢复到指定版本

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

使用步骤：
1. 配置主键策略（可选，如需使用短UUID等非默认策略）
2. 调用 init_versioning() 初始化版本化功能
3. 定义模型，继承 BaseModel 或者 CoreModel，开启 enable_history=True

运行方式：
    python test_auto_history.py
"""

import os
from sqlalchemy import String
from sqlalchemy.orm import configure_mappers, Mapped, mapped_column

# ==================== 1. 初始化版本化功能 ====================

# 如果需要使用自定义主键策略（如短UUID），必须在 init_versioning() 之前配置
# 示例（取消注释以启用短UUID主键）：
# from yweb.orm import configure_primary_key
# configure_primary_key(strategy="short_uuid", short_uuid_length=10)

# 必须在定义任何 enable_history=True 的模型之前调用
from yweb.orm import init_versioning

try:
    init_versioning()
    print("[OK] 版本化功能初始化成功")
except Exception as e:
    print(f"[INFO] 版本化已初始化或出错: {e}")


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
    """文档模型 - 支持版本历史
    
    继承说明：
    - BaseModel: 提供基础字段（id, name, code, created_at, updated_at）和软删除
    - enable_history=True: 启用自动版本历史功能
    
    每次修改都会自动记录一个历史版本。
    """
    __tablename__ = "demo_documents"
    __table_args__ = {'extend_existing': True}
    
    enable_history=True

    # 自定义业务字段
    title: Mapped[str] = mapped_column(String(200), nullable=True)
    content: Mapped[str] = mapped_column(String(5000), nullable=True)
    author: Mapped[str] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")


class ArticleModel(BaseModel):
    """文章模型 - 支持版本历史
    
    演示多个模型都可以启用版本历史。
    """
    __tablename__ = "demo_articles"
    __table_args__ = {'extend_existing': True}
    
    enable_history=True
    
    headline: Mapped[str] = mapped_column(String(300), nullable=True)
    body: Mapped[str] = mapped_column(String(10000), nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=True)


# ==================== 辅助函数 ====================

def print_section(title):
    """打印章节标题"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def print_success(message):
    """打印成功消息"""
    print(f"[OK] {message}")


def print_error(message):
    """打印错误消息"""
    print(f"[ERROR] {message}")


def print_info(message):
    """打印信息"""
    print(f"[INFO] {message}")


def print_history_record(record: dict, index: int = None):
    """打印单条历史记录"""
    prefix = f"[版本 {index}]" if index is not None else "[记录]"
    transaction_id = record.get('transaction_id', 'N/A')
    operation = record.get('operation_type', 'N/A')
    
    # 过滤掉一些系统字段，只显示业务相关的
    exclude_keys = {'transaction_id', 'end_transaction_id', 'operation_type'}
    business_fields = {k: v for k, v in record.items() if k not in exclude_keys}
    
    print(f"  {prefix} transaction_id={transaction_id}, operation={operation}")
    for key, value in business_fields.items():
        if value is not None:
            print(f"       {key}: {value}")


# ==================== 测试场景 ====================

def test_scenario_1_create_and_update(session):
    """场景1：创建文档并多次更新，查看历史记录"""
    print_section("场景1：创建文档并多次更新，查看历史记录")
    
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

## 3. 基本使用
from yweb.orm import BaseModel, init_database

# 初始化数据库
engine, session = init_database("sqlite:///test.db")
""",
        author="张三",
        status="draft"
    )
    doc.add(True)
    doc_id = doc.id
    print_success(f"创建文档: ID={doc_id}, 标题={doc.title}, 状态={doc.status}")
    
    # 第一次更新
    print_info("第一次更新：修改内容和状态...")
    doc.content = """# yweb.orm 快速入门

## 1. 简介
yweb.orm 是一个基于 SQLAlchemy 的 ORM 扩展库，提供了更简洁的 API 和丰富的功能。
它支持软删除、版本历史、级联删除等高级特性。

## 2. 安装
pip install yweb-core

## 3. 基本使用
from yweb.orm import BaseModel, init_database

# 初始化数据库
engine, session = init_database("sqlite:///test.db")

## 4. 定义模型（新增章节）
class User(BaseModel):
    __tablename__ = "users"
    username = Column(String(50))
    email = Column(String(100))
"""
    doc.status = "review"
    doc.save(True)
    print_success(f"更新后: 状态={doc.status}")
    
    # 第二次更新
    print_info("第二次更新：修改标题和作者...")
    doc.title = "yweb.orm 完整使用指南 V2"
    doc.author = "张三、李四"
    doc.save(True)
    print_success(f"更新后: 标题={doc.title}")
    
    # 第三次更新
    print_info("第三次更新：发布文档...")
    doc.status = "published"
    doc.content = """# yweb.orm 完整使用指南（正式版）

## 1. 简介
yweb.orm 是一个基于 SQLAlchemy 的 ORM 扩展库，提供了更简洁的 API 和丰富的功能。
它支持软删除、版本历史、级联删除等高级特性。本文档已通过技术评审。

## 2. 安装
pip install yweb-core

## 3. 基本使用
from yweb.orm import BaseModel, init_database

# 初始化数据库
engine, session = init_database("sqlite:///test.db")

## 4. 定义模型
class User(BaseModel):
    __tablename__ = "users"
    username = Column(String(50))
    email = Column(String(100))

## 5. CRUD 操作（新增章节）
# 创建
user = User(username="test", email="test@example.com")
user.add(True)

# 更新
user.username = "new_name"
user.save(True)

# 删除（软删除）
user.delete(True)
"""
    doc.save(True)
    print_success(f"更新后: 状态={doc.status}")
    
    # 获取历史记录数量
    count = get_history_count(DocumentModel, doc_id, session=session)
    print_info(f"历史记录总数: {count}")
    
    # 获取所有历史记录
    print_info("查询所有历史记录:")
    history = get_history(DocumentModel, doc_id, session=session)
    
    if history:
        for i, record in enumerate(history, 1):
            print_history_record(record, i)
    else:
        print_error("未找到历史记录")
    
    return doc_id


def test_scenario_2_history_diff(session, doc_id):
    """场景2：比较版本差异"""
    print_section("场景2：比较版本差异")
    
    # 获取历史记录，找到两个版本的 transaction_id
    history = get_history(DocumentModel, doc_id, session=session)
    
    if not history or len(history) < 2:
        print_error("历史记录不足，无法比较差异")
        return
    
    # 获取最早和最新的版本
    latest = history[0]  # 最新版本在前面（降序）
    oldest = history[-1]  # 最早版本在后面
    
    latest_version = latest.get('transaction_id')
    oldest_version = oldest.get('transaction_id')
    
    print_info(f"比较版本: {oldest_version} -> {latest_version}")
    
    # 获取差异
    diff = get_history_diff(
        DocumentModel, doc_id,
        from_version=oldest_version,
        to_version=latest_version,
        session=session
    )
    
    if diff:
        print_success("版本差异:")
        for field, change in diff.items():
            from_val = change.get('from', 'N/A')
            to_val = change.get('to', 'N/A')
            
            # 截断过长的内容
            if isinstance(from_val, str) and len(from_val) > 50:
                from_val = from_val[:50] + "..."
            if isinstance(to_val, str) and len(to_val) > 50:
                to_val = to_val[:50] + "..."
            
            print(f"  {field}:")
            print(f"    旧值: {from_val}")
            print(f"    新值: {to_val}")
    else:
        print_info("两个版本没有差异")


def test_scenario_3_restore_version(session, doc_id):
    """场景3：恢复到指定版本"""
    print_section("场景3：恢复到指定版本")
    
    # 查询当前状态
    doc = DocumentModel.query.filter_by(id=doc_id).first()
    print_info(f"当前状态: 标题={doc.title}, 状态={doc.status}")
    
    # 获取历史记录
    history = get_history(DocumentModel, doc_id, session=session)
    
    if not history or len(history) < 2:
        print_error("历史记录不足，无法演示恢复功能")
        return
    
    # 选择一个早期版本（倒数第二新的）
    target_version = history[-1].get('transaction_id')
    target_status = history[-1].get('status')
    target_title = history[-1].get('title')
    
    print_info(f"准备恢复到版本 {target_version}:")
    print(f"  目标标题: {target_title}")
    print(f"  目标状态: {target_status}")
    
    # 执行恢复
    restored = restore_to_version(
        DocumentModel, doc_id,
        version=target_version,
        session=session
    )
    
    if restored:
        session.commit()
        print_success(f"恢复成功!")
        print(f"  恢复后标题: {restored.title}")
        print(f"  恢复后状态: {restored.status}")
        
        # 恢复操作本身也会产生一条新的历史记录
        new_count = get_history_count(DocumentModel, doc_id, session=session)
        print_info(f"恢复后历史记录总数: {new_count}")
    else:
        print_error("恢复失败")


def test_scenario_4_get_version_class(session):
    """场景4：获取历史模型类（高级用法）"""
    print_section("场景4：获取历史模型类（高级用法）")
    
    # 获取历史模型类
    DocumentHistory = get_version_class(DocumentModel)
    
    print_info(f"原始模型: {DocumentModel.__name__}")
    print_info(f"历史模型: {DocumentHistory.__name__}")
    print_info(f"历史表名: {DocumentHistory.__table__.name}")
    
    # 列出历史模型的列
    print_info("历史模型的列:")
    for col in DocumentHistory.__table__.columns:
        print(f"  - {col.name}: {col.type}")
    
    # 直接查询历史表
    all_history = session.query(DocumentHistory).all()
    print_success(f"历史表总记录数: {len(all_history)}")


def test_scenario_5_multiple_models(session):
    """场景5：多个模型的版本历史"""
    print_section("场景5：多个模型的版本历史")
    
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
    print_success(f"创建文章: ID={article_id}, 标题={article.headline}")
    
    # 更新文章
    article.headline = "重大消息：yweb.orm 发布 2.0 版本"
    article.body = "更新后的内容..."
    article.save(True)
    print_success("更新文章完成")
    
    # 获取文章历史
    article_count = get_history_count(ArticleModel, article_id, session=session)
    print_info(f"文章历史记录数: {article_count}")
    
    # 获取文档历史
    doc_count = session.query(get_version_class(DocumentModel)).count()
    print_info(f"文档历史记录总数: {doc_count}")
    
    print_success("多个模型都正确记录了版本历史")


def test_scenario_6_soft_delete_with_history(session):
    """场景6：软删除后历史记录仍然保留"""
    print_section("场景6：软删除后历史记录仍然保留")
    
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
    print_success(f"创建文档: ID={doc_id}")
    
    # 多次更新
    for i in range(3):
        doc.content = f"内容版本 {i + 2}"
        doc.save(True)
    print_success(f"更新了 3 次")
    
    # 获取删除前的历史记录数量
    count_before = get_history_count(DocumentModel, doc_id, session=session)
    print_info(f"软删除前历史记录数: {count_before}")
    
    # 软删除文档
    doc.delete(True)
    print_info("已软删除文档")
    
    # 验证软删除后历史记录仍然存在
    count_after = get_history_count(DocumentModel, doc_id, session=session)
    print_info(f"软删除后历史记录数: {count_after}")
    
    if count_after >= count_before:
        print_success("软删除不会删除历史记录，数据完整保留！")
    else:
        print_error("历史记录丢失！")
    
    # 验证可以查询到已删除记录的历史
    history = get_history(DocumentModel, doc_id, session=session)
    if history:
        print_success(f"可以查询到已删除记录的 {len(history)} 条历史记录")
    else:
        print_error("无法查询历史记录")


def test_scenario_7_instance_methods(session):
    """场景7：实例方法调用方式（推荐）
    
    展示更优雅的实例方法调用方式，无需传入 model_class 和 session。
    """
    print_section("场景7：实例方法调用方式（推荐）")
    
    print_info("本场景展示新的实例方法调用方式，对比传统函数调用方式")
    print()
    
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
    print_success(f"创建文档: ID={doc_id}")
    
    # 多次更新以生成历史
    doc.title = "修改后的标题"
    doc.content = "这是修改后的内容。\n删除了一行。\n新增了这一行。"
    doc.save(True)
    
    doc.status = "published"
    doc.save(True)
    
    print_success("完成多次更新")
    print()
    
    # ========== 方式对比 ==========
    
    print_info("【调用方式对比】")
    print()
    
    # --- 获取历史记录 ---
    print("1. 获取历史记录:")
    print("   传统方式: history = get_history(DocumentModel, doc_id, session=session)")
    print("   实例方式: history = doc.get_history()")
    print("   便捷属性: history = doc.history")
    
    # 实际调用
    history = doc.get_history()
    print_success(f"   结果: 获取到 {len(history)} 条历史记录")
    print()
    
    # --- 历史数量 ---
    print("2. 获取历史数量:")
    print("   传统方式: count = get_history_count(DocumentModel, doc_id, session=session)")
    print("   实例方式: count = doc.history_count")
    
    count = doc.history_count
    print_success(f"   结果: {count} 条历史记录")
    print()
    
    # --- 版本差异 ---
    if len(history) >= 2:
        latest_ver = history[0].get('transaction_id')
        oldest_ver = history[-1].get('transaction_id')
        
        print("3. 比较版本差异:")
        print(f"   传统方式: diff = get_history_diff(DocumentModel, doc_id, {oldest_ver}, {latest_ver}, session=session)")
        print(f"   实例方式: diff = doc.get_history_diff({oldest_ver}, {latest_ver})")
        
        diff = doc.get_history_diff(oldest_ver, latest_ver)
        if diff:
            print_success(f"   结果: 发现 {len(diff)} 个字段有变化")
            for field in list(diff.keys())[:3]:  # 只显示前3个
                print(f"     - {field}")
        print()
        
        # --- 文本差异 ---
        print("4. 获取字段文本差异（unified diff）:")
        print(f"   传统方式: detail = get_field_text_diff(DocumentModel, doc_id, 'content', {oldest_ver}, {latest_ver}, session=session)")
        print(f"   实例方式: detail = doc.get_field_text_diff('content', {oldest_ver}, {latest_ver})")
        
        detail = doc.get_field_text_diff('content', oldest_ver, latest_ver)
        if detail:
            stats = detail.get('stats', {})
            print_success(f"   结果: +{stats.get('added', 0)} 行, -{stats.get('removed', 0)} 行, ~{stats.get('changed', 0)} 行修改")
        print()
        
        # --- 恢复版本 ---
        print("5. 恢复到指定版本:")
        print(f"   传统方式: restored = restore_to_version(DocumentModel, doc_id, {oldest_ver}, session=session)")
        print(f"   实例方式: doc.restore_to_version({oldest_ver})")
        
        original_title = doc.title
        doc.restore_to_version(oldest_ver)
        session.commit()
        print_success(f"   结果: 标题从 '{original_title}' 恢复为 '{doc.title}'")
        print()
    
    # --- 类方法（不需要实例）---
    print("6. 类方法（不需要先获取实例）:")
    print("   传统方式: history = get_history(DocumentModel, doc_id, session=session)")
    print("   类方法:   history = DocumentModel.get_history_by_id(doc_id)")
    
    history_by_class = DocumentModel.get_history_by_id(doc_id)
    print_success(f"   结果: 获取到 {len(history_by_class)} 条历史记录")
    print()
    
    print_success("实例方法调用方式演示完成！")
    print_info("推荐使用实例方法，代码更简洁、更符合 ORM 风格")


# ==================== 主函数 ====================

def main():
    """主函数"""
    print("\n" + "="*70)
    print("  自动历史版本保留功能演示")
    print("="*70)
    
    # 检查版本化状态
    if is_versioning_initialized():
        print_success("版本化功能已启用")
    else:
        print_error("版本化功能未初始化！请确保在定义模型之前调用 init_versioning()")
        return
    
    # 初始化数据库
    print_info("初始化数据库...")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, "demo_auto_history——old.db")
    engine, session_scope = init_database(f"sqlite:///{db_path}", echo=False)
    
    CoreModel.query = session_scope.query_property()
    
    # 配置 mappers（必须在创建表之前）
    print_info("配置版本映射...")
    try:
        configure_mappers()
        print_success("版本映射配置完成")
    except Exception as e:
        print_info(f"mappers 已配置: {e}")
    

    
    # 清空并重建数据表
    print_info("清空并重建数据表...")
    BaseModel.metadata.drop_all(engine)
    BaseModel.metadata.create_all(engine)
    

    
    print_success("数据库初始化完成")
    
    # 获取 session
    session = session_scope()
    
    # 运行所有测试场景
    try:
        doc_id = test_scenario_1_create_and_update(session)
        test_scenario_2_history_diff(session, doc_id)
        test_scenario_3_restore_version(session, doc_id)
        test_scenario_4_get_version_class(session)
        test_scenario_5_multiple_models(session)
        test_scenario_6_soft_delete_with_history(session)
        test_scenario_7_instance_methods(session)
        
        print_section("所有测试场景执行完成")
        print_success("自动历史版本功能演示成功！")
        
    except Exception as e:
        print_error(f"测试过程中发生错误: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        session_scope.remove()
        print()  # 空行
        print_info(f"数据库文件保存在: {db_path}")


if __name__ == "__main__":
    main()
