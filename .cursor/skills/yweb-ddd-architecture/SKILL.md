---
name: yweb-ddd-architecture
description: YWeb DDD 分层架构与 API 设计规范。在创建或修改 API 路由、Service 层、领域模型、DTO 时使用。涵盖瘦 API 原则、服务层拆分、Model 设计、DTO 转换、响应格式等。
---

# YWeb DDD 分层架构与 API 设计规范

## 核心架构要点

YWeb 采用 **Active Record + DDD 分层思想**，三层架构：

```
API 层 (路由) → Service 层 (业务编排) → Domain 层 (领域模型)
```

**关键原则**：
- 不引入 Repository 层，领域模型直接继承 ORM 基类
- API 层保持"瘦"，只做参数验证、DTO 转换、异常捕获、调用 Service
- 业务规则封装在领域模型的 `validate_xxx()` 方法中
- 跨聚合操作通过 Service 层协调
- 简单的纯查询（无业务逻辑）可由 API 层直接调用领域模型

## 各层职责速查

| 层 | 职责 | 禁止 |
|----|------|------|
| API 层（ResourceController / 函数式路由） | 参数验证、DTO 转换、异常→HTTP 响应、调用 Service | 业务逻辑、事务管理、数据库操作 |
| Service 层 | 跨聚合协调、事务管理、权限检查 | HTTP 感知、直接返回 Response |
| Domain 层 | 单聚合业务规则、数据验证、状态变更 | 调用其他聚合、HTTP 感知 |

## 聚合内建模：实体关系 vs 值对象

| 场景 | 推荐方式 | 说明 |
|------|---------|------|
| 子对象有独立生命周期、需独立增删改查 | `OneToOne` / `ManyToOne` | 两张表，外键关联 |
| 子对象是聚合内部状态、无独立主键 | `OwnsOne` | 单表展开，值对象语义 |

典型 `OwnsOne` 场景：地址、金额区间、联系方式、审计信息、时间窗口等。
详见 `yweb-core/docs/orm_docs/21_owns_one.md`。

## DTO 使用要点

- **响应模型**：继承 `DTO`（来自 `yweb`），使用 `from_entity()` / `from_page()` 转换
- **请求模型**：使用 Pydantic `BaseModel`
- DTO 继承自 Pydantic BaseModel，**不要**对 DTO 使用 `@dataclass` 装饰器
- 使用 `_field_mapping` 进行字段映射，使用 `_value_processors` 进行值处理（字段类型应与处理器转换后的类型一致）

## 响应格式要点

- 统一使用 `Resp.OK()` / `Resp.Fail()` / `Resp.NotFound()` 等
- 分页响应使用 `PageResponse`
- 异常统一捕获 `ValueError`，转为 `Resp.Fail()`

## ⚠️ API 路由 async 安全

ORM 是同步的，路由声明方式直接影响并发性能：

- **纯 DB 操作**：路由用 `def`（推荐），FastAPI 自动放线程池
- **混合异步 + DB**：路由用 `async def`，DB 调用用 `await async_db_call(...)` 包装
- **禁止**：`async def` 中直接调用 `Model.query` / `Model.get()` 等同步 ORM，会触发 `SynchronousOnlyOperation`

```python
# ✅ def 路由
@router.get("/users")
def get_users():
    return User.query.all()

# ✅ async def + async_db_call
@router.get("/users")
async def get_users():
    users = await async_db_call(User.get_all)
    extra = await some_async_call()
    return {"users": users, "extra": extra}
```

## API 层路由组织

API 层有两种等价的路由组织方式，遵循相同的「瘦 API」原则：

### ResourceController 类视图（推荐）

