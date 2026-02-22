# DTO 与响应处理规范

本文档详细说明 WebAPI 开发中 DTO（数据传输对象）的使用、响应格式规范和异常处理。

---

## 目录

1. [DTO 基础](#1-dto-基础)
2. [DTO 配置详解](#2-dto-配置详解)
3. [DTO 转换方法](#3-dto-转换方法)
4. [响应格式规范](#4-响应格式规范)
5. [异常处理规范](#5-异常处理规范)
6. [完整示例](#6-完整示例)
7. [最佳实践](#7-最佳实践)

---

## 1. DTO 基础

### 1.1 什么是 DTO

DTO（Data Transfer Object）是用于 API 响应的数据传输对象，继承自 `yweb.orm.DTO`：

```python
from yweb import DTO

class UserResponse(DTO):
    """用户响应 DTO"""
    id: int = 0
    username: str = ""
    name: Optional[str] = None
    email: Optional[str] = None
    created_at: str = ""
```

### 1.2 DTO vs Pydantic BaseModel

| 特性 | DTO | BaseModel |
|------|-----|-----------|
| 继承关系 | 继承自 BaseModel | Pydantic 原生 |
| 主要用途 | API 响应模型 | 请求模型、通用数据验证 |
| `from_entity()` | ✅ 支持 | ❌ 不支持 |
| `from_page()` | ✅ 支持 | ❌ 不支持 |
| `_field_mapping` | ✅ 支持 | ❌ 不支持 |
| `_value_processors` | ✅ 支持 | ❌ 不支持 |
| `extra='ignore'` | ✅ 默认启用 | ❌ 需手动配置 |

**使用建议**：
- **响应模型**：使用 `DTO`
- **请求模型**：使用 `BaseModel`

---

## 2. DTO 配置详解

### 2.1 model_config 配置

DTO 基类默认包含以下配置：

```python
class DTO(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,       # 支持从 ORM 对象创建
        populate_by_name=True,      # 支持字段别名
        arbitrary_types_allowed=True,
        extra='ignore',             # 忽略额外字段，便于从字典创建
    )
```

### 2.2 `extra='ignore'` 详解

`extra` 配置控制**传入数据包含模型未定义的额外字段时**的行为：

| 值 | 行为 | 适用场景 |
|---|---|---|
| `'forbid'` | **报错** - 抛出 `ValidationError` | 严格验证 |
| `'ignore'` | **忽略** - 静默丢弃额外字段 | DTO 推荐 |
| `'allow'` | **保留** - 额外字段存入 `__pydantic_extra__` | 动态数据 |

**示例对比**：

```python
class UserDTO(DTO):  # 默认 extra='ignore'
    id: int
    name: str

# 传入数据包含额外字段
data = {"id": 1, "name": "张三", "email": "test@example.com", "age": 25}
```

**`extra='ignore'`（当前配置）**：
```python
user = UserDTO(**data)  # ✅ 成功
# user.id = 1, user.name = "张三"
# email 和 age 被静默忽略
```

**`extra='forbid'`**：
```python
user = UserDTO(**data)  # ❌ 报错
# pydantic.ValidationError: Extra inputs are not permitted
```

### 2.3 为什么需要 `extra='ignore'`

在实际开发中，数据源（如 ORM 对象、外部 API）通常包含比 DTO 定义更多的字段：

```python
# scheduler.get_job() 返回的字典包含很多额外字段
job_dict = {
    "code": "DAILY_REPORT",
    "name": "每日报表",
    # DTO 定义的字段 ↑
    
    # 额外字段 ↓（DTO 未定义）
    "apscheduler_id": "...",
    "func": <function>,
    "triggers": [...],
}

# 有了 extra='ignore'，可以直接创建 DTO
JobResponse.from_dict(job_dict)  # ✅ 自动忽略额外字段
```

### 2.4 `_field_mapping` 字段映射

输出时重命名字段：

```python
class UserResponse(DTO):
    is_active: bool = True
    
    # 输出时 is_active -> status
    _field_mapping = {'is_active': 'status'}

user = UserResponse(is_active=True)
print(user.model_dump())
# {'status': True}  # 字段名已重命名
```

### 2.5 `_value_processors` 值处理器

在 `from_entity()` / `from_dict()` 创建 DTO 时转换字段值。
**字段类型声明应与处理器转换后的类型一致**：

```python
class UserResponse(DTO):
    is_active: str = "active"    # 处理后是字符串，所以声明为 str
    
    _value_processors = {
        'is_active': lambda v: 'active' if v else 'inactive',
    }

# 通过 from_entity 创建时，处理器自动执行
user = UserResponse.from_entity(entity)  # entity.is_active = True
print(user.model_dump())
# {'is_active': 'active'}  # 值已转换
```

---

## 3. DTO 转换方法

### 3.1 转换方法对照表

| 方法 | 数据源 | 返回值 | 适用场景 |
|------|--------|--------|----------|
| `from_entity(entity)` | ORM 对象 | DTO 实例 | 单个对象详情 |
| `from_list(items)` | 列表 | DTO 列表 | 下拉选项、不分页列表 |
| `from_page(page_result)` | Page 对象 | 分页字典 | 分页查询 |
| `from_tree(items)` | 扁平列表 | 树形字典列表 | 菜单、组织架构 |
| `from_dict(dict)` | 字典 | DTO 实例 | 从字典创建（自动忽略额外字段） |

### 3.2 from_entity - 单个对象

从 ORM 实体创建 DTO：

```python
user = User.get(1)
response = UserResponse.from_entity(user)
return Resp.OK(response)
```

### 3.3 from_dict - 从字典创建

从字典创建 DTO，自动处理 datetime 格式化：

```python
data = entity.to_dict()
data["extra_field"] = "额外信息"
response = UserResponse.from_dict(data)
return Resp.OK(response)
```

### 3.4 from_entity vs from_dict - 扩展字段处理（重要）

当用户在基础模型上扩展自定义字段时，两种方法行为不同：

```python
# 用户扩展的组织模型
class MyOrganization(AbstractOrganization):
    license_no: str = ...    # 用户自定义字段
    tax_id: str = ...        # 用户自定义字段
```

| 方法 | 行为 | 结果 |
|------|------|------|
| `from_entity(org)` | 只获取 DTO 定义的字段 | `{"id": 1, "name": "..."}` |
| `from_dict(org.to_dict())` | 获取实体的全部字段 | `{"id": 1, "name": "...", "license_no": "...", "tax_id": "..."}` |

**原因**：`from_entity` 遍历 DTO 的 `model_fields`，而 `from_dict` 接收字典的全部键值，配合 `extra="allow"` 保留额外字段。

**使用建议**：

| 场景 | 推荐方法 |
|------|----------|
| 只需要基础字段 | `Response.from_entity(entity)` |
| 需要包含用户扩展字段 | `Response.from_dict(entity.to_dict())` |

### 3.5 from_list - 简单列表

从列表批量转换（不分页）：

```python
roles = Role.query.all()
response = RoleResponse.from_list(roles)
return Resp.OK(response)
```

### 3.6 from_page - 分页查询

从分页结果转换：

```python
page_result = User.query.filter(...).paginate(page=1, page_size=10)
return Resp.OK(UserResponse.from_page(page_result))
```

返回结构：
```json
{
    "rows": [...],
    "total_records": 100,
    "page": 1,
    "page_size": 10,
    "total_pages": 10,
    "has_prev": false,
    "has_next": true
}
```

### 3.7 from_tree - 树形结构

从扁平列表构建树形结构：

```python
class MenuResponse(DTO):
    id: int = 0
    name: str = ""
    parent_id: Optional[int] = None

menus = Menu.query.all()
tree = MenuResponse.from_tree(menus)
return Resp.OK(tree)
```

### 3.6 from_dict - 从字典创建

当数据源是字典（而非 ORM 对象）时使用：

```python
# 从外部 API 或内部方法返回的字典创建 DTO
job_dict = scheduler.get_job(code)
response = JobResponse.from_dict(job_dict)
return Resp.OK(response)

# 批量转换
jobs = scheduler.get_jobs()
return Resp.OK([
    JobResponse.from_dict(j) for j in jobs
])
```

---

## 4. 响应格式规范

### 4.1 标准响应结构

所有 API 响应使用统一格式：

```json
{
    "status": "success",      // 状态：success / error
    "message": "请求成功",     // 响应消息
    "msg_details": [],        // 详细信息列表
    "data": { ... }           // 响应数据
}
```

### 4.2 Resp 系列方法

| 方法 | HTTP 状态码 | 用途 |
|------|------------|------|
| `Resp.OK(data, message)` | 200 | 成功响应 |
| `Resp.BadRequest(message, msg_details)` | 400 | 请求参数错误 |
| `Resp.Unauthorized(message)` | 401 | 未认证 |
| `Resp.Forbidden(message)` | 403 | 无权限 |
| `Resp.NotFound(message)` | 404 | 资源不存在 |
| `Resp.Conflict(message)` | 409 | 资源冲突（如重复） |
| `Resp.ServerError(message)` | 500 | 服务器错误 |

**参数写法**：以 `Resp.OK()`为例 ，签名为 `def OK(data: Any = None, message: str = "请求成功")`，以下写法等效：

```python
# 完整写法
Resp.OK(data=user, message="创建成功")

# 省略 data= 
Resp.OK(user, message="创建成功")

# 省略 全部位置参数
Resp.OK(user, "创建成功")
```

### 4.3 成功响应示例

```python
# 单个对象
return Resp.OK(UserResponse.from_entity(user))

# 分页列表
return Resp.OK(UserResponse.from_page(page_result))

# 带消息
return Resp.OK(data=user, message="用户创建成功")

# 仅消息
return Resp.OK(message="操作成功")
```

### 4.4 错误响应示例

```python
# 400 参数错误
return Resp.BadRequest(message="参数错误", msg_details=["username 不能为空"])

# 404 未找到
return Resp.NotFound(message=f"用户 {user_id} 不存在")

# 409 冲突
return Resp.Conflict(message=f"用户名 {username} 已存在")

# 403 无权限
return Resp.Forbidden(message="无权访问此资源")
```

### 4.5 response_model 响应文档规范（重要）

**所有 API 接口都应声明 `response_model`**，否则 `/docs` 中 Successful Response 会显示为 `"string"`，无法为调用方提供有效的接口文档。

框架提供三种响应模型，覆盖所有场景：

| 响应模型 | 适用场景 | 示例 |
|---------|---------|------|
| `PageResponse[T]` | 分页列表 | `response_model=PageResponse[UserResponse]` |
| `ItemResponse[T]` | 单条实体（详情、创建、更新） | `response_model=ItemResponse[UserResponse]` |
| `OkResponse` | 简单操作（删除、移除、设置等） | `response_model=OkResponse` |

**导入方式**：

```python
from yweb.response import Resp, PageResponse, ItemResponse, OkResponse
```

**完整用法示例**：

```python
# 分页列表：PageResponse[T]
@router.get("/list", response_model=PageResponse[UserResponse], summary="获取用户列表")
def get_users(...):
    page_result = User.query.paginate(page=page, page_size=page_size)
    return Resp.OK(UserResponse.from_page(page_result))

# 单条实体：ItemResponse[T]
@router.get("/get", response_model=ItemResponse[UserResponse], summary="获取用户详情")
def get_user(user_id: int):
    user = User.get(user_id)
    return Resp.OK(UserResponse.from_entity(user))

# 简单操作：OkResponse
@router.post("/delete", response_model=OkResponse, summary="删除用户")
def delete_user(user_id: int):
    user_service.delete(user_id)
    return Resp.OK(data={"id": user_id}, message="删除成功")
```

> **注意**：`response_model` 只描述 200 成功响应的 Schema。422 验证错误由框架的 `register_exception_handlers` 自动覆盖为项目统一格式，无需手动处理。

---

## 5. 异常处理规范

### 5.1 异常处理策略

| 异常类型 | 处理方式 | HTTP 状态码 |
|---------|---------|------------|
| `ValueError` | 参数校验失败 | 400 |
| `NotFoundException` | 资源不存在 | 404 |
| `ConflictException` | 资源冲突 | 409 |
| `PermissionDeniedException` | 权限不足 | 403 |
| 其他 `Exception` | 服务器内部错误 | 500 |

### 5.2 使用 Resp 方法（推荐）

```python
@router.get("/users/{user_id}")
def get_user(user_id: int):
    user = User.get(user_id)
    if not user:
        return Resp.NotFound(message=f"用户 {user_id} 不存在")
    return Resp.OK(UserResponse.from_entity(user))

@router.post("/users")
def create_user(request: CreateUserRequest):
    # 检查用户名是否存在
    existing = User.get_by_username(request.username)
    if existing:
        return Resp.Conflict(message=f"用户名 {request.username} 已存在")
    
    # 创建用户
    user = User(username=request.username, ...)
    user.save(commit=True)
    return Resp.OK(data=UserResponse.from_entity(user), message="创建成功")
```

### 5.3 使用 HTTPException

适用于需要中断执行流程的场景：

```python
from fastapi import HTTPException, status as http_status

@router.get("/users/{user_id}")
def get_user(user_id: int):
    user = User.get(user_id)
    if not user:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    return Resp.OK(UserResponse.from_entity(user))
```

### 5.4 try-except 模式

```python
@router.post("/users")
def create_user(request: CreateUserRequest):
    try:
        # 创建值对象（内部验证）
        username = Username(request.username)
        password = Password(request.password)
        
        # 业务逻辑
        user_service = UserService()
        user = user_service.create_user(username, password)
        
        return Resp.OK(UserResponse.from_entity(user))
        
    except ValueError as e:
        # 参数验证失败
        return Resp.BadRequest(message=str(e))
    except Exception as e:
        # 其他错误
        return Resp.ServerError(message=f"创建用户失败: {str(e)}")
```

### 5.5 细化异常处理

避免使用过于宽泛的异常捕获：

```python
# ❌ 不推荐：过于宽泛
try:
    ...
except Exception:
    return Resp.ServerError(message="操作失败")

# ✅ 推荐：细化异常类型
try:
    ...
except ValueError as e:
    return Resp.BadRequest(message=str(e))
except PermissionError as e:
    return Resp.Forbidden(message=str(e))
except Exception as e:
    logger.error(f"Unexpected error: {e}")
    return Resp.ServerError(message="服务器内部错误")
```

---

## 6. 完整示例

### 6.1 分页查询示例

```python
from fastapi import APIRouter, Query
from typing import Optional
from yweb import Resp, PageResponse, ItemResponse, OkResponse, DTO

from app.domain.auth.model import User

router = APIRouter(prefix="/users", tags=["用户管理"])


class UserResponse(DTO):
    """用户响应 DTO"""
    id: int = 0
    username: str = ""
    name: Optional[str] = None
    email: Optional[str] = None
    is_active: str = "active"
    created_at: str = ""
    
    _field_mapping = {'is_active': 'status'}
    _value_processors = {
        'is_active': lambda v: 'active' if v else 'inactive',
    }


@router.get("", response_model=PageResponse[UserResponse], summary="获取用户列表")
def get_users(
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    status: Optional[str] = Query(None, description="状态 (active/inactive)"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
):
    """分页查询用户列表"""
    # 构建查询
    query = User.query
    
    if keyword:
        query = query.filter(
            User.username.ilike(f"%{keyword}%") |
            User.name.ilike(f"%{keyword}%")
        )
    
    if status:
        query = query.filter(User.is_active == (status == 'active'))
    
    # 使用 ORM 分页
    page_result = query.order_by(User.created_at.desc()).paginate(
        page=page, page_size=page_size
    )
    
    # 使用 DTO 转换并返回
    return Resp.OK(UserResponse.from_page(page_result))
```

### 6.2 CRUD 完整示例

```python
@router.get("/{user_id}", response_model=ItemResponse[UserResponse], summary="获取用户详情")
def get_user(user_id: int):
    """获取单个用户详情"""
    user = User.get(user_id)
    if not user:
        return Resp.NotFound(message=f"用户 {user_id} 不存在")
    return Resp.OK(UserResponse.from_entity(user))


@router.post("", response_model=ItemResponse[UserResponse], summary="创建用户")
def create_user(request: CreateUserRequest):
    """创建新用户"""
    # 检查用户名是否存在
    existing = User.query.filter_by(username=request.username).first()
    if existing:
        return Resp.Conflict(message=f"用户名 {request.username} 已存在")
    
    try:
        user = User(
            username=request.username,
            name=request.name,
            email=request.email,
        )
        user.save(commit=True)
        return Resp.OK(UserResponse.from_entity(user), message="创建成功")
    except ValueError as e:
        return Resp.BadRequest(message=str(e))


@router.put("/{user_id}", response_model=ItemResponse[UserResponse], summary="更新用户")
def update_user(user_id: int, request: UpdateUserRequest):
    """更新用户信息"""
    user = User.get(user_id)
    if not user:
        return Resp.NotFound(message=f"用户 {user_id} 不存在")
    
    user.name = request.name
    user.email = request.email
    user.save(commit=True)
    
    return Resp.OK(UserResponse.from_entity(user), message="更新成功")


@router.delete("/{user_id}", response_model=OkResponse, summary="删除用户")
def delete_user(user_id: int):
    """删除用户（软删除）"""
    user = User.get(user_id)
    if not user:
        return Resp.NotFound(message=f"用户 {user_id} 不存在")
    
    user.soft_delete(commit=True)
    return Resp.OK(message="删除成功")
```

### 6.3 从字典创建 DTO 示例

```python
from yweb import Resp, DTO, PageResponse, Page
from .models import SchedulerJobHistory


class ExecutionResponse(DTO):
    """执行记录响应"""
    run_id: str = ""
    job_code: str = ""
    status: str = ""
    start_time: Optional[str] = None
    end_time: Optional[str] = None


class JobResponse(DTO):
    """任务响应"""
    code: str = ""
    name: str = ""
    is_paused: bool = False
    next_run_time: Optional[str] = None


@router.get("/jobs", summary="获取任务列表")
def get_jobs():
    """从字典列表创建 DTO"""
    jobs = scheduler.get_jobs()  # 返回字典列表
    
    # 使用 from_dict 从字典创建 DTO
    return Resp.OK(data=[
        JobResponse.from_dict(j) for j in jobs
    ])


@router.get("/executions", summary="查询执行历史")
def get_executions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """分页查询执行历史"""
    # 检查服务是否可用
    try:
        history_manager = scheduler._get_history_manager()
        if history_manager is None:
            # 返回空分页
            empty_page = Page(rows=[], total_records=0, page=page, page_size=page_size, total_pages=0)
            return Resp.OK(ExecutionResponse.from_page(empty_page))
    except AttributeError:
        empty_page = Page(rows=[], total_records=0, page=page, page_size=page_size, total_pages=0)
        return Resp.OK(ExecutionResponse.from_page(empty_page))
    
    # 使用 ORM 分页查询
    page_result = SchedulerJobHistory.query.order_by(
        SchedulerJobHistory.start_time.desc()
    ).paginate(page=page, page_size=page_size)
    
    return Resp.OK(ExecutionResponse.from_page(page_result))
```

---

## 7. 最佳实践

### 7.1 DTO 定义规范

```python
class XxxResponse(DTO):
    """响应模型命名：实体名 + Response"""
    
    # 1. 字段定义（带默认值）
    id: int = 0
    name: str = ""
    status: Optional[str] = None
    created_at: str = ""
    
    # 2. 字段映射（可选）
    _field_mapping = {'internal_name': 'external_name'}
    
    # 3. 值处理器（可选，from_entity 创建时执行）
    # 字段类型应与 transform 返回值类型一致
    _value_processors = {
        'field_name': lambda v: transform(v),
    }
```

### 7.2 响应处理规范

| 场景 | response_model | 方法 | 示例 |
|------|---------------|------|------|
| 分页查询结果 | `PageResponse[T]` | `from_page()` | `Resp.OK(UserResponse.from_page(page_result))` |
| 单个 ORM 对象 | `ItemResponse[T]` | `from_entity()` | `Resp.OK(UserResponse.from_entity(user))` |
| 字典数据 | `ItemResponse[T]` | `from_dict()` | `Resp.OK(JobResponse.from_dict(job_dict))` |
| ORM 对象列表 | `ItemResponse[T]` | `from_list()` | `Resp.OK(RoleResponse.from_list(roles))` |
| 树形数据 | `OkResponse` | `from_tree()` | `Resp.OK(MenuResponse.from_tree(menus))` |
| 简单操作 | `OkResponse` | 无需 DTO | `Resp.OK(data={"id": id}, message="删除成功")` |

### 7.3 异常处理规范

| 场景 | 使用方法 |
|------|---------|
| 资源不存在 | `Resp.NotFound(message="...")` |
| 参数错误 | `Resp.BadRequest(message="...", msg_details=[...])` |
| 资源冲突 | `Resp.Conflict(message="...")` |
| 权限不足 | `Resp.Forbidden(message="...")` |
| 服务器错误 | `Resp.ServerError(message="...")` |

### 7.4 空分页处理

当数据源不可用时，返回标准空分页结构：

```python
from yweb.orm import Page

empty_page = Page(
    rows=[], 
    total_records=0, 
    page=page, 
    page_size=page_size, 
    total_pages=0
)
return Resp.OK(XxxResponse.from_page(empty_page))
```

### 7.5 不要做的事

```python
# ❌ 不要手动构建分页结构
return Resp.OK(data={
    "rows": [...],
    "total_records": total,
    "page": page,
    ...
})

# ✅ 使用 from_page()
return Resp.OK(XxxResponse.from_page(page_result))

# ❌ 不要手动调用 model_dump()
return Resp.OK(UserResponse.from_entity(user).model_dump())

# ✅ 直接返回 DTO 实例（FastAPI 自动序列化）
return Resp.OK(UserResponse.from_entity(user))

# ❌ 不要使用过于宽泛的异常捕获
except Exception:
    pass

# ✅ 细化异常类型
except ValueError as e:
    return Resp.BadRequest(message=str(e))
except Exception as e:
    logger.error(f"Error: {e}")
    return Resp.ServerError(message="服务器内部错误")
```

---

## 相关文档

- [development_guide.md](development_guide.md) - API 与 Service 层开发规范
- [auth_flow_guide.md](auth_flow_guide.md) - 认证流程指南
- [03_orm_guide.md](../03_orm_guide.md) - ORM 使用指南
