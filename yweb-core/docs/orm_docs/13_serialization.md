# 13. 数据序列化

## 概述

YWeb ORM 提供了多种数据序列化方式：

- `to_dict()` - 模型转字典
- `to_dict_with_relations()` - 包含关联数据的序列化
- `DTO` - 数据传输对象
- `OK()` 自动序列化

## to_dict() 方法

### 基本用法

```python
user = User.get(1)

# 转换为字典
user_dict = user.to_dict()
print(user_dict)
# {'id': 1, 'username': 'tom', 'email': 'tom@example.com', ...}
```

### 排除字段

```python
# 排除敏感字段
user_dict = user.to_dict(exclude={'password', 'deleted_at'})

# 排除多个字段
user_dict = user.to_dict(exclude={
    'password',
    'salt',
    'deleted_at',
    'ver'
})
```

### 自定义序列化

```python
class User(BaseModel):
    __tablename__ = "user"

    username: Mapped[str] = mapped_column(String(50))
    password: Mapped[str] = mapped_column(String(100))

    def to_dict(self, exclude=None):
        # 默认排除密码
        if exclude is None:
            exclude = set()
        exclude.add('password')
        return super().to_dict(exclude=exclude)
```

## to_dict_with_relations() 方法

### 基本用法

```python
user = User.get(1)

# 包含关联数据
user_dict = user.to_dict_with_relations(
    relations=['roles', 'profile']
)
print(user_dict)
# {
#     'id': 1,
#     'username': 'tom',
#     'roles': [{'id': 1, 'name': 'admin'}, ...],
#     'profile': {'id': 1, 'bio': '...'}
# }
```

### 排除字段

```python
user_dict = user.to_dict_with_relations(
    relations=['roles', 'profile'],
    exclude={'password', 'deleted_at'}
)
```

### 嵌套关联

注意：`to_dict_with_relations` 不直接支持点号语法的嵌套关联。如需获取深层关联数据，需要手动处理：

```python
# 方式1：只获取一级关联
user_dict = user.to_dict_with_relations(relations=['roles'])

# 方式2：自定义序列化方法处理嵌套
class User(BaseModel):
    def to_dict_with_nested(self, exclude=None):
        data = self.to_dict(exclude=exclude)
        data['roles'] = [
            {
                **role.to_dict(),
                'permissions': [p.to_dict() for p in role.permissions]
            }
            for role in self.roles
        ]
        return data
```

## DTO（数据传输对象）

DTO（Data Transfer Object）用于在不同层之间传输数据，提供自动序列化和类型安全的特性。DTO 基于 Pydantic BaseModel，提供了丰富的便捷方法。

### 定义 DTO

```python
from typing import Optional
from pydantic import Field
from yweb.orm import DTO

class UserResponse(DTO):
    """用户响应 DTO"""
    id: int = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")
    email: Optional[str] = Field(None, description="邮箱")
    is_active: bool = Field(True, description="是否启用")
    created_at: Optional[str] = Field(None, description="创建时间")
```

> **注意：DTO 继承自 Pydantic `BaseModel`，请勿在 DTO 子类上使用 `@dataclass` 或 `@dataclass(frozen=True)` 装饰器。**
> 两者的元类机制冲突，会导致运行时错误。如需不可变行为，请使用 Pydantic 的方式：
> ```python
> from pydantic import ConfigDict
>
> class UserResponse(DTO):
>     model_config = ConfigDict(frozen=True)
>     id: int
>     username: str
> ```

**DTO 默认配置：**
- `from_attributes=True` - 支持从 ORM 对象创建
- `extra='ignore'` - 忽略未定义的额外字段（可配置为 `'allow'` 保留扩展字段）

### 从实体创建（from_entity）

```python
user = User.get(1)

# 从 ORM 对象创建 DTO
user_dto = UserResponse.from_entity(user)
print(user_dto.username)
```

`from_entity()` 会自动匹配 DTO 字段与实体属性，并处理 datetime 类型的自动格式化。

### 从字典创建（from_dict）

```python
# 从字典创建 DTO
data = user.to_dict()
data["extra_info"] = "附加信息"
user_dto = UserResponse.from_dict(data)
```

`from_dict()` 同样会自动处理 datetime 格式化和空值处理。

### from_entity vs from_dict - 扩展字段处理（重要）

当用户在基础模型上扩展自定义字段时，两种方法行为不同：

```python
# 用户扩展的模型
class MyUser(AbstractUser):
    vip_level: int = ...    # 用户自定义字段
    
# 框架提供的 DTO（只定义了基础字段）
class UserResponse(DTO):
    id: int
    username: str
    # 没有 vip_level
    
    model_config = ConfigDict(extra="allow")  # 允许额外字段
```

