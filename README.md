# YWeb

基于 **FastAPI + SQLAlchemy** 的 Python Web 应用框架。开箱即用，灵活可扩展。

**设计理念**：用最少的代码完成最多的事情。通过 Active Record 模式、装饰器、一键式 setup 函数和 Mixin 混入，让开发者专注业务逻辑，不被基础设施代码所困。

## 为什么选择 YWeb

- **极简 API**：`user.save()`、`user.delete()`、`User.get(1)` —— Active Record 模式，模型即操作
- **一键启用**：`setup_auth()` 一行完成认证，`setup_organization()` 一行启用组织架构
- **装饰器驱动**：`@cached`、`@transactional`、`@scheduler.cron()` —— 一行添加缓存、事务、定时任务
- **灵活扩展**：Mixin 混入（树形结构、状态机、排序、标签），需要时加一行继承即可
- **DDD 分层**：API → Service → Domain，职责清晰，富领域模型封装业务规则
- **智能默认**：所有配置都有合理默认值，YAML 中只写需要覆盖的项

---

## 安装

### Python 版本要求

- **最低要求**：Python 3.8+
- **推荐版本**：Python 3.11（性能最优，生态成熟）


```bash
# 从 PyPI 安装
pip install yweb

# 从本地安装（开发模式，推荐使用 compat 确保 IDE 导航正常）
pip install -e /path/to/yweb-core --config-settings editable_mode=compat
```

---

## AI 编程助手支持

YWeb 项目已集成 AI 编程助手功能，预制了常用的开发 skills，支持智能代码生成和开发流程优化。

- **Skills 目录**：`/.cursor/` 下包含了预制的 AI 编程 skills 和 rules
- **可自定义**：可根据需要修改 skills 文件夹名称，适配不同的 AI 编程工具
- **开发规范**：详细的 API 开发规范和认证流程文档已准备，支持 AI 辅助开发

> 💡 **提示**：使用支持 skills 的 AI 编程工具时，可直接调用项目中的开发规范和最佳实践

---

## 快速体验

### 30 秒启动一个 API 服务

```python
from fastapi import FastAPI
from yweb import Resp, init_database, BaseModel
from sqlalchemy import Column, String

# 初始化
app = FastAPI()
init_database("sqlite:///./app.db")

# 定义模型 —— 继承 BaseModel 自动获得 id、name、时间戳、软删除
class User(BaseModel):
    email = Column(String(200), comment="邮箱")
# 创建数据库表
BaseModel.create_all()
# API 端点
@app.get("/users/{user_id}")
def get_user(user_id: int):
    user = User.get(user_id)
    if not user:
        return Resp.NotFound("用户不存在")
    return Resp.OK(user)
```

无需手动创建 session、无需配置连接池、无需编写序列化逻辑。

---

## 核心功能一览

### ORM —— Active Record，告别样板代码

继承 `BaseModel` 自动获得：`id`、`name`、`code`、`created_at`、`updated_at`、`deleted_at`(软删除)、`ver`（版本控制） 字段。

```python
class Article(BaseModel):
    title = Column(String(200), comment="标题")
    content = Column(Text, comment="内容")

# CRUD —— 一行搞定
article = Article(title="Hello", content="World")
article.save(commit=True)                        # 创建（save 自动判断新增/更新）
article.update(title="New Title", commit=True)    # 更新
article.delete(commit=True)                       # 软删除（自动设置 deleted_at）
found = Article.get(article.id)                   # 按 ID 查询

# 链式查询 + 分页 —— 一行完成
page = Article.query.filter(Article.title.like("%Hello%")).paginate(page=1, page_size=10)
# page.rows / page.total_records / page.total_pages / page.has_next

# 批量操作
Article.add_all([a1, a2, a3], commit=True)

# 序列化 —— 一行转字典
article.to_dict(exclude={"deleted_at"})

# 历史版本 —— 启用 enable_history 自动记录每次变更
class Document(BaseModel):
    enable_history = True  # 启用版本历史
    content = Column(Text)

doc = Document(content="v1").save(commit=True)
doc.update(content="v2", commit=True)

doc.history                              # 获取所有历史版本
doc.history_count                        # 历史版本数量
doc.get_history(version=1)               # 获取指定版本
doc.get_history_diff(1, 2)               # 比较两个版本差异
doc.restore_to_version(1, commit=True)   # 恢复到指定版本

# 关系定义 —— 自动创建外键列和反向引用
from yweb.orm import fields

class Department(BaseModel):
    employees: fields.HasMany["Employee"]  # 类型提示（可选）

class Employee(BaseModel):
    # 多对一：自动创建 department_id 列 + department 属性 + Department.employees 反向引用
    department = fields.ManyToOne(Department, on_delete=fields.SET_NULL)

class User(BaseModel):
    profile: fields.HasOne["UserProfile"]  # 类型提示（可选）
    roles = fields.ManyToMany(Role, on_delete=fields.UNLINK)  # 多对多：自动创建中间表

class UserProfile(BaseModel):
    # 一对一：自动创建 user_id 列 + user 属性 + User.profile 反向引用
    user = fields.OneToOne(User, on_delete=fields.DELETE)

# on_delete 选项：DELETE(级联删除) / SET_NULL(置空) / UNLINK(解除关联) / DO_NOTHING
```