```python
from yweb.controller import ResourceController, get

class UserController(ResourceController):
    prefix = "/user"
    tags = ["用户"]

    @get
    async def list(self, page: int = 1, size: int = 10):
        """获取用户列表"""
        result = UserModel.paginate(page=page, per_page=size)
        return Resp.OK(UserDTO.from_page(result))

    async def create(self, body: CreateUserRequest):
        """创建用户"""
        user = UserService.create(body)
        return Resp.OK(UserDTO.from_entity(user))
```

- 方法名即路由路径（`create` → `/create`）
- 默认 POST，`@get` 标记 GET
- `_` 开头方法为私有辅助，不注册路由
- `dependencies` 类属性注入 Router 级依赖
- 每个 `ResourceController` 必须显式声明 `prefix`，不得省略或依赖默认值；没有额外前缀时也必须写 `prefix = ""`

### ResourceController 运行时依赖绑定（强制）

如果 controller 的 model、service、scheduler 等依赖需要在应用装配或 `create_xxx_router(...)` 调用时传入，必须使用 `Controller.create_router(...)` 生成独立 router：

```python
from fastapi import APIRouter
from yweb.controller import ResourceController, get

class UserController(ResourceController):
    prefix = ""
    tags = ["用户"]
    user_model = None

    @get(response_model=PageResponse[UserDTO])
    def list(self, page: int = 1, page_size: int = 10):
        model = self.user_model
        return Resp.OK(UserDTO.from_page(model.query.paginate(page=page, page_size=page_size)))


def create_user_router(user_model: type) -> APIRouter:
    return UserController.create_router(user_model=user_model)
```

强制规则：

- 禁止使用 `_xxx_model`、`_scheduler`、`_acl_service` 等模块级变量保存 router 工厂参数
- 禁止新增 `init_xxx_controller(...)` 这类修改全局状态或类变量的注入函数
- 使用运行时依赖的 controller 不直接挂载 `Controller.router`，也不纳入 `scan_controllers`
- 某一组可选 API 是否挂载取决于配置时，按能力组拆成独立 `ResourceController`，在工厂层用 `if xxx: include_router(...)` 条件挂载
- 相关小 controller 可以放在同一个 `.py` 文件里；用外层 `include_router(prefix=...)` + controller `prefix` 保持 URL 不变，`prefix = ""` 表示不增加额外路径层级
- 不要在一个大 controller 方法内部用运行时 `if/else` 隐藏端点是否存在，也不要把 `lambda/when/build` 作为默认方案
- 只有特殊协议端点、RESTful 强路径约束，或拆分后明显更难读的模块，继续使用函数式路由

### 函数式路由

```python
router = APIRouter(prefix="/webhook")

@router.post("/github")
async def github_webhook(request: Request): ...
```

适合特殊协议端点（webhook、OAuth callback 等）。
## 详细规范文档

编码前**必须阅读**对应文档以获取完整规范和示例：

| 主题 | 文档路径 |
|------|---------|
| DDD 分层架构全貌 | `yweb-core/docs/webapi_development_standards/ddd-layered-architecture-guide.md` |
| API 层设计规范（瘦 API 原则） | `yweb-core/docs/webapi_development_standards/api_layer_design_guide.md` |
| ResourceController 类视图指南 | `yweb-core/docs/15_controller_guide.md` |
| Model 与 Service 层设计规范 | `yweb-core/docs/webapi_development_standards/model_and_service_design_guide.md` |
| DTO 与响应处理规范 | `yweb-core/docs/webapi_development_standards/dto_response_guide.md` |
| API 与 Service 开发综合规范 | `yweb-core/docs/webapi_development_standards/development_guide.md` |

## 工作流程

1. 新建功能时，先阅读 `ddd-layered-architecture-guide.md` 确定分层
2. 编写 API 路由前，阅读 `api_layer_design_guide.md` 和 `15_controller_guide.md`
3. 编写 Model / Service 前，阅读 `model_and_service_design_guide.md`
4. 定义 DTO 和响应格式前，阅读 `dto_response_guide.md`
5. 综合参考 `development_guide.md` 中的完整示例