| 方法 | 行为 | 结果 |
|------|------|------|
| `from_entity(user)` | 只获取 DTO 定义的字段 | `{"id": 1, "username": "tom"}` |
| `from_dict(user.to_dict())` | 获取实体的全部字段 | `{"id": 1, "username": "tom", "vip_level": 5}` |

**使用建议：**

| 场景 | 推荐方法 |
|------|----------|
| 只需要基础字段 | `Response.from_entity(entity)` |
| 需要包含用户扩展字段 | `Response.from_dict(entity.to_dict())` |

### 转换为字典

```python
user_dto = UserDTO(id=1, username="tom", email="tom@example.com")

# 转换为字典
user_dict = user_dto.to_dict()
print(user_dict)
# {'id': 1, 'username': 'tom', 'email': 'tom@example.com'}

# 也可以使用 dict()
user_dict = dict(user_dto)
```

### 嵌套 DTO

DTO 支持嵌套结构，`to_dict()` 会自动递归转换嵌套的 DTO 对象：

```python
class UserDTO(DTO):
    id: int
    username: str
    email: str

class LoginResponseDTO(DTO):
    access_token: str
    refresh_token: str
    token_type: str
    user: UserDTO  # 嵌套 DTO

# 使用
user_dto = UserDTO.from_entity(user)
response = LoginResponseDTO(
    access_token="xxx",
    refresh_token="yyy",
    token_type="bearer",
    user=user_dto
)

# to_dict() 自动转换嵌套 DTO
print(response.to_dict())
# {
#     'access_token': 'xxx',
#     'refresh_token': 'yyy',
#     'token_type': 'bearer',
#     'user': {'id': 1, 'username': 'tom', 'email': 'tom@example.com'}
# }
```

### 字段名映射

当 API 输出字段名与 DTO 属性名不一致时，使用 `_field_mapping` 进行映射：

```python
class UserDTO(DTO):
    id: int
    user_name: str      # DTO 属性名
    email_address: str
    phone_number: str
    is_active: bool

    # 定义字段映射：DTO属性名 -> 输出字段名
    _field_mapping = {
        "user_name": "username",
        "email_address": "email",
        "phone_number": "phone"
    }

user_dto = UserDTO(
    id=1,
    user_name="tom",
    email_address="tom@example.com",
    phone_number="13800138000",
    is_active=True
)
print(user_dto.to_dict())
# {
#     'id': 1,
#     'username': 'tom',        # 映射后的字段名
#     'email': 'tom@example.com',
#     'phone': '13800138000',
#     'is_active': True
# }
```

### 字段值处理器

使用 `_value_processors` 对字段值进行自定义转换。
处理器在 `from_entity()` / `from_dict()` 创建 DTO 时执行，
**字段类型声明应与处理器转换后的类型一致**：

```python
class UserDTO(DTO):
    id: int
    username: str
    is_active: str       # 处理后是字符串，声明为 str
    status: str          # 处理后是字符串，声明为 str

    # 定义值处理器：字段名 -> 处理函数
    # 在 from_entity/from_dict 创建时执行
    _value_processors = {
        "is_active": lambda x: "active" if x else "inactive",
        "status": lambda x: {0: "pending", 1: "approved", 2: "rejected"}.get(x, "unknown")
    }

user_dto = UserDTO.from_entity(user_entity)
print(user_dto.to_dict())
# {
#     'id': 1,
#     'username': 'tom',
#     'is_active': 'active',    # 布尔值转换为字符串
#     'status': 'approved'       # 状态码转换为描述
# }
```

#### datetime 自动格式化

DTO 内置了 datetime 格式化处理器，当字段类型为 `str` 但实体值为 `datetime` 时，会自动格式化：

```python
class UserDTO(DTO):
    id: int
    username: str
    created_at: str  # 字段类型为 str

# from_entity 会自动将 datetime 格式化为 "YYYY-MM-DD HH:MM:SS"
user_dto = UserDTO.from_entity(user)
print(user_dto.created_at)  # "2024-01-15 10:30:45"
```

也可以使用 `_format_datetime` 静态方法自定义处理：

```python
_value_processors = {
    "created_at": DTO._format_datetime
}
```

### DTO 方法

```python
class UserDTO(DTO):
    id: int
    username: str

user_dto = UserDTO(id=1, username="tom")

# keys() 和 values()
print(user_dto.keys())    # ['id', 'username']
print(user_dto.values())  # [1, 'tom']

# 迭代
for key, value in user_dto:
    print(f"{key}: {value}")
```