### 统一响应 —— Resp 快捷类

所有 API 返回统一格式，前端无需猜测响应结构：

```python
from yweb import Resp

# 成功
return Resp.OK(data={"id": 1, "name": "Tom"}, message="查询成功")

# 客户端错误
return Resp.BadRequest("参数错误", msg_details=["用户名不能为空", "密码太短"])
return Resp.NotFound("用户不存在")
return Resp.Unauthorized("请先登录")
return Resp.Forbidden("无权操作")
return Resp.Conflict("用户名已存在")

# 警告（操作成功但有提示信息）
return Resp.Warning("导入完成，部分数据异常", data={"success": 8, "failed": 2})
```

**统一响应格式：**

```json
{
  "status": "success",
  "message": "查询成功",
  "data": {"id": 1, "name": "Tom"},
  "timestamp": "2026-01-09T10:30:00"
}
```

也可以用函数式写法（效果相同）：

```python
from yweb import OK, BadRequest, NotFound

return OK({"id": 1, "name": "Tom"}, "查询成功")
return BadRequest("参数错误")
return NotFound("用户不存在")
```

### 事务管理 —— 装饰器自动提交/回滚

```python
from yweb.orm import transaction_manager as tm

@tm.transactional()
def transfer(from_id, to_id, amount):
    sender = Account.get(from_id)
    receiver = Account.get(to_id)
    sender.balance -= amount
    sender.save()
    receiver.balance += amount
    receiver.save()
    # 函数正常返回 → 自动提交；抛出异常 → 自动回滚
```

### DTO 响应 —— 一行转换

定义 DTO，配合 API 端点使用：

```python
from yweb import DTO, Resp
from pydantic import BaseModel as Schema

# 响应 DTO —— 继承 DTO，自动从实体映射字段
class UserResponse(DTO):
    id: int
    username: str
    email: str

# 请求 Schema —— 普通 Pydantic BaseModel
class CreateUserRequest(Schema):
    username: str
    email: str

# ==================== API 端点 ====================

@app.get("/users/{user_id}")
def get_user(user_id: int):
    """获取单个用户"""
    user = User.get(user_id)
    if not user:
        return Resp.NotFound("用户不存在")
    return Resp.OK(UserResponse.from_entity(user))

@app.get("/users")
def list_users(page: int = 1, page_size: int = 10):
    """分页查询 —— from_page 一行转换分页结果"""
    page_result = User.query.paginate(page=page, page_size=page_size)
    return Resp.OK(UserResponse.from_page(page_result))

@app.post("/users")
def create_user(req: CreateUserRequest):
    """创建用户"""
    user = User(username=req.username, email=req.email)
    user.save(commit=True)
    return Resp.OK(UserResponse.from_entity(user), message="创建成功")
```

**返回格式示例：**

单个实体 `GET /users/1`：
```json
{
  "status": "success",
  "message": "操作成功",
  "data": {
    "id": 1,
    "username": "tom",
    "email": "tom@example.com"
  },
  "timestamp": "2026-01-09T10:30:00"
}
```

