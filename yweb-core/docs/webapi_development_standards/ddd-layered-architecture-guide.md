# yweb DDD 分层架构实践指导

> 基于 Active Record 模式，适度采用 DDD 的分层思想和聚合概念，保持简单直接。

## 架构定位

本框架采用 **Active Record + DDD 思想** 的务实组合：

- **Active Record 模式**：领域模型直接继承 ORM 基类，具备数据访问能力
- **DDD 分层思想**：保持清晰的职责分离，业务规则封装在领域模型中
- **富领域模型**：领域模型不仅包含数据，还包含业务行为和验证逻辑

这种方式在保持简单的同时，避免了纯 DDD 的 Repository 层带来的额外复杂性。

## 目录

- [设计原则](#设计原则)
- [分层架构](#分层架构)
- [各层职责详解](#各层职责详解)
- [服务层拆分原则](#服务层拆分原则)
- [异常处理策略](#异常处理策略)
- [代码示例](#代码示例)
- [最佳实践](#最佳实践)
- [反模式（避免）](#反模式避免)

---

## 设计原则

### 核心思想

1. **简单直接，避免过度设计**
   - 使用 Python 标准的 `ValueError` 表达业务规则违反
   - 不定义自定义异常类
   - 领域模型继承自 ORM 基类，具备数据访问能力（Active Record 模式）
   - 不引入 Repository 层，避免不必要的复杂性

2. **让每一层只关心自己的事**
   - API 层不需要知道"如何检测循环引用"
   - 服务层不需要知道"HTTP 状态码"
   - 领域模型不需要知道"谁在调用它"

3. **业务规则封装在领域模型中**
   - 单聚合内的业务规则 → 领域模型的 `validate_xxx()` 方法
   - 跨聚合的业务操作 → 服务层
   - HTTP 处理 → API 层
4. **合理规划服务层，统一入口**
   - **原则上 API 层应统一通过服务层调用**，保持调用路径一致
   - 以下情况可以绕过服务层，API 直接调用领域模型：
     - 纯查询操作（无业务逻辑，如 `get_by_id`、`list_all`）
     - 单实体的简单 CRUD（无跨实体协调）
   - 涉及以下情况必须通过服务层：
     - 跨聚合/跨实体的操作
     - 需要事务管理的操作
     - 需要额外权限检查、日志记录的操作
   - 不同领域的服务应该放在不同的服务层文件中

---

## 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│                        API 层 (Thin)                        │
│  - 参数验证、DTO 转换                                        │
│  - 调用服务层或领域模型                                       │
│  - 捕获 ValueError，统一返回 BadRequest                       │
├─────────────────────────────────────────────────────────────┤
│                       服务层 (Service)                       │
│  - 编排跨聚合操作                                            │
│  - 管理事务边界                                              │
│  - 调用领域模型的业务规则方法                                  │
├─────────────────────────────────────────────────────────────┤
│                    领域模型层 (Domain Model)                  │
│  - 封装单聚合内的业务规则                                     │
│  - 提供 validate_xxx() 方法，抛出 ValueError                  │
│  - 高内聚低耦合，合理规划对外提供的方法                        │
├─────────────────────────────────────────────────────────────┤
│                       基础设施层                              │
│  - ORM / 数据库访问                                          │
│  - 外部服务调用                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 各层职责详解

### 1. API 层（瘦）

**职责：**
- ✅ 接收 HTTP 请求，提取参数
- ✅ 参数格式验证（通过 Pydantic Schema）
- ✅ 调用服务层或领域模型
- ✅ 捕获 `ValueError`，返回 `Resp.BadRequest()`
- ✅ DTO 转换（使用 `from_entity` / `from_dict` 便捷方法）

**代码结构：**
```python
@router.post("/create")
async def create_department(data: DepartmentCreate):
    try:
        dept = org_service.create_dept(
            org_id=data.org_id,
            name=data.name,
            code=data.code,
            parent_id=data.parent_id,
        )
        # 使用 DTO 便捷方法，无需 .model_dump()
        return Resp.OK(data=DepartmentResponse.from_entity(dept))
    except ValueError as e:
        return Resp.BadRequest(message=str(e))
```

> **DTO 使用规范：** 详见 [API 层设计规范](webapi项目开发规范/api_layer_design_guide.md) 和 [DTO 与响应处理规范](webapi项目开发规范/dto_response_guide.md)

### 2. 服务层（编排者）

**职责：**
- ✅ 编排跨聚合的业务操作
- ✅ 调用领域模型的验证方法
- ✅ 抛出 `ValueError` 表达业务规则违反

**代码结构：**
```python
def create_dept(self, org_id: int, name: str, code: str = None, 
                parent_id: int = None, **kwargs) -> TDept:
    # 验证组织存在
    org = self.org_model.get(org_id)
    if not org:
        raise ValueError(f"组织不存在: {org_id}")
    
    # 调用领域模型的验证方法
    if code:
        self.dept_model.validate_code_unique(org_id=org_id, code=code)
    
    if parent_id is not None:
        parent = self.dept_model.validate_parent(parent_id=parent_id, org_id=org_id)
        level = parent.level + 1
    
    # 创建实体
    dept = self.dept_model(org_id=org_id, name=name, code=code, ...)
    dept.save(commit=True)
    
    return dept
```

### 3. 领域模型层（富领域模型）

**职责：**
- ✅ 封装单聚合内的业务规则
- ✅ 提供 `validate_xxx()` 方法
- ✅ 抛出 `ValueError` 表达业务规则违反
- ✅ 继承 ORM 基类，具备数据访问能力（Active Record 模式）
- ✅ 使用 `fields.*` API 定义关系，配置级联删除行为

**关系定义与级联删除（重要）：**

> ⚠️ 定义模型关系时，**必须使用 `fields.*` API**，框架提供了级联软删除功能，可自动处理关联数据。

```python
from yweb.orm import BaseModel, fields

class Employee(BaseModel):
    """员工"""
    # ✅ 推荐：部门删除时，员工的 dept_id 设为 NULL
    department = fields.ManyToOne(
        Department,
        on_delete=fields.SET_NULL,  # 级联行为
        nullable=True,
    )

class OrderItem(BaseModel):
    """订单项"""
    # ✅ 推荐：订单删除时，订单项也被软删除
    order = fields.ManyToOne(
        Order,
        on_delete=fields.DELETE,  # 级联软删除
        nullable=False,
    )
```

**级联删除类型**：

| 类型 | 说明 | 适用场景 |
|------|------|----------|
| `fields.DELETE` | 级联软删除子记录 | 强聚合（订单→订单项） |
| `fields.SET_NULL` | 外键设为 NULL | 弱关联（部门→员工） |
| `fields.UNLINK` | 解除多对多关联 | 用户→角色 |
| `fields.PROTECT` | 有子记录时禁止删除 | 分类→产品 |

详见 [08_级联软删除](orm_docs/08_cascade_soft_delete.md)。

**代码结构：**
```python
class AbstractDepartment(BaseModel, TreeMixin):
    
    @classmethod
    def validate_code_unique(cls, org_id: int, code: str, exclude_id: int = None):
        """验证部门编码在组织内唯一"""
        if not code:
            return
        
        query = cls.query.filter_by(org_id=org_id, code=code)
        if exclude_id:
            query = query.filter(cls.id != exclude_id)
        
        if query.first():
            raise ValueError(f"部门编码已存在: {code}")
    
    @classmethod
    def validate_parent(cls, parent_id: int, org_id: int):
        """验证父部门有效性"""
        parent = cls.get(parent_id)
        if not parent:
            raise ValueError(f"父部门不存在: {parent_id}")
        
        if parent.org_id != org_id:
            raise ValueError("父部门不属于同一组织")
        
        return parent
    
    def validate_can_move_to(self, new_parent_id: int):
        """验证是否可以移动到目标父部门"""
        if new_parent_id == self.id:
            raise ValueError("不能将部门移动到自己下面")
        
        new_parent = self.__class__.get(new_parent_id)
        if not new_parent:
            raise ValueError(f"目标父部门不存在: {new_parent_id}")
        
        if new_parent.org_id != self.org_id:
            raise ValueError("不能移动到其他组织的部门下")
        
        if self.is_ancestor_of(new_parent):
            raise ValueError("不能将部门移动到其子部门下")
        
        return new_parent
```

---

## 服务层拆分原则

### 拆分时机

当服务类满足以下任一条件时，应考虑拆分：

- 代码超过 **300 行**
- 包含 **3 个以上**不同聚合的操作
- 职责边界模糊，难以准确命名

### 拆分策略：按聚合根拆分

每个聚合根对应一个独立的服务类：

```
services/
├── org_service.py       # Organization 聚合
├── dept_service.py      # Department 聚合（含负责人）
├── employee_service.py  # Employee 聚合（含关联）
```

### 聚合归属判断

| 操作类型 | 归属服务 | 判断依据 |
|----------|----------|----------|
| 部门负责人管理 | DeptService | 负责人依附于部门存在 |
| 员工-部门关联 | EmployeeService | 关联操作由员工发起 |
| 员工-组织关联 | EmployeeService | 同上 |

**原则**：关联操作归属于"主动方"聚合。

### 跨聚合调用

- 服务间通过**组合**而非继承协作
- 跨聚合验证在**调用方服务**完成
- 保持单向依赖，避免循环引用

```python
class DeptService:
    def __init__(self, org_service: OrgService = None):
        self.org_service = org_service
    
    def create_dept(self, org_id, name, **kwargs):
        # 跨聚合验证：检查组织是否存在
        if self.org_service and not self.org_service.get_org(org_id):
            raise ValueError(f"组织不存在: {org_id}")
        # ... 创建部门
```

### 命名规范

- 服务类：`{聚合根}Service`
- 文件名：`{聚合根小写}_service.py`
- 保持一个文件一个服务类

---

## 异常处理策略

### 核心原则：领域模型使用 ValueError

**为什么选择 ValueError？**

1. **简单直接** - Python 标准库，无需定义额外类
2. **异常与框架解耦** - 不依赖框架自定义异常类
3. **测试简单** - `pytest.raises(ValueError)`
4. **符合 Python 惯例** - ValueError 就是用来表示"值/参数无效"的

### 分层异常使用策略

| 层次 | 推荐异常类型 | 说明 |
|------|-------------|------|
| **领域模型层** | `ValueError` | 保持简单，业务规则验证 |
| **服务层** | `ValueError` 或框架异常 | 简单场景用 ValueError，需要区分状态码时用框架异常 |
| **API 层** | 框架异常（可选） | 需要返回不同 HTTP 状态码时使用 |

**典型场景**：

```python
# 领域模型 - 统一用 ValueError
def validate_can_delete(self):
    if self.children:
        raise ValueError("部门下有子部门，无法删除")

# 服务层 - 简单场景继续用 ValueError
def delete_dept(self, dept_id):
    dept = self.dept_model.get(dept_id)
    if not dept:
        raise ValueError(f"部门不存在: {dept_id}")

# 服务层/API层 - 需要区分状态码时用框架异常
from yweb import Err

def delete_user(self, user_id, current_user):
    if not current_user.is_admin:
        raise Err.forbidden("需要管理员权限")  # 返回 403
    user = User.get(user_id)
    if not user:
        raise Err.not_found("用户不存在")  # 返回 404
```

### API 层统一处理

```python
@router.post("/create")
async def create_department(data: DepartmentCreate):
    try:
        dept = org_service.create_dept(...)
        return Resp.OK(data=...)
    except ValueError as e:
        return Resp.BadRequest(message=str(e))
```

**注意**：不建议通过解析 message 字符串来区分不同的 HTTP 状态码，这种做法脆弱且难以维护。业务规则违反统一返回 `BadRequest` 即可。

### 与框架异常体系的配合

框架提供了完整的业务异常体系（详见 `05_exception_handling.md`），与本文档的 ValueError 策略配合使用：

**全局异常处理器行为**：
- `BusinessException` 及其子类 → 按异常定义的状态码返回（400/401/403/404/409/422/503）
- `ValueError` → 返回 400 BadRequest
- 其他未捕获异常 → 返回 500 Internal Server Error

**框架异常体系概览**：

```
BusinessException (核心业务异常基类)
├── AuthenticationException (401) - 认证失败
├── AuthorizationException (403) - 权限不足
├── ResourceNotFoundException (404) - 资源不存在
├── ResourceConflictException (409) - 资源冲突
├── ValidationException (422) - 数据验证失败
└── ServiceUnavailableException (503) - 服务不可用
```

**快捷方式**：使用 `Err` 类创建异常

```python
from yweb import Err

raise Err.auth("用户名或密码错误")      # 401
raise Err.forbidden("需要管理员权限")   # 403
raise Err.not_found("用户不存在")       # 404
raise Err.conflict("用户名已存在")      # 409
raise Err.invalid("数据验证失败")       # 422
raise Err.unavailable("服务不可用")     # 503
raise Err.fail("操作失败")              # 400
```

### 模块专用异常说明

框架中各模块有独立的异常基类，用于处理模块内部的技术异常：

| 模块 | 基类 | 说明 |
|------|------|------|
| 存储模块 | `StorageError` | 文件上传、存储配额等 |
| 事务模块 | `TransactionError` | 事务状态、保存点等 |
| 状态机模块 | `StateMachineError` | 状态转换、守卫条件等 |

**这些模块异常不继承 `BusinessException`**，原因：
- 它们是**基础设施层**的技术异常，不应直接暴露给用户
- 应在服务层捕获并转换为业务异常或 ValueError

```python
# 服务层捕获技术异常并转换
from yweb.storage.exceptions import FileTooLarge

def upload_avatar(self, file):
    try:
        return storage.save(file)
    except FileTooLarge as e:
        raise ValueError(f"文件过大，最大允许 {e.max_size} 字节")
```

---

## 代码示例

### 完整的创建部门流程

```python
# 1. API 层 - department_api.py
@router.post("/create")
async def create_department(data: DepartmentCreate):
    try:
        dept = org_service.create_dept(
            org_id=data.org_id,
            name=data.name,
            code=data.code,
            parent_id=data.parent_id,
        )
        return Resp.OK(data=DepartmentResponse(**dept.to_dict()).model_dump())
    except ValueError as e:
        return Resp.BadRequest(message=str(e))

# 2. 服务层 - org_service.py
def create_dept(self, org_id, name, code=None, parent_id=None, **kwargs):
    org = self.org_model.get(org_id)
    if not org:
        raise ValueError(f"组织不存在: {org_id}")
    
    if code:
        self.dept_model.validate_code_unique(org_id=org_id, code=code)
    
    level = 1
    if parent_id:
        parent = self.dept_model.validate_parent(parent_id=parent_id, org_id=org_id)
        level = parent.level + 1
    
    # 创建实体，先不提交
    dept = self.dept_model(org_id=org_id, name=name, code=code, 
                           parent_id=parent_id, level=level, **kwargs)
    dept.save()
    dept.update_path_and_level()
    # 所有操作完成后统一提交
    dept.save(commit=True)
    
    return dept

# 3. 领域模型 - department.py
@classmethod
def validate_code_unique(cls, org_id, code, exclude_id=None):
    if not code:
        return
    query = cls.query.filter_by(org_id=org_id, code=code)
    if exclude_id:
        query = query.filter(cls.id != exclude_id)
    if query.first():
        raise ValueError(f"部门编码已存在: {code}")

@classmethod
def validate_parent(cls, parent_id, org_id):
    parent = cls.get(parent_id)
    if not parent:
        raise ValueError(f"父部门不存在: {parent_id}")
    if parent.org_id != org_id:
        raise ValueError("父部门不属于同一组织")
    return parent
```

### 完整的移动部门流程

```python
# 1. API 层
@router.post("/move")
async def move_department(dept_id: int, new_parent_id: int = None):
    try:
        dept = org_service.move_dept(dept_id=dept_id, new_parent_id=new_parent_id)
        return Resp.OK(data=DepartmentResponse(**dept.to_dict()).model_dump())
    except ValueError as e:
        return Resp.BadRequest(message=str(e))

# 2. 服务层
def move_dept(self, dept_id, new_parent_id):
    dept = self.dept_model.get(dept_id)
    if not dept:
        raise ValueError(f"部门不存在: {dept_id}")
    
    # 调用领域模型的移动方法（包含验证和级联更新）
    dept.move_to_parent(new_parent_id)
    
    # 先保存所有后代变更
    for descendant in dept.get_descendants():
        descendant.save()
    
    # 通过模型实例统一提交（推荐）
    dept.save(commit=True)
    
    return dept

# 3. 领域模型
def move_to_parent(self, new_parent_id):
    """移动到新的父部门（包含级联更新）"""
    self.validate_can_move_to(new_parent_id)
    self.move_to(new_parent_id)  # TreeMixin 方法

def validate_can_move_to(self, new_parent_id):
    if new_parent_id is None:
        return None
    
    if new_parent_id == self.id:
        raise ValueError("不能将部门移动到自己下面")
    
    new_parent = self.__class__.get(new_parent_id)
    if not new_parent:
        raise ValueError(f"目标父部门不存在: {new_parent_id}")
    
    if new_parent.org_id != self.org_id:
        raise ValueError("不能移动到其他组织的部门下")
    
    if self.is_ancestor_of(new_parent):
        raise ValueError("不能将部门移动到其子部门下")
    
    return new_parent
```

---

## 最佳实践

### 1. 验证方法命名规范

```python
# validate_xxx - 验证通过返回 None 或对象，失败抛出 ValueError
validate_code_unique(org_id, code)        # 验证编码唯一
validate_parent(parent_id, org_id)         # 验证父部门有效，返回父部门对象
validate_can_move_to(new_parent_id)        # 验证是否可移动
validate_can_delete(force=False)           # 验证是否可删除，返回检查结果
```

### 2. 错误消息清晰明确

```python
# 好的错误消息
raise ValueError(f"部门不存在: {dept_id}")
raise ValueError(f"部门编码已存在: {code}")
raise ValueError("父部门不属于同一组织")
raise ValueError("不能将部门移动到自己下面")
raise ValueError(f"部门下还有 {len(children)} 个子部门，请先删除或移动")

# 避免模糊的错误消息
raise ValueError("无效的操作")  # 不好，不清楚是什么无效
raise ValueError("错误")  # 不好，没有任何信息
```

### 3. 测试简单直接

```python
def test_create_dept_wrong_org_fails(self, service):
    """测试在不同组织下创建子部门失败"""
    org1 = service.create_org(name="公司A", code="A001")
    org2 = service.create_org(name="公司B", code="B001")
    parent = service.create_dept(org_id=org1.id, name="技术部")
    
    with pytest.raises(ValueError, match="不属于同一组织"):
        service.create_dept(org_id=org2.id, name="后端组", parent_id=parent.id)

def test_move_dept_to_child_fails(self, service):
    """测试移动部门到子部门失败"""
    org = service.create_org(name="测试公司", code="TEST")
    parent = service.create_dept(org_id=org.id, name="技术部")
    child = service.create_dept(org_id=org.id, name="后端组", parent_id=parent.id)
    
    with pytest.raises(ValueError, match="子部门"):
        service.move_dept(parent.id, child.id)
```

### 4. 服务层事务管理（推荐 @transactional）

> ⚠️ **重要**：服务层推荐使用 `@transactional` 装饰器自动管理事务。

```python
from yweb.orm import transaction_manager as tm

# ✅ 推荐：使用 @transactional 装饰器
class DepartmentService:
    @tm.transactional()
    def remove_from_dept(self, employee_id: int, dept_id: int):
        employee = self.employee_model.get(employee_id)
        
        # 批量删除操作
        self.emp_dept_rel_model.query.filter(...).delete()
        
        if employee.primary_dept_id == dept_id:
            employee.primary_dept_id = None
        
        employee.save()  # 不需要 commit=True，事务管理器自动提交

# 简单场景：不使用装饰器时，通过 save(commit=True) 提交
def update_dept(self, dept_id: int, **kwargs):
    dept = self.dept_model.get(dept_id)
    dept.update(**kwargs)
    dept.save(commit=True)
```

**@transactional 优势**：
- 自动提交/回滚
- 支持嵌套事务（Savepoint）
- 内部方法的 `commit=True` 会被自动抑制

**内部方法规范**：辅助方法不应自行提交，由调用方或事务管理器统一处理。

---

## 反模式（避免）

### 1. 过度设计异常类

```python
# ❌ 错误：为每种错误定义一个异常类
class DepartmentNotFoundException(Exception): ...
class DepartmentCodeExistsException(Exception): ...
class DepartmentCircularReferenceException(Exception): ...
# 结果：大量异常类，维护成本高
```

```python
# ✅ 正确：直接使用 ValueError
raise ValueError(f"部门不存在: {dept_id}")
raise ValueError(f"部门编码已存在: {code}")
raise ValueError("不能将部门移动到其子部门下")
```

### 2. API 层包含业务逻辑

```python
# ❌ 错误：API 层知道太多业务细节
@router.post("/move")
async def move_department(dept_id: int, new_parent_id: int):
    dept = dept_model.get(dept_id)
    
    # 这些业务规则不应该在 API 层
    if new_parent_id == dept_id:
        return Resp.BadRequest(message="不能移动到自己下面")
    
    new_parent = dept_model.get(new_parent_id)
    if new_parent.org_id != dept.org_id:
        return Resp.BadRequest(message="不能跨组织移动")
    
    ancestors = new_parent.get_ancestors()
    if any(a.id == dept_id for a in ancestors):
        return Resp.BadRequest(message="不能移动到子部门下")
    
    # ... 更多业务逻辑
```

```python
# ✅ 正确：API 层只调用服务
@router.post("/move")
async def move_department(dept_id: int, new_parent_id: int):
    try:
        dept = org_service.move_dept(dept_id, new_parent_id)
        return Resp.OK(data=DepartmentResponse(**dept.to_dict()).model_dump())
    except ValueError as e:
        return Resp.BadRequest(message=str(e))
```

### 3. 领域模型使用框架异常类

```python
# ❌ 错误：领域模型使用框架定义的异常类
from yweb.exceptions import Err

def validate_code_unique(self, code):
    if self.query.filter_by(code=code).first():
        raise Err.conflict(f"编码已存在: {code}")  # 依赖框架异常
```

```python
# ✅ 正确：领域模型使用标准 ValueError
def validate_code_unique(self, code):
    if self.query.filter_by(code=code).first():
        raise ValueError(f"部门编码已存在: {code}")  # 标准异常
```

**说明**：虽然我们采用 Active Record 模式，领域模型可以使用 ORM 的数据访问能力（如 `query`、`save`），但异常应该使用 Python 标准的 `ValueError`，避免依赖框架自定义的异常类。

### 4. 使用传统 ForeignKey 定义关系

```python
# ❌ 错误：使用传统 ForeignKey，没有级联删除功能
class Employee(BaseModel):
    department_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("department.id"),  # ❌ 没有 on_delete 配置
        nullable=True,
    )
```

```python
# ✅ 正确：使用 fields.* API，支持级联软删除
class Employee(BaseModel):
    department = fields.ManyToOne(
        Department,
        on_delete=fields.SET_NULL,  # ✅ 配置级联行为
        nullable=True,
    )
```

**说明**：框架的 `fields.*` API 提供了级联软删除功能，当父记录被删除时，可自动处理子记录（软删除、置 NULL、解除关联等）。传统 `ForeignKey` 方式无法使用此功能。

> **例外情况**：框架内部（如 `setup_org_relationships()`）在运行时动态添加关系时，会使用原生 `relationship()`，此时必须使用 `back_populates` 双向绑定。业务代码无需关注此场景。

---

## 总结

### 核心要点

1. **Active Record + DDD 思想** - 务实组合，避免过度设计
2. **富领域模型** - 业务规则封装在模型中，模型具备数据访问能力
3. **使用 ValueError** - 简单直接，Python 标准
4. **统一通过服务层** - 保持调用路径一致，简单查询可绕过
5. **事务自动管理** - 使用 `@transactional` 装饰器，自动提交/回滚
6. **关系使用 fields.* API** - 支持级联软删除，自动处理关联数据

### 检查清单

- [ ] 领域模型是否只使用 `ValueError`？
- [ ] **关系是否使用 `fields.*` API 定义**（而非传统 ForeignKey）？
- [ ] **是否配置了正确的 `on_delete` 参数**（DELETE/SET_NULL/UNLINK/PROTECT）？
- [ ] 涉及跨实体操作是否通过服务层？
- [ ] 服务层方法是否使用 `@transactional` 装饰器？
- [ ] 内部辅助方法是否不自行提交（由事务管理器统一处理）？
- [ ] API 层是否只有简单的 `except ValueError` 处理？
- [ ] 错误消息是否清晰明确？

---

*本文档基于 yweb 框架 organization 模块的重构实践编写。*
