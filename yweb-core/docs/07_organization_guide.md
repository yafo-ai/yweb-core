# 组织管理模块使用指南

本指南详细介绍如何使用 YWeb 的组织管理模块（Organization Module）。

## 30秒快速入门

在 `main.py` 中添加以下代码，即可启用完整的组织架构功能（包含 26 个 API 接口）：

```python
from fastapi import FastAPI
from yweb.organization import setup_organization

app = FastAPI()

org = setup_organization(
    app=app,
    api_prefix="/api/v1",
)
```

就这样！无需创建任何额外文件，即可获得完整的组织管理 API。

> 如需认证保护，使用 `setup_auth(User)` 创建认证依赖后添加 `dependencies` 参数，详见下方 [添加认证保护](#级别1零配置快速启用推荐新项目)。
> 如需将员工关联到用户账号等自定义扩展，请参阅下方 [级别2：轻量自定义](#级别2轻量自定义通过-mixin)。

---

## 概述

组织管理模块提供了一套完整的组织架构管理功能，支持：

- **多组织管理**：支持多个独立组织
- **树形部门结构**：部门支持无限层级的父子关系
- **员工多归属**：员工可属于多个组织、多个部门
- **主归属设置**：员工有一个主组织和主部门
- **部门负责人**：每个部门可设置多个负责人和一个主负责人
- **外部系统同步**：支持企业微信、飞书、钉钉等外部系统数据同步

## 快速开始

组织管理模块提供三种使用级别，按需选择：

| 级别 | 代码量 | 灵活性 | 适用场景 |
|------|--------|--------|----------|
| 级别1 | ~5行 | 低 | 快速原型、零自定义 |
| 级别2 | ~15行 | 中 | 需要少量扩展字段 |
| 级别3 | ~80行 | 高 | 复杂定制需求 |

### 级别1：零配置快速启用（推荐新项目）

**方式A：一站式设置（最简洁，推荐）**

```python
# main.py
from fastapi import FastAPI
from yweb.organization import setup_organization

app = FastAPI()

org = setup_organization(
    app=app,
    api_prefix="/api/v1",
    tags=["组织架构"],
)
```

`setup_organization()` 会自动完成以下步骤：

1. 创建所有模型（Organization, Department, Employee 等）
2. 创建服务实例（org_service）并注入到 API 路由
3. 创建完整的 CRUD 路由（包括组织/部门/员工关联操作）
4. 将路由挂载到 FastAPI 应用

返回的 `org` 对象包含所有模型、枚举和服务入口，详见 [OrgModels 返回对象](#orgmodels-返回对象)。

> **添加认证保护**（推荐生产环境使用）：
> ```python
> from fastapi import Depends
> from yweb.auth import AbstractUser, setup_auth
> 
> # 项目中定义的用户模型（继承 AbstractUser）
> class User(AbstractUser):
>     __tablename__ = "sys_user"
> 
> auth = setup_auth(User)  # 一行完成认证设置
> 
> org = setup_organization(
>     app=app,
>     api_prefix="/api/v1",
>     dependencies=[Depends(auth.get_current_user)],  # 所有接口需登录访问
> )
> ```
> **关于用户模型**：
> - **推荐**：继承 `AbstractUser`，内置 `username`、`password_hash`、`email`、`phone`、`is_active`、`last_login_at` 等字段和常用查询方法（`get_by_username()` 等）
> - **自定义**：如果不继承 `AbstractUser`，你的 User 模型必须满足 `setup_auth()` 的最低要求：继承 `CoreModel`（提供 `.get(id)` 方法）且包含 `is_active` 布尔字段
>
> 自动从 `settings.jwt` 创建 JWT 管理器，并生成带缓存的认证依赖，详见 [认证指南](06_auth_guide.md)。

**方式B：分步设置（更灵活）**

适用于需要在创建模型和挂载路由之间插入自定义逻辑的场景（如修改模型、注册事件等）：

```python
from yweb.organization import create_org_models, create_org_router

# 1. 创建所有模型（"sys_" 自定义所有表的前缀）
org = create_org_models(table_prefix="sys_")

# 2. 在此处可插入自定义逻辑...

# 3. 创建 API 路由（as_dict() 将所有模型解包传入）
router = create_org_router(
    **org.as_dict(),
    prefix="/api/v1/org",
    tags=["组织架构"],
)

# 4. 挂载路由
app.include_router(router)
```

**方式C：使用 mount_routes()（与 auth 模块风格一致）**

`OrgModels` 对象提供了 `mount_routes()` 方法，与 `auth.mount_routes()` 风格保持一致：

```python
from yweb.organization import create_org_models

# 1. 创建所有模型
org = create_org_models(table_prefix="sys_")

# 2. 在此处可插入自定义逻辑...

# 3. 一行代码挂载路由
org.mount_routes(
    app,
    prefix="/api/v1/org",
    tags=["组织架构"],
    dependencies=[Depends(auth.get_current_user)],  # 可选：权限控制
)
```

`mount_routes()` 方法签名：

```python
def mount_routes(
    self,
    app,                              # FastAPI 应用实例
    prefix: str = "/api/org",         # API 路由前缀
    tags: list = None,                # OpenAPI 标签
    dependencies: list = None,        # 路由依赖（如权限检查）
    tree_node_builder=None,           # 自定义部门树节点构建函数
    employee_response_builder=None,   # 自定义员工响应构建函数
):
```

### OrgModels 返回对象

`create_org_models()` 和 `setup_organization()` 返回的 `OrgModels` 对象包含：

```python
org = create_org_models()

# 模型类
org.Organization        # 组织模型
org.Department          # 部门模型
org.Employee            # 员工模型
org.EmployeeOrgRel      # 员工-组织关联
org.EmployeeDeptRel     # 员工-部门关联
org.DepartmentLeader    # 部门负责人

# 枚举（便捷访问，无需单独导入）
org.ExternalSource      # 外部来源枚举
org.EmployeeStatus      # 雇佣状态枚举（员工-组织关系状态）
org.AccountStatus       # 账号状态枚举（员工系统账号状态）
org.Gender              # 性别枚举
org.SyncStatus          # 同步状态枚举

# 服务（单例模式）
org.get_org_service()   # 获取/创建服务实例

# 工具方法
org.as_dict()           # 返回所有模型的字典，用于 create_org_router(**org.as_dict())
```

### 级别2：轻量自定义（通过 Mixin）

使用 Mixin 添加自定义字段（如员工关联用户账号）。框架通过 MRO 扫描自动识别 Mixin 中的关系字段（`fields.OneToOne` / `fields.ManyToOne` / `fields.ManyToMany`），无需额外配置：

```python
from fastapi import Depends
from yweb.auth import setup_auth
from yweb.organization import setup_organization
from yweb.orm import fields
from app.domain.auth.model.user import User

# 认证设置
auth = setup_auth(User)

# 员工关联用户账号
class EmployeeUserMixin:
    """fields.OneToOne 自动创建：
    - user_id 列（外键）
    - user relationship（正向关系）
    - User.employee backref（反向关系，自动生成单数名称）
    """
    user = fields.OneToOne(
        User, 
        on_delete=fields.DO_NOTHING,  # 员工删除时不影响用户
        nullable=True,                # 允许员工不关联用户
    )

# 一站式设置
org = setup_organization(
    app=app,
    api_prefix="/api/v1",
    employee_mixin=EmployeeUserMixin,
    dependencies=[Depends(auth.get_current_user)],
)

# Employee 现在有 user 和 user_id 属性
emp = org.Employee.query.first()
print(emp.user)        # 关联的用户对象
print(emp.user_id)     # 关联的用户ID

# User 现在有 employee 反向引用
user = User.query.first()
print(user.employee)   # 关联的员工对象
```

> **技术说明**：Mixin 中定义的 `fields.*` 关系字段会通过 `__init_subclass__` 的 MRO 扫描被自动发现。框架在动态创建模型类时，会将 Mixin 中的关系配置正确传递给 `process_relationship_fields` 处理，确保外键列和 relationship 都被正确创建。

**支持的 Mixin 参数**：

| 参数 | 说明 |
|------|------|
| `organization_mixin` | 组织模型的 Mixin |
| `department_mixin` | 部门模型的 Mixin |
| `employee_mixin` | 员工模型的 Mixin |
| `emp_org_rel_mixin` | 员工-组织关联的 Mixin |
| `emp_dept_rel_mixin` | 员工-部门关联的 Mixin |
| `dept_leader_mixin` | 部门负责人的 Mixin |

**也可以使用 customizer 回调添加自定义逻辑**：

```python
def customize_employee(cls):
    """自定义员工模型"""
    cls.DEFAULT_AVATAR = "/static/default-avatar.png"
    
    def get_full_info(self):
        return f"{self.name} ({self.mobile})"
    cls.get_full_info = get_full_info

org = create_org_models(
    employee_customizer=customize_employee,
)
```

**支持的 customizer 参数**：

| 参数 | 说明 |
|------|------|
| `organization_customizer` | 组织模型的自定义回调 |
| `department_customizer` | 部门模型的自定义回调 |
| `employee_customizer` | 员工模型的自定义回调 |

### 级别3：完全自定义（继承抽象类）

需要完全控制时，继承抽象模型：

```python
from yweb.organization import (
    AbstractOrganization,
    AbstractDepartment,
    AbstractEmployee,
    AbstractEmployeeOrgRel,
    AbstractEmployeeDeptRel,
    AbstractDepartmentLeader,
    setup_org_relationships,  # 辅助函数
)


# 组织模型（表名自动生成为 organization）
class Organization(AbstractOrganization):
    pass


# 部门模型
class Department(AbstractDepartment):
    __org_tablename__ = "organization"
    __employee_tablename__ = "employee"


# 员工模型
class Employee(AbstractEmployee):
    __org_tablename__ = "organization"
    __dept_tablename__ = "department"


# 员工-组织关联模型
class EmployeeOrgRel(AbstractEmployeeOrgRel):
    __employee_tablename__ = "employee"
    __org_tablename__ = "organization"


# 员工-部门关联模型
class EmployeeDeptRel(AbstractEmployeeDeptRel):
    __employee_tablename__ = "employee"
    __dept_tablename__ = "department"


# 部门负责人关联模型
class DepartmentLeader(AbstractDepartmentLeader):
    __dept_tablename__ = "department"
    __employee_tablename__ = "employee"


# 使用辅助函数自动设置所有 relationship（推荐）
setup_org_relationships(
    Organization, Department, Employee,
    EmployeeOrgRel, EmployeeDeptRel, DepartmentLeader
)
```

> **提示**：`setup_org_relationships()` 会自动为各模型添加 `organization`、`parent`、`children`、`employee` 等 relationship 属性，同时配置级联软删除策略，无需手动定义。

如果需要自定义表名前缀，可以手动指定 `__tablename__`：

```python
class Organization(AbstractOrganization):
    __tablename__ = "sys_organization"  # 自定义表名
```

### 服务层使用

**方式1：使用单例服务（推荐，级别1/2适用）**

```python
# OrgModels 内置单例服务
org = create_org_models()

# 获取服务实例（单例模式，多次调用返回同一实例）
service = org.get_org_service()

# 使用服务
org_entity = service.create_org(name="某某公司", code="COMPANY001")
dept = service.create_dept(org_id=org_entity.id, name="技术部")
emp = service.create_employee(name="张三", mobile="13800138000")
```

**方式2：使用工厂函数创建服务**

```python
from yweb.organization import create_org_service

# 创建独立的服务实例
service = create_org_service(org)  # org 是 create_org_models() 的返回值
```

**方式3：继承服务类（级别3适用）**

```python
from yweb.organization import BaseOrganizationService

class OrganizationService(BaseOrganizationService):
    org_model = Organization
    dept_model = Department
    employee_model = Employee
    emp_org_rel_model = EmployeeOrgRel
    emp_dept_rel_model = EmployeeDeptRel
    dept_leader_model = DepartmentLeader
```

### 服务使用示例

```python
# 创建服务实例
org_service = OrganizationService()

# 创建组织
org = org_service.create_org(name="某某科技有限公司", code="TECH001")

# 创建部门
tech_dept = org_service.create_dept(org_id=org.id, name="技术部")
dev_team = org_service.create_dept(org_id=org.id, name="研发组", parent_id=tech_dept.id)

# 创建员工
emp = org_service.create_employee(name="张三", mobile="13800138000")

# 添加员工到组织
org_service.add_employee_to_org(
    employee_id=emp.id,
    org_id=org.id,
    emp_no="EMP001",
    position="高级工程师",
    set_as_primary=True  # 设为主组织
)

# 添加员工到部门
org_service.add_employee_to_dept(
    employee_id=emp.id,
    dept_id=dev_team.id,
    set_as_primary=True  # 设为主部门
)

# 设置部门负责人
org_service.add_dept_leader(
    dept_id=dev_team.id,
    employee_id=emp.id,
    set_as_primary=True  # 设为主负责人
)
```

## 数据模型说明

### 实体关系图

```
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│ Organization │──1:N──│  Department  │──M:N──│   Employee   │
└──────────────┘       └──────────────┘       └──────────────┘
                              │                      │
                              │                      │
                       ┌──────┴──────┐        ┌──────┴──────┐
                       │ 自关联(树形) │        │ 多组织多部门 │
                       └─────────────┘        └─────────────┘
```

### 核心模型字段

#### Organization（组织）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | PK | 主键 |
| name | String | 组织名称 |
| code | String | 组织编码 |
| external_source | String | 外部来源（none/wechat_work/feishu/dingtalk） |
| external_corp_id | String | 外部企业ID |
| external_config | Text(JSON) | 外部系统配置 |

#### Department（部门）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | PK | 主键 |
| org_id | FK | 所属组织ID |
| parent_id | FK | 父部门ID（自关联） |
| name | String | 部门名称 |
| path | String | 路径（如 /1/2/3/） |
| level | Integer | 层级（1=根部门） |
| sort_order | Integer | 排序序号 |
| primary_leader_id | FK | 主负责人ID |
| external_dept_id | String | 外部部门ID |

#### Employee（员工）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | PK | 主键 |
| name | String | 姓名 |
| mobile | String | 手机号 |
| email | String | 邮箱 |
| avatar | String | 头像URL |
| gender | Integer | 性别（0-未知,1-男,2-女） |
| is_senior | Boolean | 是否高管 |
| primary_org_id | FK | 主组织ID |
| primary_dept_id | FK | 主部门ID |

#### EmployeeOrgRel（员工-组织关联）

| 字段 | 类型 | 说明 |
|------|------|------|
| employee_id | FK | 员工ID |
| org_id | FK | 组织ID |
| emp_no | String | 工号（组织内） |
| position | String | 职位 |
| status | Integer | 状态（1-在职,2-离职...） |
| joined_at | DateTime | 入职日期 |
| external_user_id | String | 外部用户ID |

#### EmployeeDeptRel（员工-部门关联）

| 字段 | 类型 | 说明 |
|------|------|------|
| employee_id | FK | 员工ID |
| dept_id | FK | 部门ID |
| sort_order | Integer | 排序序号 |
| joined_at | DateTime | 加入时间 |

#### DepartmentLeader（部门负责人）

| 字段 | 类型 | 说明 |
|------|------|------|
| dept_id | FK | 部门ID |
| employee_id | FK | 员工ID |
| sort_order | Integer | 排序序号 |

## 服务方法详解

### 组织管理

```python
# 创建组织
org = org_service.create_org(name="公司名称", code="CODE001")

# 更新组织
org_service.update_org(org_id=1, name="新名称")

# 删除组织（有部门或员工时会报错）
org_service.delete_org(org_id=1)

# 强制删除（即使有部门或员工）
org_service.delete_org(org_id=1, force=True)

# 获取组织
org = org_service.get_org(org_id=1)
org = org_service.get_org_by_code("CODE001")
orgs = org_service.list_orgs()
```

### 部门管理

```python
# 创建部门
dept = org_service.create_dept(org_id=1, name="技术部")

# 创建子部门
sub_dept = org_service.create_dept(org_id=1, name="研发组", parent_id=dept.id)

# 更新部门
org_service.update_dept(dept_id=1, name="新名称")

# 移动部门（更换父部门）
org_service.move_dept(dept_id=2, new_parent_id=3)

# 删除部门（有员工时会报错）
org_service.delete_dept(dept_id=1)

# 获取部门树
tree = org_service.get_dept_tree(org_id=1)

# 获取根部门
roots = org_service.get_root_depts(org_id=1)
```

### 员工管理

```python
# 创建员工
emp = org_service.create_employee(
    name="张三",
    mobile="13800138000",
    email="zhangsan@example.com"
)

# 更新员工
org_service.update_employee(employee_id=1, name="李四")

# 删除员工（同时清理所有关联）
org_service.delete_employee(employee_id=1)
```

### 员工-组织关联

```python
# 添加员工到组织
rel = org_service.add_employee_to_org(
    employee_id=1,
    org_id=1,
    emp_no="EMP001",
    position="工程师",
    set_as_primary=True  # 设为主组织
)

# 从组织移除员工（同时移除该组织下的部门关联）
org_service.remove_employee_from_org(employee_id=1, org_id=1)

# 获取员工所属的所有组织
rels = org_service.get_employee_orgs(employee_id=1)

# 获取组织下的所有员工
rels = org_service.get_org_employees(org_id=1)
```

### 员工-部门关联

```python
# 添加员工到部门（员工必须已在该部门所属的组织中）
rel = org_service.add_employee_to_dept(
    employee_id=1,
    dept_id=1,
    set_as_primary=True  # 设为主部门
)

# 从部门移除员工
org_service.remove_employee_from_dept(employee_id=1, dept_id=1)

# 获取员工所属的所有部门
rels = org_service.get_employee_depts(employee_id=1)

# 获取部门下的所有员工
rels = org_service.get_dept_employees(dept_id=1)
```

### 主组织/主部门设置

```python
# 设置主组织（员工必须已在该组织中）
org_service.set_primary_org(employee_id=1, org_id=2)

# 设置主部门（员工必须已在该部门中，且部门必须属于主组织）
org_service.set_primary_dept(employee_id=1, dept_id=3)
```

### 部门负责人管理

```python
# 添加部门负责人（员工必须已在该部门中）
leader = org_service.add_dept_leader(
    dept_id=1,
    employee_id=2,
    set_as_primary=True  # 设为主负责人
)

# 移除部门负责人
org_service.remove_dept_leader(dept_id=1, employee_id=2)

# 设置主负责人（必须已是负责人）
org_service.set_primary_leader(dept_id=1, employee_id=3)

# 获取部门的所有负责人
leaders = org_service.get_dept_leaders(dept_id=1)

# 获取主负责人
primary_leader = org_service.get_primary_leader(dept_id=1)
```

## 树形结构操作

部门模型继承了 `TreeMixin`，提供丰富的树形操作方法：

```python
# 获取直接子部门
children = dept.get_children()

# 获取所有子孙部门
descendants = dept.get_descendants()

# 获取所有祖先部门
ancestors = dept.get_ancestors()

# 获取父部门
parent = dept.get_parent()

# 获取兄弟部门
siblings = dept.get_siblings()

# 获取根部门
root = dept.get_root()

# 判断是否为根部门
is_root = dept.is_root()

# 判断是否为叶子部门（无子部门）
is_leaf = dept.is_leaf()

# 判断是否为某部门的祖先
is_ancestor = dept1.is_ancestor_of(dept2)

# 移动部门到新的父部门下
dept.move_to(new_parent_id=3)

# 获取完整的部门名称（包含所有祖先）
full_name = dept.get_full_name()  # 返回 "总公司 > 技术部 > 研发组"
```

## 外部系统同步

### 1. 创建同步服务

继承 `AbstractSyncService` 实现具体的同步逻辑：

```python
from yweb.organization import AbstractSyncService, ExternalSource
from typing import List, Dict, Any, Optional

class WechatWorkSyncService(AbstractSyncService):
    """企业微信同步服务"""
    
    external_source = ExternalSource.WECHAT_WORK
    
    # 配置模型类
    org_model = Organization
    dept_model = Department
    employee_model = Employee
    emp_org_rel_model = EmployeeOrgRel
    emp_dept_rel_model = EmployeeDeptRel
    
    def fetch_organization_info(self, org) -> Optional[Dict[str, Any]]:
        """从企业微信获取组织信息"""
        # 调用企业微信 API
        corp_id = org.external_corp_id
        # ... 实现 API 调用
        return {"name": "公司名称"}
    
    def fetch_departments(self, org) -> List[Dict[str, Any]]:
        """从企业微信获取部门列表"""
        # 调用企业微信 API
        # 返回格式示例：
        return [
            {
                "external_dept_id": "1",
                "external_parent_id": None,
                "name": "总公司",
                "sort_order": 0
            },
            {
                "external_dept_id": "2",
                "external_parent_id": "1",
                "name": "技术部",
                "sort_order": 1
            }
        ]
    
    def fetch_employees(self, org) -> List[Dict[str, Any]]:
        """从企业微信获取员工列表"""
        # 调用企业微信 API
        # 返回格式示例：
        return [
            {
                "external_user_id": "zhangsan",
                "name": "张三",
                "mobile": "13800138000",
                "email": "zhangsan@example.com",
                "department_ids": ["1", "2"],  # 所属部门的外部ID
                "position": "工程师"
            }
        ]
```

### 2. 执行同步

```python
# 创建同步服务
sync_service = WechatWorkSyncService()

# 执行同步
result = sync_service.sync_from_external(org_id=1)

# 查看同步结果
print(f"同步成功: {result.success}")
print(f"创建: {result.created_count}")
print(f"更新: {result.updated_count}")
print(f"删除: {result.deleted_count}")
print(f"耗时: {result.duration_seconds}秒")

if result.errors:
    print("错误信息:")
    for error in result.errors:
        print(f"  - {error}")
```

### 3. 安全同步机制

`BaseSyncService` 内置了多项安全机制，子类自动继承，无需额外代码：

#### 预拉取缓存

`sync_from_external()` 在同步开始时一次性调用 `fetch_departments()` 和 `fetch_employees()`，结果缓存在 `self._cached_departments` / `self._cached_employees` 中。后续的 `sync_departments()`、`sync_employees()`、`sync_employee_dept_relations()` 自动使用缓存数据，避免重复 API 调用和数据不一致窗口。

#### 安全阈值

防止外部 API 故障（返回空列表/部分数据）导致误删本地数据：

- 本地 > 10 条且外部返回 0 条 → 中止同步（疑似 API 故障）
- 本地 > 20 条且外部 < 本地 30% → 中止同步（疑似数据异常）
- 首次同步（本地 0 条）→ 跳过检查

子类可覆写 `_check_safety_threshold()` 调整阈值。

#### 安全删除策略

基于 `external_dept_id` / `external_user_id` 映射关系逐条 upsert，本地多出的数据不物理删除：

| 数据类型 | 本地有、外部没有时的处理 |
|---------|----------------------|
| 部门 | 软删除（设置 `deleted_at`，数据保留可恢复） |
| 员工 | 标记离职（`EmployeeOrgRel.status = RESIGNED`），清理部门关联，保留 Employee 和 User 记录 |

如果员工重新出现在外部系统，全量同步会自动恢复 `EmployeeOrgRel.status`。

#### 生命周期钩子

员工被标记为离职时，框架会调用 `_on_employee_mark_resigned(employee, rel)` 钩子。子类可覆写此方法执行额外操作：

```python
class WechatWorkSyncService(BaseSyncService):
    # ...
    
    def _on_employee_mark_resigned(self, employee, rel):
        """员工离职时禁用关联的 User 账号"""
        user_id = getattr(employee, 'user_id', None)
        if user_id:
            user = User.get(user_id)
            if user and user.is_active:
                user.is_active = False
                user.save(commit=True)
```

### 支持的外部系统

参见上方「枚举类型 - 外部来源」。

## 枚举类型

枚举可以从 `yweb.organization` 导入，也可以从 `OrgModels` 对象直接访问：

```python
# 方式1：标准导入
from yweb.organization import EmployeeStatus, AccountStatus, Gender, ExternalSource, SyncStatus

# 方式2：从 OrgModels 便捷访问（推荐）
org = create_org_models()
EmployeeStatus = org.EmployeeStatus
AccountStatus = org.AccountStatus
Gender = org.Gender
```

### 雇佣状态（EmployeeStatus）

雇佣状态描述员工与某个组织的雇佣关系。数值按入职生命周期设计：

```python
EmployeeStatus.RESIGNED    # -1 - 离职（终态）
EmployeeStatus.SUSPENDED   #  0 - 停职（冻结态）
EmployeeStatus.PENDING     #  1 - 待入职（起点）
EmployeeStatus.PROBATION   #  2 - 试用期
EmployeeStatus.ACTIVE      #  3 - 在职

# 便捷判断
status >= 0   # → 未离职
status > 0    # → 活跃状态
status >= 2   # → 正式员工（试用期+在职）
```

### 账号状态（AccountStatus）

账号状态从关联的 `User.is_active` 动态推导，**不存储在员工表中**：

```python
AccountStatus.DISABLED       # -1 - 已禁用（user.is_active = False）
AccountStatus.NOT_ACTIVATED  #  0 - 未激活（employee.user_id IS NULL）
AccountStatus.ACTIVATED      #  1 - 已激活（user.is_active = True）
```

推导规则（需通过 `employee_mixin` 配置 user 关联）：

```
employee.user_id 为空   → NOT_ACTIVATED (0)  无账号
user.is_active = True   → ACTIVATED (1)      可登录
user.is_active = False  → DISABLED (-1)      已禁用
未配置 user 关联        → 不提供账号状态功能
```

> **设计理由**：账号状态直接由 `User.is_active` 决定，避免两张表状态不一致。
> `AccountStatus` 枚举仅作为 API 参数和前端展示的常量定义。

### 性别

```python
Gender.UNKNOWN  # 0 - 未知
Gender.MALE     # 1 - 男
Gender.FEMALE   # 2 - 女
```

### 外部来源

```python
ExternalSource.NONE          # 本地创建
ExternalSource.WECHAT_WORK   # 企业微信
ExternalSource.FEISHU        # 飞书
ExternalSource.DINGTALK      # 钉钉
ExternalSource.CUSTOM        # 自定义
```

### 同步状态

```python
SyncStatus.NONE       # 未同步
SyncStatus.SYNCING    # 同步中
SyncStatus.SUCCESS    # 同步成功
SyncStatus.FAILED     # 同步失败
```

## 业务约束

模块内置了以下业务约束（由 Service 层和级联软删除保证）：

| 约束 | 说明 |
|------|------|
| 员工-组织唯一 | 同一员工不能重复加入同一组织 |
| 员工-部门唯一 | 同一员工不能重复加入同一部门 |
| 部门负责人唯一 | 同一员工不能重复成为同一部门的负责人 |
| 主部门属于主组织 | 员工的主部门必须属于其主组织 |
| 加入部门前需加入组织 | 员工必须先加入组织，才能加入该组织下的部门 |
| 成为负责人前需在部门中 | 员工必须先在部门中，才能成为该部门的负责人 |
| 删除保护 | 有员工的部门禁止删除（PROTECT 策略） |
| 删除保护 | 有子部门的部门禁止删除（PROTECT 策略） |
| 删除保护 | 有部门或员工的组织禁止删除（PROTECT 策略） |
| 员工删除级联 | 员工删除时自动清理所有关联（DELETE 策略） |
| 主负责人置空 | 员工删除时自动将其主负责人引用置空（SET_NULL 策略） |

## 账号与雇佣状态联动

当员工通过 `employee_mixin` 关联了用户账号（`User` 模型）时，框架会自动维护雇佣状态与账号状态的联动关系。

> **前提**：这些联动仅影响"绑定了员工"的用户账号。独立用户（如管理员账号，未绑定任何员工）不受这些规则限制。

### 联动规则总览

```
                      ┌──────────────────────┐
                      │    雇佣状态变更       │
                      │ update_emp_org_status │
                      └──────────┬───────────┘
                                 │
                    ┌────────────▼────────────┐
                    │ 新状态 <= 0 (离职/停职)？│
                    └────────────┬────────────┘
                           是    │
                    ┌────────────▼────────────┐
                    │ 所有组织都非活跃？       │
                    │ _has_any_active_org()    │
                    └────────────┬────────────┘
                           是    │
                    ┌────────────▼────────────┐
                    │ 自动禁用关联账号         │
                    │ user.is_active = False   │
                    └─────────────────────────┘
```

### 各操作的联动行为

| 操作 | 联动行为 | 说明 |
|------|---------|------|
| **修改雇佣状态→非活跃** | 自动禁用账号 | 当员工在所有组织中都变为非活跃（离职/停职），自动设置 `user.is_active = False` |
| **修改雇佣状态→活跃** | 不自动激活 | 需管理员手动激活账号，防止误操作 |
| **激活账号** | 校验雇佣状态 | 所有组织都非活跃的员工，不允许激活账号 |
| **禁用账号** | 直接禁用 | 管理员可随时手动禁用账号 |
| **创建账号** | 校验雇佣状态 | 所有组织都非活跃的员工（离职/停职），禁止创建账号 |
| **删除员工** | 自动禁用账号 | 删除前自动禁用关联的用户账号 |
| **从组织移除** | 检查并禁用 | 移除后若所有组织都不活跃，自动禁用账号 |

### 状态判断规则

雇佣状态按 `EmployeeStatus` 数值划分：

```
活跃状态（status > 0）：待入职(1)、试用期(2)、在职(3)
  → 允许创建账号、允许激活账号

非活跃状态（status <= 0）：停职(0)、离职(-1)
  → 禁止创建账号、禁止激活账号、自动禁用已有账号
```

判断维度是**所有组织关联**，而非单个组织。只有当员工在**所有组织**中都为非活跃状态时，才触发账号禁用。例如：

- 员工在 A 组织离职、B 组织在职 → 账号不受影响
- 员工在 A 组织离职、B 组织也离职 → 自动禁用账号

### 容错机制

- **未配置 user 关联**：所有联动逻辑通过 `hasattr(employee, 'user_id')` 做前置判断，未配置 Mixin 时静默跳过
- **关联用户不存在**：通过 relationship 加载失败时，自动回退到直接查询 User 模型
- **无组织关联**：无 `emp_org_rel_model` 时，`_has_any_active_org()` 返回 `False`

### 代码示例

```python
# 雇佣状态变更会自动联动账号
org_service.update_emp_org_status(
    employee_id=1, org_id=1, status=EmployeeStatus.RESIGNED  # -1
)
# → 如果员工在所有组织都非活跃，user.is_active 自动变为 False

# 手动修改账号状态（会校验雇佣状态）
org_service.update_account_status(
    employee_id=1, account_status=1  # 激活
)
# → 如果员工所有组织都非活跃，会抛出 ValueError

# 创建账号（会校验雇佣状态）
account_service.create_account_for_employee(employee_id=1)
# → 如果员工所有组织都非活跃，会抛出 ValueError

# 删除员工会自动禁用关联账号
org_service.delete_employee(employee_id=1)
# → user.is_active 自动变为 False，然后执行软删除
```

## API 路由

组织模块提供了内置的 API 路由，可以快速挂载完整的组织管理接口。

**路由风格**：使用动词风格路由，只使用 GET 和 POST 请求，适合传统项目。

### 方式1：一次性挂载全部路由（推荐）

```python
from fastapi import FastAPI, Depends
from yweb.organization import create_org_router
from yweb.permission import require_role

app = FastAPI()

# 创建并挂载组织管理路由
router = create_org_router(
    org_model=Organization,
    dept_model=Department,
    employee_model=Employee,
    emp_org_rel_model=EmployeeOrgRel,
    emp_dept_rel_model=EmployeeDeptRel,
    dept_leader_model=DepartmentLeader,
    prefix="/org",
    tags=["组织管理"],
    dependencies=[Depends(require_role("admin"))],  # 可选：添加权限控制
)
app.include_router(router, prefix="/api/v1")
```

这会自动生成以下路由（假设最终前缀为 `/api/v1/org`）：

**组织管理**

| 路由 | 方法 | 说明 |
|-----|------|------|
| `/list` | GET | 获取组织列表 |
| `/get` | GET | 获取组织详情（?org_id=1） |
| `/create` | POST | 创建组织 |
| `/update` | POST | 更新组织（?org_id=1） |
| `/delete` | POST | 删除组织（?org_id=1） |

**部门管理**

| 路由 | 方法 | 说明 |
|-----|------|------|
| `/dept/list` | GET | 获取部门列表（?org_id=1） |
| `/dept/tree` | GET | 获取部门树（?org_id=1） |
| `/dept/get` | GET | 获取部门详情（?dept_id=1） |
| `/dept/create` | POST | 创建部门 |
| `/dept/update` | POST | 更新部门（?dept_id=1） |
| `/dept/move` | POST | 移动部门（?dept_id=1&new_parent_id=2） |
| `/dept/delete` | POST | 删除部门（?dept_id=1） |
| `/dept/employees` | GET | 获取部门员工（?dept_id=1） |
| `/dept/add-leader` | POST | 添加部门负责人 |
| `/dept/remove-leader` | POST | 移除部门负责人 |

**员工管理**

| 路由 | 方法 | 说明 |
|-----|------|------|
| `/employee/list` | GET | 获取员工列表 |
| `/employee/get` | GET | 获取员工详情（?employee_id=1） |
| `/employee/create` | POST | 创建员工 |
| `/employee/update` | POST | 更新员工（?employee_id=1） |
| `/employee/delete` | POST | 删除员工（?employee_id=1） |
| `/employee/add-to-org` | POST | 员工加入组织 |
| `/employee/remove-from-org` | POST | 员工离开组织 |
| `/employee/set-primary-org` | POST | 设置主组织 |
| `/employee/add-to-dept` | POST | 员工加入部门 |
| `/employee/remove-from-dept` | POST | 员工离开部门 |
| `/employee/set-primary-dept` | POST | 设置主部门 |

**列表响应格式**

所有列表 API 返回统一的分页格式：

```json
{
    "code": 200,
    "data": {
        "items": [...],
        "total": 100,
        "page": 1,
        "page_size": 20
    }
}
```

### 方式2：按需挂载独立路由

```python
from yweb.organization import (
    create_organization_crud_router,
    create_department_crud_router,
    create_employee_crud_router,
)

# 只挂载需要的部分（组织 CRUD）
app.include_router(
    create_organization_crud_router(org_model=Organization),
    prefix="/api/admin/org",
    tags=["组织管理"]
)

# 部门 CRUD（需要传入更多模型以支持部门员工功能）
app.include_router(
    create_department_crud_router(
        dept_model=Department,
        org_model=Organization,
        employee_model=Employee,  # 可选，用于 /employees 接口
        emp_org_rel_model=EmployeeOrgRel,
        emp_dept_rel_model=EmployeeDeptRel,
        dept_leader_model=DepartmentLeader,
    ),
    prefix="/api/admin/dept",
    tags=["部门管理"]
)
```

### 扩展模型字段自动返回

框架支持在继承抽象模型时添加自定义字段，**扩展字段会自动出现在 API 响应中**。

```python
class Employee(AbstractEmployee):
    __tablename__ = "sys_employee"
    
    # 添加自定义字段
    id_card: Mapped[str] = mapped_column(String(18), nullable=True)
    work_years: Mapped[int] = mapped_column(Integer, default=0)
```

API 响应会自动包含扩展字段：

```json
{
    "code": 200,
    "data": {
        "id": 1,
        "name": "张三",
        "mobile": "13800138000",
        "id_card": "110101199001011234",
        "work_years": 5
    }
}
```

### 自定义响应构建

如果需要在响应中添加额外的计算字段，可以提供自定义构建函数：

```python
def my_employee_response_builder(employee, base_data: dict) -> dict:
    """自定义员工响应构建"""
    base_data["full_dept_path"] = employee.primary_dept.get_full_name() if employee.primary_dept else None
    base_data["avatar_url"] = f"https://cdn.example.com/{employee.avatar}" if employee.avatar else None
    return base_data

router = create_org_router(
    ...,
    employee_response_builder=my_employee_response_builder,
)
```

### include 参数：按需返回关联数据

API 支持 `include` 参数，按需返回关联数据，避免不必要的查询开销。

#### 支持的 API 和选项

| API | 支持的 include 选项 | 说明 |
|-----|-------------------|------|
| `GET /dept/tree` | `employee_count`, `full_name`, `primary_leader_name` | 部门树附加信息 |
| `GET /dept/get` | `employee_count`, `full_name`, `primary_leader_name` | 部门详情附加信息 |
| `GET /employee/list` | `org_name`, `dept_name` | 员工列表附加主组织/部门名 |

#### 使用示例

```bash
# 基础查询（不附加关联数据）
GET /api/v1/org/employee/list

# 附加主组织名称
GET /api/v1/org/employee/list?include=org_name

# 附加多个字段（逗号分隔）
GET /api/v1/org/employee/list?include=org_name,dept_name

# 部门树包含员工数量和负责人
GET /api/v1/org/dept/tree?org_id=1&include=employee_count,primary_leader_name
```

#### 响应示例

不带 `include`：

```json
{
    "id": 1,
    "name": "张三",
    "primary_org_id": 1,
    "primary_dept_id": 2
}
```

带 `include=org_name,dept_name`：

```json
{
    "id": 1,
    "name": "张三",
    "primary_org_id": 1,
    "primary_dept_id": 2,
    "primary_org_name": "总公司",
    "primary_dept_name": "技术部"
}
```

### 响应构建钩子：自定义响应数据

当需要在响应中添加自定义计算字段时，可以提供响应构建钩子函数。

#### 员工响应构建器

```python
def my_employee_response_builder(employee, base_data: dict) -> dict:
    """自定义员工响应构建
    
    Args:
        employee: 员工模型实例
        base_data: to_dict() 返回的基础数据
        
    Returns:
        修改后的响应数据
    """
    # 添加头像完整 URL
    if employee.avatar:
        base_data["avatar_url"] = f"https://cdn.example.com/{employee.avatar}"
    
    # 添加部门完整路径
    if employee.primary_dept:
        base_data["dept_full_path"] = employee.primary_dept.get_full_name()
    
    # 添加工龄显示
    if hasattr(employee, 'work_years'):
        base_data["work_years_display"] = f"{employee.work_years}年"
    
    return base_data

# 使用
router = create_org_router(
    ...,
    employee_response_builder=my_employee_response_builder,
)
```

#### 部门树节点构建器

```python
def my_tree_node_builder(dept, base_data: dict) -> dict:
    """自定义部门树节点构建
    
    Args:
        dept: 部门模型实例
        base_data: to_dict() 返回的基础数据
        
    Returns:
        树节点数据
    """
    node = {
        "id": base_data["id"],
        "name": base_data["name"],
        "parent_id": base_data["parent_id"],
        "level": base_data["level"],
        "children": [],  # 框架会自动填充
    }
    
    # 添加扩展字段（如部门预算）
    if hasattr(dept, 'budget'):
        node["budget"] = dept.budget
        node["budget_display"] = f"¥{dept.budget:,}"
    
    # 添加员工数量
    if hasattr(dept, 'employee_dept_rels'):
        node["employee_count"] = len(dept.employee_dept_rels)
    
    # 添加自定义标记
    node["is_root"] = dept.parent_id is None
    
    return node

# 使用
router = create_org_router(
    ...,
    tree_node_builder=my_tree_node_builder,
)
```

#### 注意事项

- 构建器接收模型实例和 `to_dict()` 返回的基础数据
- 修改 `base_data` 后返回，或返回全新的 dict
- 扩展字段通过 Schema 的 `extra="allow"` 配置自动通过

### 部门树 API

部门树 API 返回树形结构的部门数据，适合前端渲染组织架构。

#### 请求

```bash
GET /api/v1/org/dept/tree?org_id=1&include=employee_count,primary_leader_name
```

#### 响应结构

```json
{
    "code": 200,
    "data": [
        {
            "id": 1,
            "org_id": 1,
            "name": "技术部",
            "code": "TECH",
            "parent_id": null,
            "level": 1,
            "sort_order": 0,
            "employee_count": 50,
            "primary_leader_name": "张经理",
            "children": [
                {
                    "id": 2,
                    "org_id": 1,
                    "name": "前端组",
                    "code": "TECH-FE",
                    "parent_id": 1,
                    "level": 2,
                    "sort_order": 0,
                    "employee_count": 20,
                    "primary_leader_name": "李组长",
                    "children": []
                },
                {
                    "id": 3,
                    "org_id": 1,
                    "name": "后端组",
                    "code": "TECH-BE",
                    "parent_id": 1,
                    "level": 2,
                    "sort_order": 1,
                    "employee_count": 30,
                    "primary_leader_name": "王组长",
                    "children": []
                }
            ]
        },
        {
            "id": 4,
            "org_id": 1,
            "name": "销售部",
            "code": "SALES",
            "parent_id": null,
            "level": 1,
            "sort_order": 1,
            "employee_count": 25,
            "primary_leader_name": null,
            "children": []
        }
    ]
}
```

#### include 选项说明

| 选项 | 说明 |
|-----|------|
| `employee_count` | 部门员工数量（需要配置 `employee_dept_rels` relationship） |
| `full_name` | 部门完整路径名（如"总公司 > 技术部 > 前端组"） |
| `primary_leader_name` | 主负责人姓名（需要配置 `primary_leader` relationship） |

#### 扩展字段自动包含

如果你的部门模型添加了扩展字段，使用自定义 `tree_node_builder` 可以将其包含在树节点中：

```python
class Department(AbstractDepartment):
    __tablename__ = "sys_department"
    
    # 扩展字段
    budget: Mapped[int] = mapped_column(Integer, nullable=True, comment="部门预算")
    cost_center: Mapped[str] = mapped_column(String(50), nullable=True, comment="成本中心")

def my_tree_node_builder(dept, base_data: dict) -> dict:
    # 基础字段
    node = {
        "id": base_data["id"],
        "name": base_data["name"],
        "parent_id": base_data["parent_id"],
        "level": base_data["level"],
        "children": [],
    }
    
    # 保留所有扩展字段
    for key in ("budget", "cost_center"):
        if key in base_data:
            node[key] = base_data[key]
    
    return node
```

---

## 在 FastAPI 中使用

### 方式3：完全自定义 API

```python
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel as PydanticModel
from typing import Optional, List
from yweb import OK, BadRequest, NotFound
from yweb.orm import init_database, get_engine

app = FastAPI(title="组织管理 API")

# 初始化数据库
@app.on_event("startup")
def startup():
    init_database("sqlite:///./organization.db")
    from yweb.orm import BaseModel
    BaseModel.metadata.create_all(bind=get_engine())

# 请求模型
class CreateOrgRequest(PydanticModel):
    name: str
    code: str

class CreateDeptRequest(PydanticModel):
    org_id: int
    name: str
    parent_id: Optional[int] = None

class CreateEmployeeRequest(PydanticModel):
    name: str
    mobile: Optional[str] = None
    email: Optional[str] = None

# 服务依赖
def get_org_service():
    return OrganizationService()

# 组织 API
@app.post("/orgs")
def create_org(req: CreateOrgRequest, svc: OrganizationService = Depends(get_org_service)):
    org = svc.create_org(name=req.name, code=req.code)
    return OK(org.to_dict(), "创建成功")

@app.get("/orgs/{org_id}")
def get_org(org_id: int, svc: OrganizationService = Depends(get_org_service)):
    org = svc.get_org(org_id)
    if not org:
        return NotFound("组织不存在")
    return OK(org.to_dict())

@app.get("/orgs/{org_id}/departments")
def get_org_depts(org_id: int, svc: OrganizationService = Depends(get_org_service)):
    depts = svc.get_dept_tree(org_id)
    return OK([d.to_dict() for d in depts])

# 部门 API
@app.post("/departments")
def create_dept(req: CreateDeptRequest, svc: OrganizationService = Depends(get_org_service)):
    try:
        dept = svc.create_dept(
            org_id=req.org_id,
            name=req.name,
            parent_id=req.parent_id
        )
        return OK(dept.to_dict(), "创建成功")
    except ValueError as e:
        return BadRequest(str(e))

@app.delete("/departments/{dept_id}")
def delete_dept(dept_id: int, svc: OrganizationService = Depends(get_org_service)):
    try:
        svc.delete_dept(dept_id)
        return OK(None, "删除成功")
    except ValueError as e:
        return BadRequest(str(e))

# 员工 API
@app.post("/employees")
def create_employee(req: CreateEmployeeRequest, svc: OrganizationService = Depends(get_org_service)):
    emp = svc.create_employee(
        name=req.name,
        mobile=req.mobile,
        email=req.email
    )
    return OK(emp.to_dict(), "创建成功")

@app.post("/employees/{employee_id}/join-org/{org_id}")
def join_org(
    employee_id: int,
    org_id: int,
    emp_no: Optional[str] = None,
    set_primary: bool = False,
    svc: OrganizationService = Depends(get_org_service)
):
    try:
        rel = svc.add_employee_to_org(
            employee_id=employee_id,
            org_id=org_id,
            emp_no=emp_no,
            set_as_primary=set_primary
        )
        return OK(rel.to_dict(), "加入成功")
    except ValueError as e:
        return BadRequest(str(e))

@app.post("/employees/{employee_id}/join-dept/{dept_id}")
def join_dept(
    employee_id: int,
    dept_id: int,
    set_primary: bool = False,
    svc: OrganizationService = Depends(get_org_service)
):
    try:
        rel = svc.add_employee_to_dept(
            employee_id=employee_id,
            dept_id=dept_id,
            set_as_primary=set_primary
        )
        return OK(rel.to_dict(), "加入成功")
    except ValueError as e:
        return BadRequest(str(e))
```

## 辅助函数说明

### setup_org_relationships()

由于 SQLAlchemy 的限制，抽象类无法预先定义 `relationship`（因为不知道子类的名称）。`setup_org_relationships()` 辅助函数解决了这个问题，一行代码自动设置所有模型间的关系。

**自动设置的关系**：

| 模型 | 自动添加的 relationship |
|------|------------------------|
| Organization | `departments`, `employee_org_rels` |
| Department | `organization`, `parent`, `children`, `primary_leader`, `employee_dept_rels`, `department_leader_rels` |
| Employee | `primary_org`, `primary_dept`, `employee_org_rels`, `employee_dept_rels`, `department_leader_rels`, `leading_departments` |
| EmployeeOrgRel | `employee`, `organization` |
| EmployeeDeptRel | `employee`, `department` |
| DepartmentLeader | `department`, `employee` |

**双向关系说明**：

- `Department.primary_leader` ↔ `Employee.leading_departments`：通过 `back_populates` 双向绑定
  - `dept.primary_leader` → 获取部门的主负责人
  - `emp.leading_departments` → 获取员工作为主负责人的所有部门

**使用方式**：

```python
# 方式1（推荐）：使用辅助函数自动设置
setup_org_relationships(
    Organization, Department, Employee,
    EmployeeOrgRel, EmployeeDeptRel, DepartmentLeader
)

# 设置后可以直接使用：
dept = Department.get(1)
print(dept.organization.name)  # 关联的组织
print(dept.children)           # 子部门列表
print(dept.parent)             # 父部门
```

```python
# 方式2：手动定义（更灵活但代码更多）
class Department(AbstractDepartment):
    organization = relationship("Organization", back_populates="departments")
    parent = relationship("Department", remote_side="Department.id", back_populates="children")
    children = relationship("Department", back_populates="parent")
    # ... 其他关系
```

**混合使用**：如果有项目特有的关系，可以先定义在类中，辅助函数会跳过已定义的：

```python
class Employee(AbstractEmployee):
    # 项目特有关系，手动定义
    user = relationship("User", foreign_keys="Employee.user_id")

# 辅助函数会设置其他标准关系，但跳过已定义的
setup_org_relationships(...)
```

### 级联软删除配置

`setup_org_relationships()` 会自动配置所有关系的级联软删除策略。默认配置如下：

| 配置键 | 默认策略 | 说明 |
|--------|----------|------|
| `org_to_dept` | PROTECT | 组织有部门时禁止删除 |
| `org_to_emp_org_rel` | PROTECT | 组织有员工时禁止删除 |
| `dept_to_children` | PROTECT | 部门有子部门时禁止删除 |
| `dept_to_emp_dept_rel` | PROTECT | 部门有员工时禁止删除 |
| `dept_to_leader_rel` | DELETE | 删除部门时级联删除负责人关系 |
| `emp_to_primary_leader` | SET_NULL | 删除员工时将其主负责人引用置空 |
| `emp_to_emp_org_rel` | DELETE | 删除员工时级联删除组织关系 |
| `emp_to_emp_dept_rel` | DELETE | 删除员工时级联删除部门关系 |
| `emp_to_leader_rel` | DELETE | 删除员工时级联删除负责人关系 |

**自定义级联配置**：

```python
from yweb.organization import setup_organization
from yweb.orm.fields import DELETE, SET_NULL, PROTECT

# 使用工厂函数时传入自定义配置
org = setup_organization(
    app=app,
    cascade_config={
        # 允许级联删除组织下的部门（谨慎使用）
        "org_to_dept": DELETE,
        # 其他未指定的保持默认
    }
)

# 或使用辅助函数
from yweb.organization import setup_org_relationships

setup_org_relationships(
    Organization, Department, Employee,
    EmployeeOrgRel, EmployeeDeptRel, DepartmentLeader,
    cascade_config={"org_to_dept": DELETE}
)
```

**可用的删除策略**：

| 策略 | 说明 |
|------|------|
| `DELETE` | 级联删除关联记录 |
| `SET_NULL` | 将关联字段置为 NULL |
| `PROTECT` | 存在关联时禁止删除（抛出异常） |
| `DO_NOTHING` | 不做任何处理 |
| `UNLINK` | 解除关联（适用于多对多） |

> **注意**：级联软删除是框架的核心特性，无需在 Service 层手动清理关联数据。删除员工时，其所有组织关系、部门关系、负责人关系都会自动处理。

## 最佳实践

1. **优先使用工厂函数**：新项目推荐使用 `setup_organization()` 一站式设置，代码最少、维护最简单

2. **表名前缀**：建议为所有模型添加统一的表名前缀（如 `sys_`），便于区分业务表
   ```python
   org = setup_organization(app=app, table_prefix="sys_", ...)
   ```

3. **使用 Mixin 扩展字段**：需要扩展字段时使用 Mixin，而非完整继承抽象类
   ```python
   class EmployeeUserMixin:
       user = fields.OneToOne(User, on_delete=fields.DO_NOTHING, nullable=True)
   
   org = setup_organization(app=app, employee_mixin=EmployeeUserMixin, ...)
   ```

4. **使用单例服务**：通过 `org.get_org_service()` 获取服务，保证单例模式

5. **事务管理**：批量操作时建议使用 `@transactional` 装饰器，确保数据一致性

6. **删除策略**：默认使用 PROTECT 策略禁止删除有子部门或员工的组织/部门，员工删除时自动级联清理关联数据

7. **级联软删除**：依赖框架的级联软删除机制，不要在 Service 层手动清理关联数据

7. **主归属设置**：设置主部门前确保已设置主组织，且主部门属于主组织

8. **完全自定义场景**：只有在需要完全控制模型定义时才使用级别3（继承抽象类），大多数场景 Mixin 已足够

## 更多资源

- [ORM 使用指南](orm_guide.md)
- [配置指南](config_guide.md)
- [示例应用](../examples/)
