# ACL 模块使用指南

本指南介绍如何使用 YWeb 的 ACL（Access Control List）模块。ACL 提供**对象级权限控制**——即"某人对某个具体资源有什么权限"。

## 概述

ACL 模块与 RBAC（`yweb.rbac`）是互补的两套授权机制：

| 特性 | RBAC (`yweb.rbac`) | ACL (`yweb.acl`) |
|------|---------------------|-------------------|
| 粒度 | 功能级（"能不能用这个 API"） | 对象级（"能不能看这个文档"） |
| 模型 | 角色 + 权限码 | 身份标签 + 资源树 + 规则 |
| 典型场景 | 菜单权限、按钮权限 | 文件夹权限、文档权限、工作流权限 |

### 核心设计原则

1. **引擎只认字符串和整数**：入参是 `identities: set[str]` + `required_level: int`
2. **仅依赖 yweb.orm**：不依赖 auth、organization、rbac 等其他模块
3. **业务语义外置**：权限等级（READ/WRITE）、资源类型（FOLDER/DOCUMENT）由应用层定义
4. **集成逻辑外置**：身份展开（IdentityExpander）、API 中间件等由应用层组装

## 快速开始

### 一站式设置

```python
from yweb.acl import setup_acl

acl = setup_acl(app=app, table_prefix="sys_")

# 获取服务
service = acl.get_service()

# 检查权限
identities = {"user:123", "dept:tech", "everyone"}
has_perm = service.check(identities, "DOCUMENT", "d001", required_level=10)
```

### 分步设置

```python
from yweb.acl import create_acl_models

# 1. 创建模型
acl = create_acl_models(table_prefix="sys_")

# 2. 初始化依赖（可选）
acl.init_dependency(identity_provider=my_provider)

# 3. 挂载路由（可选）
acl.mount_routes(app, prefix="/api/v1/acl")
```

## 架构概览

```
Layer 3: 应用层（你的代码）
    ├── PermissionLevel 枚举（READ=10, WRITE=30, ADMIN=60）
    ├── ResourceType 枚举（FOLDER, DOCUMENT, ...）
    ├── IdentityExpander（桥接 organization + rbac → 身份标签）
    └── ApiPermissionMiddleware（桥接 FastAPI 请求 → ACL 检查）

Layer 2: AclService（规则管理 + 权限检查门面）
    ├── check / get_effective_level / get_accessible / batch_check
    ├── create_rule / update_rule / delete_rule
    └── register_resource / unregister_resource / set_inherit_parent

Layer 1: AclEngine（纯算法）
    ├── AbstractAclRule（规则模型）
    ├── AbstractAclResource（资源树节点）
    └── Effect 枚举（ALLOW / DENY）
```

## ACL 规则模型

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `resource_type` | str(50) | 资源类型（应用层定义） |
| `resource_id` | str(256) | 业务资源 ID |
| `subject_type` | str(20) | 主体类型（辅助字段，引擎不使用） |
| `subject_id` | str(256) | 身份标签（如 `user:123`, `dept:456`） |
| `permission_level` | int | 权限等级（应用层定义语义） |
| `effect` | str(10) | ALLOW / DENY |
| `inherit` | bool | 此规则是否向子资源传播（默认 True） |
| `dept_scope` | str(20) | 部门范围（辅助字段，引擎不使用） |

### 关键概念：inherit 与 inherit_parent

这两个字段控制继承的两个方向：

- **`AclRule.inherit`**：这条规则是否向子资源传播。`True` 表示"对当前资源和所有子资源生效"
- **`AclResource.inherit_parent`**：这个资源节点是否接收父级传下来的规则。`False` 表示"断开继承"

两者配合：即使规则 `inherit=True`，如果子资源 `inherit_parent=False`，该规则也不会生效。

## 资源树

ACL 资源树使用物化路径（Materialized Path）存储层级关系。每个业务资源在 ACL 中对应一个树节点。

### 注册资源

```python
service = acl.get_service()

# 注册根文件夹
service.register_resource(
    resource_type="FOLDER",
    resource_id="f001",
    display_name="技术文档",
)

# 注册子文档
service.register_resource(
    resource_type="DOCUMENT",
    resource_id="d001",
    display_name="API 设计规范",
    parent_id=root_folder.id,  # 指向 ACL 资源表的 id
)
```

### 资源 ID 约定

`AclRule.resource_id` 和 `AclResource.resource_id` 必须使用相同的值域。推荐统一使用 `str(业务表主键)`。

## 权限检查

### 基本检查

```python
identities = {"user:123", "dept:tech", "everyone"}

# 单个资源
has_read = service.check(identities, "DOCUMENT", "d001", required_level=10)

# 获取有效等级
level = service.get_effective_level(identities, "DOCUMENT", "d001")
```

### 批量检查

```python
result = service.batch_check(identities, [
    {"resource_type": "DOCUMENT", "resource_id": "d001", "required_level": 10},
    {"resource_type": "DOCUMENT", "resource_id": "d002", "required_level": 30},
])
# result = {"DOCUMENT:d001": True, "DOCUMENT:d002": False}
```

