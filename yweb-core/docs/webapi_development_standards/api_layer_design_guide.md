# API 层设计规范

本文档定义了 yweb 框架中 API 层（路由层）的设计规范，重点阐述"瘦 API"原则和 DTO 的正确使用方式。

---

## 目录

1. [瘦 API 原则](#1-瘦-api-原则)
2. [Schema 设计规范](#2-schema-设计规范)
3. [响应返回规范](#3-响应返回规范)
4. [完整示例](#4-完整示例)
5. [检查清单](#5-检查清单)

---

## 1. 瘦 API 原则

### 1.1 API 层的职责边界

API 层（路由层）应该保持**精简**，只负责以下四项职责：

| 职责 | 说明 | 示例 |
|------|------|------|
| 参数验证 | 通过 Pydantic Schema 自动完成 | `data: DepartmentCreate` |
| DTO 转换 | 将模型/数据转换为响应格式 | `DepartmentResponse.from_entity(dept)` |
| 异常处理 | 捕获业务异常并转换为 HTTP 响应 | `except ValueError as e:` |
| 调用服务层 | 委托业务逻辑给服务层 | `org_service.create_dept(...)` |

### 1.2 业务逻辑应该在服务层

以下逻辑**不应该**出现在 API 层：

| 反模式 | 说明 |
|--------|------|
| 唯一性校验 | `if Model.query.filter_by(code=code).first():` |
| 关联数据处理 | `for rel in rels: rel.delete()` |
| 状态切换逻辑 | `if is_primary: other.is_primary = False` |
| 计算逻辑 | `level = parent.level + 1` |
| 事务管理 | `db.session.commit()` |

**正确做法**：将上述逻辑封装到服务层方法中。

### 1.3 对比示例

#### ❌ 错误：API 层包含业务逻辑

```python
@router.post("/create")
async def create_department(data: DepartmentCreate):
    # ❌ 业务逻辑：唯一性校验
    existing = dept_model.query.filter_by(code=data.code).first()
    if existing:
        raise ValueError("编码已存在")
    
    # ❌ 业务逻辑：level 计算
    level = 1
    if data.parent_id:
        parent = dept_model.get(data.parent_id)
        level = parent.level + 1
    
    # ❌ 业务逻辑：创建和保存
    dept = dept_model(
        name=data.name,
        code=data.code,
        level=level,
    )
    dept.save()
    dept.update_path_and_level()
    dept.save(commit=True)
    
    return Resp.OK(data=DepartmentResponse.from_entity(dept))
```

#### ✅ 正确：API 层只调用服务层

```python
@router.post("/create", response_model=ItemResponse[DepartmentResponse])
async def create_department(data: DepartmentCreate):
    try:
        # ✅ 一行调用服务层，所有业务逻辑在服务层
        dept = org_service.create_dept(
            org_id=data.org_id,
            name=data.name,
            code=data.code,
            parent_id=data.parent_id,
        )
        return Resp.OK(data=DepartmentResponse.from_entity(dept), message="创建成功")
    except ValueError as e:
        return Resp.BadRequest(message=str(e))
```

---

## 2. Schema 设计规范

### 2.1 请求 Schema vs 响应 Schema

| 类型 | 基类 | 用途 |
|------|------|------|
| 请求 Schema | `BaseModel` | 创建/更新请求的参数验证 |
| 响应 Schema | `DTO` | API 响应的数据转换 |

### 2.2 响应 Schema 必须继承 DTO

响应 Schema **必须**继承 `yweb.orm.DTO`，而非直接继承 `BaseModel`：

```python
# ❌ 错误：直接继承 BaseModel
from pydantic import BaseModel

class DepartmentResponse(BaseModel):
    id: int
    name: str
    ...

# ✅ 正确：继承 DTO
from yweb.orm import DTO

class DepartmentResponse(DTO):
    id: int
    name: str
    ...
```

### 2.3 DTO 提供的便捷方法

| 方法 | 用途 | 示例 |
|------|------|------|
| `from_entity(obj)` | 从单个 ORM 对象创建 | `UserResponse.from_entity(user)` |
| `from_page(page_result)` | 从分页结果创建 | `UserResponse.from_page(page_result)` |
| `from_dict(data)` | 从字典创建 | `UserResponse.from_dict(data)` |
| `from_list(items)` | 从列表批量创建 | `UserResponse.from_list(users)` |
| `from_tree(items)` | 从扁平列表构建树 | `MenuResponse.from_tree(menus)` |

### 2.4 from_entity vs from_dict - 扩展字段处理

当用户在基础模型上扩展自定义字段时，两种方法行为不同：

| 方法 | 行为 | 适用场景 |
|------|------|----------|
| `from_entity(entity)` | 只获取 DTO 定义的字段 | 只需要基础字段 |
| `from_dict(entity.to_dict())` | 获取实体的全部字段 | 需要包含用户扩展字段 |

> 详细说明请参考 [DTO 与响应处理规范](dto_response_guide.md#34-from_entity-vs-from_dict---扩展字段处理重要)

### 2.5 datetime 字段处理

DTO 会自动将 `datetime` 格式化为字符串，因此响应 Schema 中时间字段应定义为 `str` 类型：

```python
class DepartmentResponse(DTO):
    # ✅ 正确：时间字段用 str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    # ❌ 错误：时间字段用 datetime
    # created_at: datetime
```

### 2.6 支持用户扩展字段

如果需要支持用户在 ORM 模型中添加的自定义字段自动返回，配置 `extra="allow"`：

```python
from pydantic import ConfigDict

class DepartmentResponse(DTO):
    id: int
    name: str
    ...
    
    # 允许额外字段通过（用户扩展字段）
    model_config = ConfigDict(from_attributes=True, extra="allow")
```

---

## 3. 响应返回规范

### 3.0 必须声明 response_model

**所有接口都应声明 `response_model`**，使 `/docs` 文档显示正确的响应格式。框架提供三种响应模型：

```python
from yweb.response import Resp, PageResponse, ItemResponse, OkResponse
```

| 响应模型 | 适用场景 | 示例 |
|---------|---------|------|
| `PageResponse[T]` | 分页列表 | `response_model=PageResponse[DeptResponse]` |
| `ItemResponse[T]` | 单条实体 | `response_model=ItemResponse[DeptResponse]` |
| `OkResponse` | 简单操作（delete/remove 等） | `response_model=OkResponse` |

> 详见 [DTO 与响应处理规范 - 4.5 response_model 响应文档规范](dto_response_guide.md#45-response_model-响应文档规范重要)

### 3.1 不需要 `.model_dump()`

使用 DTO 便捷方法后，**不需要**调用 `.model_dump()`：

```python
# ❌ 错误：多余的 .model_dump()
return Resp.OK(data=DepartmentResponse.from_entity(dept).model_dump())

# ❌ 错误：手动创建 + .model_dump()
return Resp.OK(data=DepartmentResponse(**dept.to_dict()).model_dump())

# ✅ 正确：直接返回 DTO 实例
return Resp.OK(data=DepartmentResponse.from_entity(dept))
```

### 3.2 各场景的规范写法

#### 单个实体

```python
# 从 ORM 对象
return Resp.OK(data=DepartmentResponse.from_entity(dept))

# 有附加字段时，先构建字典
data = dept.to_dict()
data["employee_count"] = len(dept.employees)
return Resp.OK(data=DepartmentResponse.from_dict(data))
```

#### 分页列表

```python
page_result = dept_model.query.paginate(page=page, page_size=page_size)

# ✅ 推荐：使用 from_page
return Resp.OK(data=DepartmentResponse.from_page(page_result))
```

#### 普通列表（不分页）

```python
roles = role_model.query.all()

# ✅ 推荐：使用 from_list
return Resp.OK(data=RoleResponse.from_list(roles))
```

#### 树形数据

```python
menus = menu_model.query.order_by(menu_model.sort_order).all()

# ✅ 推荐：使用 from_tree
return Resp.OK(data=MenuResponse.from_tree(menus))
```

### 3.3 有附加字段的处理

当需要在响应中添加 ORM 对象本身不包含的字段时：

```python
@router.get("/get")
async def get_department(dept_id: int, include: Optional[str] = None):
    dept = dept_model.get(dept_id)
    if not dept:
        return Resp.NotFound(message=f"部门不存在: {dept_id}")
    
    # 无附加信息时直接用 from_entity
    if not include:
        return Resp.OK(data=DepartmentResponse.from_entity(dept))
    
    # 有附加信息时构建字典
    data = dept.to_dict()
    include_options = set(include.split(","))
    
    if "employee_count" in include_options:
        data["employee_count"] = len(dept.employee_dept_rels)
    
    if "leader_name" in include_options:
        if dept.primary_leader:
            data["leader_name"] = dept.primary_leader.name
    
    return Resp.OK(data=DepartmentResponse.from_dict(data))
```

---

## 4. 完整示例

### 4.1 Schema 定义

```python
"""部门相关 Schema"""

from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict
from yweb.orm import DTO


# ==================== 请求 Schema ====================

class DepartmentCreate(BaseModel):
    """创建部门请求 - 继承 BaseModel"""
    org_id: int = Field(..., description="所属组织ID")
    name: str = Field(..., min_length=1, max_length=100, description="部门名称")
    code: Optional[str] = Field(None, max_length=50, description="部门编码")
    parent_id: Optional[int] = Field(None, description="父部门ID")


class DepartmentUpdate(BaseModel):
    """更新部门请求 - 继承 BaseModel"""
    name: Optional[str] = Field(None, description="部门名称")
    code: Optional[str] = Field(None, description="部门编码")


# ==================== 响应 Schema ====================

class DepartmentResponse(DTO):
    """部门响应 - 继承 DTO"""
    id: int = Field(..., description="部门ID")
    org_id: int = Field(..., description="所属组织ID")
    name: str = Field(..., description="部门名称")
    code: Optional[str] = Field(None, description="部门编码")
    parent_id: Optional[int] = Field(None, description="父部门ID")
    level: int = Field(1, description="部门层级")
    is_active: bool = Field(True, description="是否启用")
    created_at: Optional[str] = Field(None, description="创建时间")
    updated_at: Optional[str] = Field(None, description="更新时间")
    
    # 附加字段（可选）
    employee_count: Optional[int] = Field(None, description="员工数量")
    leader_name: Optional[str] = Field(None, description="负责人姓名")
    
    # 允许用户扩展字段通过
    model_config = ConfigDict(from_attributes=True, extra="allow")
```

### 4.2 API 定义

```python
"""部门 CRUD API"""

from fastapi import APIRouter, Query
from yweb.response import Resp, PageResponse, ItemResponse, OkResponse

from .schemas import DepartmentCreate, DepartmentUpdate, DepartmentResponse
from .services import org_service

router = APIRouter()


@router.get("/list", response_model=PageResponse[DepartmentResponse])
async def list_departments(
    org_id: int = Query(..., description="组织ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """获取部门列表 - 分页"""
    page_result = dept_model.query.filter_by(org_id=org_id).paginate(
        page=page, page_size=page_size
    )
    return Resp.OK(data=DepartmentResponse.from_page(page_result))


@router.get("/get", response_model=ItemResponse[DepartmentResponse])
async def get_department(dept_id: int = Query(...)):
    """获取部门详情"""
    dept = dept_model.get(dept_id)
    if not dept:
        return Resp.NotFound(message=f"部门不存在: {dept_id}")
    return Resp.OK(data=DepartmentResponse.from_entity(dept))


@router.post("/create", response_model=ItemResponse[DepartmentResponse])
async def create_department(data: DepartmentCreate):
    """创建部门"""
    try:
        dept = org_service.create_dept(
            org_id=data.org_id,
            name=data.name,
            code=data.code,
            parent_id=data.parent_id,
        )
        return Resp.OK(data=DepartmentResponse.from_entity(dept), message="创建成功")
    except ValueError as e:
        return Resp.BadRequest(message=str(e))


@router.post("/update", response_model=ItemResponse[DepartmentResponse])
async def update_department(
    data: DepartmentUpdate,
    dept_id: int = Query(...),
):
    """更新部门"""
    try:
        update_data = data.model_dump(exclude_unset=True)
        dept = org_service.update_dept(dept_id=dept_id, **update_data)
        return Resp.OK(data=DepartmentResponse.from_entity(dept), message="更新成功")
    except ValueError as e:
        return Resp.BadRequest(message=str(e))


@router.post("/delete", response_model=OkResponse)
async def delete_department(dept_id: int = Query(...)):
    """删除部门"""
    try:
        org_service.delete_dept(dept_id=dept_id)
        return Resp.OK(data={"id": dept_id}, message="删除成功")
    except ValueError as e:
        return Resp.BadRequest(message=str(e))
```

---

## 5. 检查清单

### API 层检查

| 检查项 | 说明 |
|--------|------|
| ☐ 是否声明了 `response_model`？ | PageResponse / ItemResponse / OkResponse |
| ☐ 是否只有参数验证、DTO 转换、异常处理、调用服务层？ | 瘦 API 原则 |
| ☐ 是否所有业务逻辑都在服务层？ | 无数据库操作/业务判断 |
| ☐ 是否正确捕获 ValueError 并返回合适的 HTTP 响应？ | 异常处理 |
| ☐ 是否使用 DTO 便捷方法而非 `.model_dump()`？ | 响应规范 |

### Schema 检查

| 检查项 | 说明 |
|--------|------|
| ☐ 请求 Schema 是否继承 `BaseModel`？ | 请求验证 |
| ☐ 响应 Schema 是否继承 `DTO`？ | 响应转换 |
| ☐ 时间字段是否定义为 `Optional[str]`？ | datetime 自动格式化 |
| ☐ 是否需要 `extra="allow"` 支持扩展字段？ | 用户自定义字段 |

### 响应返回检查

| 场景 | response_model | 正确写法 |
|------|---------------|----------|
| 分页列表 | `PageResponse[T]` | `Resp.OK(data=XxxResponse.from_page(page_result))` |
| 单个实体 | `ItemResponse[T]` | `Resp.OK(data=XxxResponse.from_entity(obj))` |
| 字典数据 | `ItemResponse[T]` | `Resp.OK(data=XxxResponse.from_dict(data))` |
| 普通列表 | `ItemResponse[T]` | `Resp.OK(data=XxxResponse.from_list(items))` |
| 树形结构 | `OkResponse` | `Resp.OK(data=XxxResponse.from_tree(items))` |
| 简单操作 | `OkResponse` | `Resp.OK(data={"id": id}, message="删除成功")` |

---

## 相关文档

- [DTO 与响应处理规范](dto_response_guide.md) - DTO 的详细配置和高级用法
- [Model 与 Service 层设计规范](model_and_service_design_guide.md) - 服务层设计规范