分页结果 `GET /users?page=1&page_size=2`：
```json
{
  "status": "success",
  "message": "操作成功",
  "data": {
    "rows": [
      {"id": 1, "username": "tom", "email": "tom@example.com"},
      {"id": 2, "username": "jerry", "email": "jerry@example.com"}
    ],
    "total_records": 50,
    "total_pages": 25,
    "page": 1,
    "page_size": 2,
    "has_next": true,
    "has_prev": false
  },
  "timestamp": "2026-01-09T10:30:00"
}
```

---

### 认证授权 —— 一行启用，功能完整

**一行 setup，自动完成 5 件事：**

```python
from yweb.auth import setup_auth, AbstractUser

class User(AbstractUser):
    # 自定义数据库表名，可以省略，省略后，自动创建表名为'user'
    __tablename__ = "sys_user"

# 一行完成：JWT 双 Token + 角色模型 + 用户管理路由 + 登录记录路由
auth = setup_auth(app=app, user_model=User, jwt_settings=settings.jwt)

# 框架自动完成：
# 1. 创建 JWTManager（双 Token：Access Token + Refresh Token）
# 2. 创建 Role 模型 + User.roles 多对多关系（表名自动推导）
# 3. 创建 LoginRecord 模型（登录审计）
# 4. 挂载用户管理路由 → /api/v1/users
# 5. 挂载登录记录路由 → /api/v1/login-records
```

**在路由中使用：**

```python
@app.get("/me")
def get_me(user=Depends(auth.get_current_user)):
    return Resp.OK(user)
```

**自定义认证服务（需要扩展登录逻辑时）：**

```python
from yweb.auth import BaseAuthService

class MyAuthService(BaseAuthService):
    def on_authenticate_success(self, user, **kwargs):
        """登录成功回调 —— 发送通知、记录统计"""
        super().on_authenticate_success(user, **kwargs)
        send_login_notification(user)

    def on_authenticate_failure(self, username, **kwargs):
        """登录失败回调 —— 自动累计失败次数、锁定账户"""
        super().on_authenticate_failure(username, **kwargs)
        check_alert(username)
```

**内置安全特性（开箱即用）：**

| 特性 | 说明 |
|------|------|
| JWT 双 Token | Access Token（短期）+ Refresh Token（长期），自动刷新 |
| 滑动过期 | Refresh Token 剩余不足 N 天时自动续期，活跃用户"永不过期" |
| Token 黑名单 | `logout()` 自动撤销用户所有 Token |
| IP 频率限制 | 同一 IP 连续失败 N 次 → 自动封锁（一级防线） |
| 账户锁定 | 累计失败 N 次 → 自动锁定账户（二级防线，需 `LockableMixin`） |
| 密码安全 | `PasswordHelper` 哈希/验证 + `PasswordValidator` 强度检查 |
| 登录审计 | 自动记录登录成功/失败/IP/设备信息 |

**支持 7 种认证方式：**

JWT、API Key、Session、OAuth 2.0、OIDC、MFA（多因素）、LDAP/AD —— 按需启用，通过统一认证管理器协调。

### 权限管理 —— RBAC 框架

```python
from yweb.permission import require_permission, require_role

@app.get("/users")
def list_users(user=Depends(require_permission("user:list"))):
    ...

@app.delete("/users/{id}")
def delete_user(user=Depends(require_role("admin"))):
    ...
```

支持角色继承、权限缓存、FastAPI 依赖注入。

### 组织架构 —— 一行启用

```python
from yweb.organization import setup_organization

# 一行启用：组织/部门/员工/关系 管理（26 个 API 自动挂载）
org = setup_organization(app=app, api_prefix="/api/v1")
```

**自动完成**：创建 6 个模型（Organization / Department / Employee / 员工-组织关联 / 员工-部门关联 / 部门负责人）、创建服务实例、挂载 26 个 CRUD API 路由。

**内置能力**：

| 功能 | 说明 |
|------|------|
| 多组织管理 | 支持多个独立组织 |
| 树形部门 | 无限层级父子结构，支持 `get_children()` / `get_descendants()` |
| 员工多归属 | 员工可属于多个组织、多个部门，可设置主归属 |
| 部门负责人 | 每个部门可设多个负责人和一个主负责人 |
| 外部系统同步 | 支持企业微信、飞书、钉钉数据同步 |

