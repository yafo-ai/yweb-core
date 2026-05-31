# 项目时区问题记录

## 问题概述

项目中存在多处时区处理不一致的问题，可能导致时间偏差或比较错误。

## 问题分类

### 1. ✅ 已修复：auth/mixins.py

**位置**: `yweb/auth/mixins.py`

**处理方式**:
- 使用 `DateTime(timezone=True)` 声明带时区字段
- 配合 `_as_utc()` 辅助函数处理 SQLite/MySQL 回落问题
- 将 naive datetime 视为 UTC 处理

**代码示例**:
```python
def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
```

### 2. ⚠️ 潜在问题：ORM 核心模型 core_model.py

**位置**: `yweb/orm/core_model.py`

**问题描述**:
```python
created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=False),   # 没有时区信息
    server_default=func.now(),   # 使用数据库服务器时间
)
updated_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=False),
    onupdate=func.now(),
)
```

**风险**:
- 存储的是数据库服务器的本地时间
- naive datetime（没有时区标记）
- 如果应用服务器和数据库服务器时区不一致，会出现时间偏差

### 3. ⚠️ 潜在问题：其他模块使用 datetime.now

**位置**:
- `yweb/rbac/models/subject_role.py:102`
- `yweb/orm/statemachine/state_history.py:95`
- `yweb/rbac/models/subject_permission.py:96`

**问题描述**:
```python
granted_at: Mapped[datetime] = mapped_column(
    DateTime,              # 默认 timezone=False
    default=datetime.now,  # Python 本地时间，非 UTC
)
```

**风险**:
- `datetime.now()` 返回的是 Python 所在服务器的本地时间
- 如果应用服务器和数据库服务器时区不一致，会出现时间偏差
- 与 `core_model.py` 使用数据库时间的方式不一致

## 风险场景

1. **跨时区部署**: 应用服务器和数据库服务器在不同时区
2. **容器化部署**: 容器默认时区可能与宿主机不一致
3. **时间比较**: 不同时区来源的时间直接比较会产生错误结果

## 当前状态

- **暂不处理**: 当前应用服务器和数据库服务器在同一时区，暂时不会出现明显问题
- **记录备案**: 作为技术债务记录，待后续统一处理

## 建议修复方案（未来）

### 方案一：统一使用 UTC（推荐）

1. 所有时间字段声明为 `DateTime(timezone=True)`
2. 使用 `datetime.now(timezone.utc)` 替代 `datetime.now()`
3. 数据库字段统一存储 UTC 时间

### 方案二：统一使用数据库时间

1. 所有时间字段使用 `server_default=func.now()` 或 `onupdate=func.now()`
2. 避免在 Python 代码中生成时间
3. 确保数据库服务器时区配置正确

## 相关文件

- `yweb/auth/mixins.py` - 已修复，参考实现
- `yweb/orm/core_model.py` - 需要处理
- `yweb/rbac/models/subject_role.py` - 需要处理
- `yweb/orm/statemachine/state_history.py` - 需要处理
- `yweb/rbac/models/subject_permission.py` - 需要处理

## 记录时间

- 发现时间: 2026-04-22
- 记录人: AI Assistant
- 优先级: 低（当前环境无影响）
