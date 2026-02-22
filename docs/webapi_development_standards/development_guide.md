# yweb API 与 Service 层开发规范

本文档定义了基于 yweb 框架的 API 层和 Service 层开发规范。

---

## 目录

1. [项目结构](#1-项目结构)
2. [API 层开发规范](#2-api-层开发规范)
3. [Service 层开发规范](#3-service-层开发规范)
4. [完整示例](#4-完整示例)

---

## 1. 项目结构

```
app/
├── api/
│   └── v1/
│       ├── __init__.py
│       ├── users.py          # API 路由层
│       └── login_record.py
├── domain/
│   └── auth/
│       ├── __init__.py
│       ├── entities.py       # ORM 实体
│       ├── user_service.py   # Service 层
│       └── model/
│           └── user.py
└── utils/
```

---

## 2. API 层开发规范

### 2.1 导入规范

```python
from fastapi import APIRouter, HTTPException, status as http_status, Query
from typing import Optional, List
from pydantic import BaseModel

from app.domain.auth import UserService, Username, Email, PhoneNumber, Password
from app.domain.auth.model.user import User
from yweb import Resp, PageResponse, DTO
```

> **注意**：使用 `status as http_status` 避免与函数参数名冲突。

### 2.2 DTO（数据传输对象）定义

#### 响应 DTO

继承 `DTO` 类，利用 `_field_mapping` 和 `_value_processors` 进行字段转换。

> **注意：`DTO` 继承自 Pydantic `BaseModel`，请勿在 DTO 子类上使用 `@dataclass` 或 `@dataclass(frozen=True)` 装饰器，两者的元类机制冲突。** 如需不可变行为，使用 `model_config = ConfigDict(frozen=True)`。

```python
class UserResponse(DTO):
    """用户响应模型"""
    id: int = 0
    username: str = ""
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    is_active: str = "active"   # 处理后是字符串
    created_at: str = ""
    
    # 字段名映射：输出时 is_active -> status
    _field_mapping = {'is_active': 'status'}
    
    # 值处理器：from_entity 创建时转换值
    # 字段类型应与转换后的类型一致
    _value_processors = {
        'is_active': lambda v: 'active' if v else 'inactive',
    }
```

**DTO 特性说明**：

| 特性 | 说明 | 示例 |
|------|------|------|
| `_field_mapping` | 输出时重命名字段 | `{'is_active': 'status'}` |
| `_value_processors` | 创建时转换字段值（字段类型应与转换后一致） | `{'is_active': lambda v: 'active' if v else 'inactive'}` |
| `from_entity()` | 单个实体转换 | `UserResponse.from_entity(user)` |
| `from_list()` | 简单列表转换（不分页） | `UserResponse.from_list(users)` |
| `from_page()` | 分页列表转换 | `UserResponse.from_page(page_result)` |
| `from_tree()` | 树形结构转换 | `MenuResponse.from_tree(menus)` |
| `from_dict()` | 从字典创建（自动忽略额外字段） | `JobResponse.from_dict(job_dict)` |

**DTO 转换方法选择**：

| 场景 | 方法 | 返回值 |
|------|------|--------|
| 单个对象详情 | `from_entity()` | DTO 实例 |
| 下拉选项、不分页列表 | `from_list()` | DTO 列表 |
| 分页查询列表 | `from_page()` | 分页字典 |
| 菜单、组织架构等层级数据 | `from_tree()` | 树形字典列表 |
| 从字典创建（外部 API、内部方法返回） | `from_dict()` | DTO 实例 |

#### 请求模型

请求模型继承 Pydantic `BaseModel`：

```python
class CreateUserRequest(BaseModel):
    """创建用户请求模型"""
    username: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    password: str
    status: str = "active"


class UpdateUserRequest(BaseModel):
    """更新用户请求模型"""
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    status: str
```

### 2.3 响应类型定义

使用泛型 `PageResponse[T]` 定义分页响应类型（用于 OpenAPI 文档）：

```python
# 分页响应类型
UserListResponse = PageResponse[UserResponse]

@router.get("/", response_model=UserListResponse)
def get_users(...):
    ...
```

### 2.4 DTO 转换方法

```python
# 1. 单个对象
user = UserResponse.from_entity(entity)
return Resp.OK(user)

# 2. 简单列表（下拉选项等，不分页）
roles = RoleResponse.from_list(role_entities)
return Resp.OK(roles)

# 3. 分页列表
page_result = User.query.paginate(page=1, page_size=10)
return Resp.OK(UserResponse.from_page(page_result))

# 4. 树形结构（菜单、组织架构等）
class MenuResponse(DTO):
    id: int
    name: str
    parent_id: Optional[int] = None

menus = Menu.query.all()
tree = MenuResponse.from_tree(menus)
return Resp.OK(tree)
```

### 2.5 API 路由实现

```python
@router.get("/", response_model=UserListResponse)
def get_users(
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    status: Optional[str] = Query(None, description="用户状态 (active, inactive)"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
):
    """获取用户列表"""
    try:
        # 1. 创建 Service 实例
        user_service = UserService()
        
        # 2. 调用 Service 方法获取分页结果
        page_result = user_service.search_users(
            keyword=keyword,
            status=status,
            page=page,
            page_size=page_size
        )
        
        # 3. 使用 DTO 转换并返回标准响应
        return Resp.OK(UserResponse.from_page(page_result))
        
    except ValueError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取用户列表失败: {str(e)}"
        )
```

### 2.6 响应格式

#### 成功响应

使用 `Resp.OK()` 返回标准格式：

```python
# 单个对象
return Resp.OK(UserResponse.from_entity(user))

# 简单列表
return Resp.OK(RoleResponse.from_list(roles))

# 分页列表
return Resp.OK(UserResponse.from_page(page_result))

# 树形结构
return Resp.OK(MenuResponse.from_tree(menus))

# 自定义数据
return Resp.OK({"id": user.id, "username": user.username})
```

**参数写法**：`Resp.OK()` 的签名为 `def OK(data: Any = None, message: str = "请求成功")`，以下写法等效：

```python
Resp.OK(data=user, message="创建成功")  # 完整写法
Resp.OK(user, message="创建成功")       # 省略 data=（推荐）
Resp.OK(user, "创建成功")               # 全部位置参数
```

响应格式：

```json
{
    "status": "success",
    "message": "请求成功",
    "msg_details": [],
    "data": {
        "rows": [...],
        "total_records": 100,
        "page": 1,
        "page_size": 10,
        "total_pages": 10,
        "has_prev": false,
        "has_next": true
    }
}
```

#### 错误响应

使用 `HTTPException` 或 `Resp` 系列方法：

```python
# 方式1：HTTPException
raise HTTPException(
    status_code=http_status.HTTP_404_NOT_FOUND,
    detail="用户不存在"
)

# 方式2：Resp 方法
return Resp.NotFound(message="用户不存在")
return Resp.BadRequest(message="参数错误", msg_details=["username 不能为空"])
```

---

## 3. Service 层开发规范

### 3.1 值对象定义

使用 `@dataclass(frozen=True)` 定义不可变值对象，封装验证逻辑：

```python
from dataclasses import dataclass
import re

@dataclass(frozen=True)
class Username:
    """用户名值对象"""
    value: str
    
    def __post_init__(self):
        if not self._is_valid_username(self.value):
            raise ValueError("用户名必须是1-20个字符，支持中文、字母、数字、下划线")
    
    @staticmethod
    def _is_valid_username(username: str) -> bool:
        if len(username) < 1 or len(username) > 20:
            return False
        username_regex = r"^[\u4e00-\u9fa5a-zA-Z0-9_]+$"
        return bool(re.match(username_regex, username))


@dataclass(frozen=True)
class Email:
    """邮箱值对象"""
    value: str
    
    def __post_init__(self):
        if not self._is_valid_email(self.value):
            raise ValueError(f"无效的邮箱格式: {self.value}")
    
    @staticmethod
    def _is_valid_email(email: str) -> bool:
        email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return bool(re.match(email_regex, email))


@dataclass(frozen=True)
class Password:
    """密码值对象"""
    value: str
    
    def __post_init__(self):
        if not self._is_valid_password(self.value):
            raise ValueError("密码必须至少包含8个字符，包含大小写字母、数字和特殊字符")
    
    @staticmethod
    def _is_valid_password(password: str) -> bool:
        if len(password) < 8:
            return False
        if not re.search(r"[A-Z]", password):
            return False
        if not re.search(r"[a-z]", password):
            return False
        if not re.search(r"[0-9]", password):
            return False
        if not re.search(r"[!@#$%^&*(),.?;:{}|<>+\-_=\[\]\\/'\"~`]", password):
            return False
        return True
```

### 3.2 Service 类定义

```python
from typing import Optional
from .entities import User

class UserService:
    """用户服务"""
    
    def create_user(
        self, 
        username: Username, 
        password: Password, 
        email: Optional[str] = None, 
        phone: Optional[str] = None
    ) -> User:
        """创建用户
        
        Args:
            username: 用户名值对象
            password: 密码值对象
            email: 邮箱（可选）
            phone: 手机号（可选）
            
        Returns:
            创建的用户实体
            
        Raises:
            ValueError: 参数验证失败
        """
        from yweb.auth import PasswordHelper
        
        user = User(
            username=username.value,
            password_hash=PasswordHelper.hash(password.value),
            email=email,
            phone=phone,
            is_active=True
        )
        user.add(True)
        return user
    
    def search_users(
        self, 
        keyword: Optional[str] = None, 
        status: Optional[str] = None,
        page: int = 1, 
        page_size: int = 10
    ):
        """搜索用户
        
        Args:
            keyword: 搜索关键词（用户名、邮箱、手机号）
            status: 用户状态（active/inactive）
            page: 页码
            page_size: 每页数量
            
        Returns:
            分页结果对象（包含 items, total, page, page_size 等属性）
        """
        # 1. 创建基础查询
        query = User.query.order_by(User.created_at.desc())
        
        # 2. 应用过滤条件
        if keyword:
            query = query.filter(
                User.username.ilike(f"%{keyword}%") |
                User.name.ilike(f"%{keyword}%") |
                User.email.ilike(f"%{keyword}%") |
                User.phone.ilike(f"%{keyword}%")
            )
        
        if status:
            is_active = status == 'active'
            query = query.filter(User.is_active == is_active)
        
        # 3. 使用 paginate 方法获取分页结果
        page_result = query.paginate(page=page, page_size=page_size)
        return page_result
```

### 3.3 分页查询规范

使用 ORM 的 `paginate()` 方法：

```python
# 链式查询 + 分页
page_result = User.query \
    .filter(User.is_active == True) \
    .order_by(User.created_at.desc()) \
    .paginate(page=page, page_size=page_size)

# page_result 包含以下属性：
# - rows: 当前页数据列表
# - total_records: 总记录数
# - page: 当前页码
# - page_size: 每页数量
# - total_pages: 总页数
# - has_prev: 是否有上一页
# - has_next: 是否有下一页
```

---

## 4. 完整示例

### 4.1 API 层完整示例

```python
# app/api/v1/users.py

from fastapi import APIRouter, HTTPException, status as http_status, Query
from typing import Optional
from pydantic import BaseModel

from app.domain.auth import UserService, Username, Password
from app.domain.auth.model.user import User
from yweb import Resp, PageResponse, DTO

router = APIRouter(prefix="/users", tags=["users"])


# ========== DTO 定义 ==========

class UserResponse(DTO):
    """用户响应 DTO"""
    id: int = 0
    username: str = ""
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    is_active: str = "active"
    created_at: str = ""
    
    _field_mapping = {'is_active': 'status'}
    _value_processors = {
        'is_active': lambda v: 'active' if v else 'inactive',
    }

UserListResponse = PageResponse[UserResponse]


class CreateUserRequest(BaseModel):
    """创建用户请求"""
    username: str
    password: str
    name: str
    email: Optional[str] = None


# ========== API 路由 ==========

@router.get("/", response_model=UserListResponse)
def get_users(
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    status: Optional[str] = Query(None, description="状态"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    """获取用户列表"""
    try:
        user_service = UserService()
        page_result = user_service.search_users(
            keyword=keyword,
            status=status,
            page=page,
            page_size=page_size
        )
        return Resp.OK(UserResponse.from_page(page_result))
    except Exception as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{user_id}")
def get_user(user_id: int):
    """获取用户详情"""
    user = User.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    return Resp.OK(UserResponse.from_entity(user))


@router.post("/", status_code=http_status.HTTP_201_CREATED)
def create_user(request: CreateUserRequest):
    """创建用户"""
    try:
        user_service = UserService()
        username = Username(request.username)
        password = Password(request.password)
        
        user = user_service.create_user(
            username=username,
            password=password,
            email=request.email
        )
        
        if request.name:
            user.name = request.name
            user.update()
        
        return Resp.OK(UserResponse.from_entity(user), message="用户创建成功")
        
    except ValueError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
```

### 4.2 Service 层完整示例

```python
# app/domain/auth/user_service.py

from dataclasses import dataclass
from typing import Optional
import re
from .entities import User


@dataclass(frozen=True)
class Username:
    """用户名值对象"""
    value: str
    
    def __post_init__(self):
        if not self._is_valid(self.value):
            raise ValueError("用户名格式无效")
    
    @staticmethod
    def _is_valid(username: str) -> bool:
        if len(username) < 1 or len(username) > 20:
            return False
        return bool(re.match(r"^[\u4e00-\u9fa5a-zA-Z0-9_]+$", username))


@dataclass(frozen=True)
class Password:
    """密码值对象"""
    value: str
    
    def __post_init__(self):
        if len(self.value) < 8:
            raise ValueError("密码长度不能少于8位")


class UserService:
    """用户服务"""
    
    def create_user(
        self, 
        username: Username, 
        password: Password,
        email: Optional[str] = None
    ) -> User:
        """创建用户"""
        from yweb.auth import PasswordHelper
        
        user = User(
            username=username.value,
            password_hash=PasswordHelper.hash(password.value),
            email=email,
            is_active=True
        )
        user.add(True)
        return user
    
    def search_users(
        self,
        keyword: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 10
    ):
        """搜索用户"""
        query = User.query.order_by(User.created_at.desc())
        
        if keyword:
            query = query.filter(
                User.username.ilike(f"%{keyword}%") |
                User.email.ilike(f"%{keyword}%")
            )
        
        if status:
            query = query.filter(User.is_active == (status == 'active'))
        
        return query.paginate(page=page, page_size=page_size)
```

---

## 5. 最佳实践总结

### API 层

| 规范 | 说明 |
|------|------|
| 使用 `DTO` 定义响应模型 | 继承 `DTO`，利用 `_field_mapping` 和 `_value_processors` |
| 使用 `PageResponse[T]` | 定义分页响应的 OpenAPI 文档类型 |
| 使用 `Resp.OK()` | 返回标准化响应格式 |
| 使用 `status as http_status` | 避免与参数名冲突 |

### DTO 转换方法

| 方法 | 用途 | 示例 |
|------|------|------|
| `from_entity()` | 单个对象 | `UserResponse.from_entity(user)` |
| `from_list()` | 简单列表 | `RoleResponse.from_list(roles)` |
| `from_page()` | 分页列表 | `UserResponse.from_page(page_result)` |
| `from_tree()` | 树形结构 | `MenuResponse.from_tree(menus)` |

### Service 层

| 规范 | 说明 |
|------|------|
| 使用值对象封装验证 | `@dataclass(frozen=True)` 定义不可变值对象 |
| Service 返回 ORM 对象 | 让 API 层负责 DTO 转换 |
| 使用 `paginate()` 分页 | 返回标准分页结果对象 |
| 业务逻辑集中在 Service | API 层只做参数处理和响应转换 |