**三种使用级别，按需选择**：

```
级别 1（~5 行）  ：零配置快速启用，开箱即用
级别 2（~15 行） ：Mixin 轻量扩展，如员工关联用户账号
级别 3（~80 行） ：继承抽象模型，完全自定义
```

**级别 2 示例 —— Mixin 扩展员工关联用户：**

```python
from yweb.organization import setup_organization, fields

class EmployeeUserMixin:
    """自动创建 user_id 外键 + user 关系 + User.employee 反向引用"""
    user = fields.OneToOne("User", nullable=True)

org = setup_organization(
    app=app,
    api_prefix="/api/v1",
    employee_mixin=EmployeeUserMixin,
)

# Employee 自动拥有 user / user_id 属性
emp = org.Employee.query.first()
print(emp.user.username)
```

---

### 缓存 —— 装饰器一行搞定

支持**内存缓存**和 **Redis 缓存**两种后端，API 完全一致，切换零成本：

```python
from yweb import cached

# 内存缓存 + 自动失效（推荐）—— User 变更时自动清除缓存
@cached(ttl=300, invalidate_on=User)
def get_user(user_id: int):
    return User.get(user_id)

# Redis 缓存（分布式/多实例部署）
@cached(ttl=300, backend="redis", invalidate_on=Config)
def get_config(key: str):
    return Config.get_by_key(key)

# 多模型组合 + 自定义 key 提取
@cached(ttl=300, invalidate_on={
    User: lambda u: u.id,
    Department: lambda d: [e.user_id for e in d.employees]  # 关联失效
})
def get_user_with_dept(user_id: int):
    ...
```

并提供通用缓存管理 API（函数列表、统计、清空、自动失效开关）以及缓存条目观测能力（`/entries`、`/entry`，默认返回脱敏预览）。

| 后端 | 适用场景 | 特点 |
|------|---------|------|
| 内存（默认） | 开发环境、单机部署 | 零依赖、速度最快 |
| Redis | 多实例部署、分布式 | 跨进程共享、支持持久化 |

### 异常处理 —— Err 快捷类

```python
from yweb import Err

raise Err.not_found("用户不存在")     # 404
raise Err.auth("密码错误")            # 401
raise Err.forbidden("无权操作")       # 403
raise Err.conflict("用户名已存在")    # 409
```

### 定时任务 —— 装饰器 + Builder 模式

```python
from yweb.scheduler import Scheduler, JobBuilder, cron

scheduler = Scheduler()

# 装饰器方式（推荐）
@scheduler.cron("0 8 * * *", code="DAILY_REPORT", name="每日报表")
async def daily_report(context):
    ...

# Builder 模式（需要动态配置时使用）
async def cleanup_old_data(context):
    ...

config = (
    JobBuilder(cleanup_old_data)
    .code("CLEANUP")
    .name("数据清理")
    .trigger(cron("0 2 * * *"))
    .max_retries(3)
    .build()
)
scheduler.add_job_from_builder(config)

# 执行历史查看（持久化模式下）
executions = scheduler.get_executions(code="DAILY_REPORT", limit=10)
for exe in executions:
    print(f"{exe.run_id}: {exe.status}, 耗时 {exe.duration_ms}ms")
```

> **历史记录**：使用 ORM 存储时，执行历史自动保存到 `scheduler_job_history` 表。框架提供完整的管理 API（`/jobs/list`、`/executions/list`、`/stats` 等），详见 [定时任务指南](docs/09_scheduler_guide.md)。

### 中间件 —— 预制开箱即用

```python
from yweb.middleware import (
    RequestIDMiddleware,              # 请求 ID 追踪（自动生成 X-Request-ID）
    RequestLoggingMiddleware,         # 请求/响应日志（自动记录耗时、状态码、请求体）
    PerformanceMonitoringMiddleware,  # 性能监控（慢请求告警）
    IPAccessMiddleware,               # IP 访问控制（白名单/黑名单、路径级规则）
)

app.add_middleware(RequestIDMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(PerformanceMonitoringMiddleware)
```

中间件行为通过 YAML 配置调整，无需改代码：

