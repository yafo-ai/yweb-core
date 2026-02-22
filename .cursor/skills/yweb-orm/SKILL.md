---
name: yweb-orm
description: YWeb ORM 使用规范。在编写数据库模型定义、CRUD 操作、查询过滤、分页、软删除、事务管理、批量操作、关系定义等数据层代码时使用。基于 SQLAlchemy 的 Active Record 模式。
---

# YWeb ORM 使用规范

## 核心要点

YWeb ORM 基于 **SQLAlchemy**，采用 **Active Record 模式**：

- 模型继承 `BaseModel`（自动获得 id/name/code/时间戳/软删除等字段）
- 或继承 `CoreModel`（仅 id + 时间戳，更轻量）
- 使用 `init_database()` 一行初始化
- 通过 `Model.query` 进行链式查询

## 关键编码规范

1. **所有字段必须有 `comment`**：`mapped_column(String(255), comment="字段说明")`
2. **使用 SQLAlchemy 2.0 风格**：`Mapped[str]` 类型注解 + `mapped_column()`
3. **表名自动生成**：类名驼峰转下划线，也可手动指定 `__tablename__`
4. **软删除**：`BaseModel` 自带软删除支持，查询自动过滤已删除记录
5. **事务管理**：Service 层使用 `@transactional` 装饰器管理事务边界
6. **ORM 事务外行为**：注意理解提交抑制机制，避免意外的自动提交

## ORM 功能文档索引

编码时根据需要阅读对应文档：

### 基础指南

| 文档路径 | 说明 |
|---------|------|
| `yweb-core/docs/03_orm_guide.md` | ORM 基础指南（初始化、模型定义、CRUD、分页、软删除） |
| `yweb-core/docs/orm_docs/README.md` | ORM 完整功能文档索引 |

### 核心功能

| 文档路径 | 说明 |
|---------|------|
| `yweb-core/docs/orm_docs/01_overview.md` | 概述与架构设计 |
| `yweb-core/docs/orm_docs/02_model_definition.md` | 模型定义（BaseModel、CoreModel、字段） |
| `yweb-core/docs/orm_docs/03_crud_operations.md` | CRUD 操作（save/add/update/delete） |
| `yweb-core/docs/orm_docs/03_relationships.md` | 关系定义（一对一/一对多/多对多/自关联） |
| `yweb-core/docs/orm_docs/04_query_and_filter.md` | 查询与过滤（Query 对象、链式调用） |
| `yweb-core/docs/orm_docs/05_pagination.md` | 分页查询（Page 对象） |
| `yweb-core/docs/orm_docs/06_bulk_operations.md` | 批量操作 |

### 高级功能

| 文档路径 | 说明 |
|---------|------|
| `yweb-core/docs/orm_docs/07_soft_delete.md` | 软删除机制 |
| `yweb-core/docs/orm_docs/08_cascade_soft_delete.md` | 级联软删除 |
| `yweb-core/docs/orm_docs/09_version_control.md` | 乐观锁与版本控制 |
| `yweb-core/docs/orm_docs/10_history.md` | 历史记录 |
| `yweb-core/docs/orm_docs/11_transaction.md` | 事务管理 |
| `yweb-core/docs/orm_docs/12_db_session.md` | 数据库会话管理 |
| `yweb-core/docs/orm_docs/16_transaction_manager.md` | 高级事务管理器（嵌套事务、Savepoints） |

### 辅助功能

| 文档路径 | 说明 |
|---------|------|
| `yweb-core/docs/orm_docs/13_serialization.md` | 数据序列化（to_dict） |
| `yweb-core/docs/orm_docs/14_schema_validation.md` | Schema 与验证 |
| `yweb-core/docs/orm_docs/15_fastapi_integration.md` | FastAPI 集成 |

### 高级混入（Mixin）

| 文档路径 | 说明 |
|---------|------|
| `yweb-core/docs/orm_docs/17-tree-structure-guide.md` | 树形结构混入 |
| `yweb-core/docs/orm_docs/18-sortable-mixin-guide.md` | 排序混入 |
| `yweb-core/docs/orm_docs/19-state-machine-guide.md` | 状态机混入 |
| `yweb-core/docs/orm_docs/20-taggable-mixin-guide.md` | 标签混入 |

### 事务行为专题

| 文档路径 | 说明 |
|---------|------|
| `yweb-core/docs/orm_commit_behavior_outside_transaction.md` | 事务外提交行为 |
| `yweb-core/docs/orm_commit_suppression_mechanism.md` | 提交抑制机制 |

## 工作流程

1. 定义新模型前，阅读 `02_model_definition.md`
2. 编写 CRUD 操作前，阅读 `03_crud_operations.md`
3. 涉及事务管理时，阅读 `11_transaction.md` 和 `16_transaction_manager.md`
4. 使用高级混入（树形/排序/状态机/标签）前，阅读对应文档
5. 不确定时，先从 `03_orm_guide.md` 基础指南开始
