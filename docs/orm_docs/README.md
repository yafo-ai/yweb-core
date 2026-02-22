# YWeb ORM 功能文档

本文档详细介绍 YWeb ORM 模块的所有功能，帮助开发者快速上手和深入理解。

## 文档目录

### 核心功能

| 文档 | 说明 |
|------|------|
| [01_概述与快速开始](01_overview.md) | ORM模块概述、架构设计、快速开始指南 |
| [02_模型定义](02_model_definition.md) | BaseModel、CoreModel、字段定义、表名生成 |
| [03_关系定义](03_relationships.md) | 一对一、一对多、多对多、自关联、fields.* API |
| [03_CRUD操作](03_crud_operations.md) | 增删改查基础操作、save/add/update/delete方法 |
| [04_查询与过滤](04_query_and_filter.md) | Query对象、条件查询、链式调用 |
| [05_分页查询](05_pagination.md) | 分页功能、Page对象、性能优化 |
| [06_批量操作](06_bulk_operations.md) | 批量更新、批量删除、批量软删除 |

### 高级功能

| 文档 | 说明 |
|------|------|
| [07_软删除](07_soft_delete.md) | 软删除机制、自动过滤、恢复功能 |
| [08_级联软删除](08_cascade_soft_delete.md) | 级联删除类型、fields.* API、配置方法 |
| [09_版本控制](09_version_control.md) | 乐观锁、ver字段、并发控制 |
| [10_历史记录](10_history.md) | sqlalchemy-history集成、版本历史、恢复功能 |
| [11_事务管理](11_transaction.md) | 事务控制、提交与回滚、Service层模式 |
| [12_数据库会话](12_db_session.md) | init_database、get_db、会话管理 |

### 辅助功能

| 文档 | 说明 |
|------|------|
| [13_数据序列化](13_serialization.md) | to_dict、to_dict_with_relations、DTO |
| [14_Schema与验证](14_schema_validation.md) | BaseSchemas、PaginationField、Pydantic集成 |
| [15_FastAPI集成](15_fastapi_integration.md) | 依赖注入、路由示例、最佳实践 |

### 高级事务管理

| 文档 | 说明 |
|------|------|
| [16_事务管理器](16_transaction_manager.md) | 嵌套事务、Savepoints、事务钩子、分布式事务接口 |

## 功能清单

### 核心模块

```
yweb/orm/
├── core_model.py           # 核心ORM模型类（CRUD、分页等）
├── base_model.py           # 业务模型基类（继承CoreModel）
├── db_session.py           # 数据库会话管理
├── history.py              # 版本历史记录
├── base_dto.py             # 数据传输对象
├── base_schemas.py         # Pydantic Schema、Page分页类
├── orm_extensions/         # 软删除扩展目录
│   ├── __init__.py
│   ├── soft_delete_hook.py        # 软删除钩子
│   ├── soft_delete_mixin.py       # 软删除Mixin
│   ├── soft_delete_rewriter.py    # SQL重写器
│   └── cascade_soft_delete.py     # 级联软删除
└── __init__.py             # 模块导出
```

### 功能矩阵

| 功能类别 | 功能项 | 状态 |
|----------|--------|------|
| **基础CRUD** | create/read/update/delete | ✅ 完整实现 |
| **查询** | Query对象、条件过滤、排序 | ✅ 完整实现 |
| **分页** | Query分页、Select分页 | ✅ 完整实现 |
| **批量操作** | 批量更新、批量删除 | ✅ 完整实现 |
| **软删除** | 自动过滤、恢复、级联 | ✅ 完整实现 |
| **版本控制** | 乐观锁(ver字段) | ✅ 完整实现 |
| **历史记录** | sqlalchemy-history集成 | ✅ 可选功能 |
| **序列化** | to_dict、关联序列化 | ✅ 完整实现 |
| **会话管理** | scoped_session、依赖注入 | ✅ 完整实现 |

## 快速开始

### 安装依赖

```bash
pip install sqlalchemy>=2.0.0
# 可选：历史记录功能
pip install sqlalchemy-history
```

### 最小示例

```python
from fastapi import FastAPI
from yweb.orm import init_database, BaseModel, get_engine
from yweb import OK
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String

# 1. 定义模型
class User(BaseModel):
    __tablename__ = "user"
    username: Mapped[str] = mapped_column(String(50))
    email: Mapped[str] = mapped_column(String(100))

# 2. 创建应用
app = FastAPI()

@app.on_event("startup")
def startup():
    init_database("sqlite:///./test.db")
    BaseModel.metadata.create_all(bind=get_engine())

# 3. CRUD接口
@app.get("/users")
def list_users(page: int = 1, page_size: int = 10):
    return OK(User.query.paginate(page=page, page_size=page_size))

@app.post("/users")
def create_user(data: dict):
    user = User(**data)
    user.save(True)
    return OK(user)
```

## 版本信息

- **当前版本**: 1.0.0
- **SQLAlchemy版本**: >= 2.0.0
- **Python版本**: >= 3.9

## 相关链接

- [ORM使用指南](../docs/orm_guide.md)
- [分页功能指南](../docs/pagination_guide.md)
- [软删除指南](../docs/soft_delete_guide.md)