```yaml
middleware:
  request_log_max_body_size: 10KB       # 请求体日志截断大小
  slow_request_threshold: 1.0           # 慢请求阈值（秒）
  request_log_skip_paths:               # 跳过日志的路径
    - "/health"
    - "/metrics"
```

### 日志 —— 开箱即用，生产级特性

```python
from yweb import get_logger

logger = get_logger()  # 自动推断模块名，无需传参

logger.info("用户登录成功")
logger.error("数据库连接失败", exc_info=True)
```

**生产级特性**：
- 时间 + 大小双重轮转（`file_when: midnight` + `file_max_bytes: 10MB`）
- 敏感数据自动过滤（密码、Token 等字段自动脱敏）
- SQL 日志独立文件（`sql_log_enabled: true` 开启，方便调试）
- 写缓存（`buffer_enabled: true`，高并发场景批量写入提升性能）
- 自动清理（`max_retention_days: 30`，过期日志自动删除）

```yaml
logging:
  level: INFO
  file_path: logs/app_{date}.log
  max_retention_days: 30          # 自动清理 30 天前的日志
  sql_log_enabled: false          # 生产环境关闭 SQL 日志
```

### 验证约束 —— 类似 .NET MVC 特性

```python
from yweb import Typed, StringLength, Range

class CreateUserRequest(BaseModel):
    username: StringLength(2, 20)           # 长度 2-20
    email: Typed.Email                      # 邮箱格式
    phone: Typed.OptionalPhone              # 可选手机号
    age: Range(18, 120)                     # 范围 18-120
```

---

## 灵活扩展 —— Mixin 混入，需要时加一行继承

YWeb 提供丰富的 Mixin，按需组合，不引入不需要的功能：

### 树形结构

```python
from yweb.orm import TreeMixin

class Category(BaseModel, TreeMixin):
    title = Column(String(100), comment="分类名")

# 自动获得树形操作能力
root.get_children()       # 直接子节点
root.get_descendants()    # 所有子孙
child.get_ancestors()     # 所有祖先
Category.get_tree_list()  # 嵌套树结构（一次查询）
```

### 状态机

```python
from yweb.orm import StateMachineMixin

class Order(BaseModel, StateMachineMixin):
    __states__ = ["pending", "paid", "shipped", "completed"]
    __transitions__ = [
        {"from": "pending", "to": "paid"},
        {"from": "paid",    "to": "shipped"},
        {"from": "shipped", "to": "completed"},
    ]

order.transition_to("paid")  # 自动验证合法性，触发钩子
```

### 排序

```python
from yweb.orm import SortableMixin

class Banner(BaseModel, SortableMixin):
    image_url = Column(String(500), comment="图片地址")

banner.move_up()       # 上移
banner.move_to_top()   # 置顶
banner.move_to(3)      # 移到第 3 位
```

### 标签

```python
from yweb.orm import TaggableMixin

class Article(BaseModel, TaggableMixin):
    content = Column(Text, comment="内容")

article.add_tags(["Python", "Web"])         # 自动创建标签并关联
Article.find_by_tag("Python")               # 按标签查询
Article.find_by_all_tags(["Python", "Web"]) # AND 查询
```

---

## 配置 —— 智能默认，最小配置即可运行

**最小可运行配置（只需 2 项）：**

```yaml
database:
  url: "sqlite:///./app.db"
jwt:
  secret_key: "your-secret-key"
```

其余全部使用框架默认值。详见 [配置指南](docs/02_config_guide.md)。

**多环境支持：**

```python
from yweb.config import AppSettings, load_yaml_config

class Settings(AppSettings):
    app_name: str = "My App"  # 只写业务特有字段

settings = load_yaml_config("config/settings.yaml", Settings)
# 配置优先级：环境变量 > YAML > 默认值
```

---

## 项目结构