### 反向查询

```python
# 查询用户能访问的所有文档
accessible_ids = service.get_accessible(
    identities,
    resource_type="DOCUMENT",
    min_level=10,
)
```

## 规则管理

### 创建规则

```python
# 给部门授权
service.create_rule(
    resource_type="FOLDER",
    resource_id="f001",
    subject_id="dept:tech",
    permission_level=10,
    effect="ALLOW",
    inherit=True,
    subject_type="dept",
    dept_scope="INCLUDE_CHILDREN",
)

# DENY 某用户
service.create_rule(
    resource_type="DOCUMENT",
    resource_id="d003",
    subject_id="user:789",
    permission_level=10,
    effect="DENY",
    inherit=False,
)
```

### 断开继承

```python
service.set_inherit_parent("FOLDER", "f002", inherit=False)
```

## 身份标签（Identities）

身份标签是 ACL 引擎的核心输入。引擎不关心标签怎么来的，只做字符串匹配。

### 标签格式示例

```python
identities = {
    "everyone",                    # 所有人
    "user:123",                    # 用户
    "dept:tech",                   # 部门（含子部门）
    "dept_only:frontend",          # 仅直属部门
    "role:admin",                  # 角色
    "dept_role:tech:admin",        # 部门×角色
}
```

### IdentityProvider 协议

框架定义了 `IdentityProvider` 协议，应用层实现身份展开逻辑：

```python
from yweb.acl import IdentityProvider

class MyIdentityProvider:
    """将用户转换为身份标签集合"""

    def get_identities(self, user) -> set[str]:
        identities = {"everyone", f"user:{user.id}"}
        # 添加部门、角色等标签...
        return identities
```

## API 端点

ACL 模块提供以下 RESTful API（通过 ResourceController）：

### 规则管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/acl/rules/list?resource_type=X&resource_id=Y` | 查询规则列表 |
| POST | `/acl/rules/create` | 创建规则 |
| POST | `/acl/rules/create_batch` | 批量创建/更新规则（同一主体写到多个资源；同主体+效果已存在且等级/继承不同则更新） |
| POST | `/acl/rules/update` | 更新规则 |
| POST | `/acl/rules/delete` | 删除规则 |

### 资源树管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/acl/resources/tree` | 获取资源树 |
| POST | `/acl/resources/register` | 注册资源节点 |
| POST | `/acl/resources/inherit` | 设置继承开关 |

### 权限检查

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/acl/permission/check` | 检查权限 |
| POST | `/acl/permission/batch` | 批量检查 |
| GET | `/acl/permission/accessible` | 查询可访问资源 |

权限检查端点的 `identities` 由服务端自动从请求上下文获取（需配置 IdentityProvider）。

## 与应用集成

### 典型集成方式

```python
# main.py
from yweb.acl import setup_acl
from yweb.auth import setup_auth
from yweb.organization import setup_organization
from yweb.rbac import setup_rbac

# 各模块独立初始化
auth = setup_auth(User, app=app)
org = setup_organization(app, ...)
rbac = setup_rbac(app=app)
acl = setup_acl(app=app, table_prefix="sys_")

# 应用层组装
expander = MyIdentityExpander(
    employee_model=org.Employee,
    dept_model=org.Department,
    role_model=rbac.Role,
)
acl.init_dependency(identity_provider=expander)
```

### 在 Service 层使用

```python
class DocumentService:
    def __init__(self, acl_service, identity_provider):
        self.acl = acl_service
        self.expander = identity_provider

    def get_document(self, user, doc_id):
        if user.is_admin:
            return Document.get(doc_id)

        identities = self.expander.get_identities(user)
        if not self.acl.check(identities, "DOCUMENT", str(doc_id), 10):
            raise PermissionDenied("无权查看此文档")

        return Document.get(doc_id)
```

## DENY 优先算法

ACL 引擎的权限解析遵循 **DENY 优先** 原则：

1. 从目标资源沿树向上收集所有适用的规则
2. 过滤：只保留 `subject_id` 匹配 `identities` 的规则
3. 如果有任何 DENY 规则命中 → 返回 0（无权限）
4. ALLOW 规则中取最高的 `permission_level`

## setup_acl 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `app` | FastAPI | None | 传入时自动挂载路由 |
| `table_prefix` | str | "" | 表名前缀 |
| `rule_mixin` | Type | None | 规则模型扩展 Mixin |
| `resource_mixin` | Type | None | 资源模型扩展 Mixin |
| `rule_tablename` | str | None | 自定义规则表名 |
| `resource_tablename` | str | None | 自定义资源表名 |
| `api_prefix` | str | "/api/v1" | API 全局前缀 |
| `acl_prefix` | str | "/acl" | ACL 模块前缀 |
| `tags` | list | None | OpenAPI 标签 |
| `dependencies` | list | None | 路由依赖 |
| `identity_provider` | IdentityProvider | None | 身份展开实例 |