## OK() 自动序列化

### 基本用法

YWeb 的 `OK()` 响应函数支持自动序列化 SQLAlchemy 模型：

```python
from yweb import OK

@app.get("/users/{user_id}")
def get_user(user_id: int):
    user = User.get(user_id)
    return OK(user)  # 自动调用 to_dict()
```

### 列表序列化

```python
@app.get("/users")
def list_users():
    users = User.get_all()
    return OK(users)  # 自动序列化列表
```

### 分页结果序列化

```python
@app.get("/users")
def list_users(page: int = 1, page_size: int = 10):
    page_result = User.query.paginate(page=page, page_size=page_size)
    return OK(page_result)  # 自动序列化 Page 对象
```

### 注意事项

```python
# OK() 自动序列化只包含模型的列字段，不包含 relationship 关联数据
return OK(user)  # 不包含 user.roles

# 如需关联数据，使用 to_dict_with_relations
return OK(user.to_dict_with_relations(relations=['roles']))
```

## 日期时间处理

### DateTimeStr 类型

```python
from yweb.orm import DateTimeStr, format_datetime_to_string

# 格式化日期时间
dt = datetime(2024, 1, 15, 10, 30, 45)
result = format_datetime_to_string(dt)
print(result)  # "2024-01-15 10:30:45"

# None 值处理
result = format_datetime_to_string(None)
print(result)  # None
```

### 自定义日期格式

```python
class User(BaseModel):
    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)

        # 自定义日期格式
        if data.get('created_at'):
            data['created_at'] = data['created_at'].strftime('%Y-%m-%d')

        return data
```

## Pydantic Schema 集成

### BaseSchemas

```python
from yweb.orm import BaseSchemas

class UserSchema(BaseSchemas):
    id: int
    username: str
    email: str

# 从 ORM 对象创建
user = User.get(1)
user_schema = UserSchema.model_validate(user)
```

### 在分页中使用

```python
class UserSchema(BaseSchemas):
    id: int
    username: str
    email: str

# 分页时自动转换
page_result = User.query.paginate(
    page=1,
    page_size=10,
    schema=UserSchema
)
# page_result.rows 中的数据会自动转换为 UserSchema
```

## 最佳实践

### 1. 定义响应 Schema

```python
from pydantic import BaseModel as PydanticModel

class UserResponse(PydanticModel):
    id: int
    username: str
    email: str
    created_at: str

    model_config = {"from_attributes": True}

@app.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: int):
    user = User.get(user_id)
    return user
```

### 2. 排除敏感字段

```python
# 在模型中定义默认排除
class User(BaseModel):
    EXCLUDE_FIELDS = {'password', 'salt', 'deleted_at'}

    def to_dict(self, exclude=None):
        if exclude is None:
            exclude = set()
        exclude.update(self.EXCLUDE_FIELDS)
        return super().to_dict(exclude=exclude)
```

### 3. 使用 DTO 分离关注点

```python
# 列表 DTO（简化）
class UserListDTO(DTO):
    id: int
    username: str

# 详情 DTO（完整）
class UserDetailDTO(DTO):
    id: int
    username: str
    email: str
    created_at: datetime
    roles: list
```

### 4. 统一响应格式

```python
@app.get("/users/{user_id}")
def get_user(user_id: int):
    user = User.get(user_id)
    if not user:
        return NotFound("用户不存在")
    return OK(user.to_dict(exclude={'password'}))
```

## 常见问题

### Q1: 如何序列化嵌套关联？

```python
user_dict = user.to_dict_with_relations(
    relations=['roles', 'department', 'profile']
)
```

### Q2: 如何处理循环引用？

```python
# 使用 exclude 排除反向引用
class User(BaseModel):
    def to_dict_with_relations(self, relations=None, exclude=None):
        if exclude is None:
            exclude = set()
        # 排除可能导致循环的字段
        exclude.add('department.users')
        return super().to_dict_with_relations(relations, exclude)
```

### Q3: 如何自定义字段名？

```python
class User(BaseModel):
    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)
        # 重命名字段
        data['user_name'] = data.pop('username', None)
        return data
```

### Q4: 如何添加计算字段？

```python
class User(BaseModel):
    def to_dict(self, exclude=None):
        data = super().to_dict(exclude=exclude)
        # 添加计算字段
        data['full_name'] = f"{self.first_name} {self.last_name}"
        data['is_admin'] = 'admin' in [r.name for r in self.roles]
        return data
```

## 下一步

- [14_Schema与验证](14_schema_validation.md) - 学习 Schema 验证
- [15_FastAPI集成](15_fastapi_integration.md) - 了解 FastAPI 集成