```
yweb-core/
├── yweb/                     # 核心包
│   ├── orm/                  # ORM（Active Record、分页、软删除、Mixin）
│   ├── auth/                 # 认证（JWT 双 Token、setup_auth 一键启用）
│   ├── permission/           # 权限（RBAC、角色继承）
│   ├── organization/         # 组织管理（setup_organization 一键启用）
│   ├── cache/                # 缓存（@cached 装饰器、自动失效）
│   ├── scheduler/            # 定时任务（Cron / Interval / Once、Builder 模式）
│   ├── response/             # 统一响应（Resp 快捷类、DTO）
│   ├── exceptions/           # 异常处理（Err 快捷类、全局处理器）
│   ├── middleware/           # 中间件（请求日志、ID 追踪、性能监控、IP 控制）
│   ├── storage/              # 文件存储（本地 / OSS / S3）
│   ├── log/                  # 日志（时间+大小轮转、敏感数据过滤）
│   ├── config/               # 配置（YAML + 环境变量、AppSettings）
│   ├── validators/           # 验证约束（类似 .NET MVC 特性）
│   └── utils/                # 工具（加密、文件大小解析）
├── docs/                     # 文档
├── tests/                    # 测试
└── examples/                 # 示例
```

## 文档

### 核心指南

| 主题 | 链接 |
|------|------|
| 快速开始 | [docs/01_quickstart.md](docs/01_quickstart.md) |
| 配置指南 | [docs/02_config_guide.md](docs/02_config_guide.md) |
| ORM 指南 | [docs/03_orm_guide.md](docs/03_orm_guide.md) |
| 日志指南 | [docs/04_log_guide.md](docs/04_log_guide.md) |
| 异常处理 | [docs/05_exception_handling.md](docs/05_exception_handling.md) |
| 认证指南 | [docs/06_auth_guide.md](docs/06_auth_guide.md) |
| 组织管理 | [docs/07_organization_guide.md](docs/07_organization_guide.md) |
| 权限管理 | [docs/08_permission_guide.md](docs/08_permission_guide.md) |
| 定时任务 | [docs/09_scheduler_guide.md](docs/09_scheduler_guide.md) |
| 文件存储 | [docs/10_storage_guide.md](docs/10_storage_guide.md) |
| 缓存指南 | [docs/11_cache_guide.md](docs/11_cache_guide.md) |
| 模型注册 | [docs/12_model_registry_guide.md](docs/12_model_registry_guide.md) |
| IP 访问控制 | [docs/13_ip_access_control_guide.md](docs/13_ip_access_control_guide.md) |

### ORM 详细文档

| 主题 | 链接 |
|------|------|
| ORM 文档索引 | [docs/orm_docs/README.md](docs/orm_docs/README.md) |

### WebAPI 开发标准

| 主题 | 链接 |
|------|------|
| DDD 分层架构 | [docs/webapi_development_standards/ddd-layered-architecture-guide.md](docs/webapi_development_standards/ddd-layered-architecture-guide.md) |
| API 层设计 | [docs/webapi_development_standards/api_layer_design_guide.md](docs/webapi_development_standards/api_layer_design_guide.md) |
| 认证流程 | [docs/webapi_development_standards/auth_flow_guide.md](docs/webapi_development_standards/auth_flow_guide.md) |
| JWT 认证 | [docs/webapi_development_standards/jwt_auth_guide.md](docs/webapi_development_standards/jwt_auth_guide.md) |
| DTO 响应 | [docs/webapi_development_standards/dto_response_guide.md](docs/webapi_development_standards/dto_response_guide.md) |
| 模型与服务设计 | [docs/webapi_development_standards/model_and_service_design_guide.md](docs/webapi_development_standards/model_and_service_design_guide.md) |
| 开发指南 | [docs/webapi_development_standards/development_guide.md](docs/webapi_development_standards/development_guide.md) |

### 设计文档

| 主题 | 链接 |
|------|------|
| 定时任务设计 | [docs/scheduler_design.md](docs/scheduler_design.md) |
| 文件存储设计 | [docs/storage_design.md](docs/storage_design.md) |
| ORM 事务外提交行为 | [docs/orm_commit_behavior_outside_transaction.md](docs/orm_commit_behavior_outside_transaction.md) |
| ORM 提交抑制机制 | [docs/orm_commit_suppression_mechanism.md](docs/orm_commit_suppression_mechanism.md) |

## 依赖

- Python >= 3.8
- FastAPI >= 0.100.0
- SQLAlchemy >= 2.0.0
- Pydantic >= 2.0.0

## 测试

```bash
pip install -e ".[dev]"
pytest
pytest --cov=yweb --cov-report=html
```

## License

MIT License
