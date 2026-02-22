# 快速开始

本指南将帮助你快速上手 YWeb。

## 安装

### 前置要求

- Python >= 3.8
- pip

### 从本地安装(开发模式)

```bash
# 1. 克隆仓库
git clone <repository-url>
cd yweb-core

# 2. 安装
pip install -e .
```

## 创建第一个应用

### 1. 基础示例

创建 `main.py`：

```python
from fastapi import FastAPI
from yweb import Resp, RequestIDMiddleware

app = FastAPI(title="My First App")

# 添加请求ID中间件
app.add_middleware(RequestIDMiddleware)

@app.get("/")
def read_root():
    return Resp.OK(data={"message": "Hello World"}, message="欢迎使用")

@app.get("/users/{user_id}")
def get_user(user_id: int):
    if user_id == 1:
        return Resp.OK(data={"id": 1, "name": "Tom", "age": 25}, message="查询成功")
    return Resp.NotFound(message="用户不存在")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

**参数写法**：以 `Resp.OK()`为例 ，签名为 `def OK(data: Any = None, message: str = "请求成功")`，以下写法等效：

```python
# 假设 user 是一个用户对象或字典
user = {"id": 1, "name": "Tom"}

# 完整写法
Resp.OK(data=user, message="创建成功")

# 省略 data= 
Resp.OK(user, message="创建成功")

# 省略 全部位置参数
Resp.OK(user, "创建成功")
```

### 2. 运行应用

```bash
python main.py
```

访问 `http://localhost:8000/users/1`，你将看到：

```json
{
    "status": "success",
    "message": "查询成功",
    "msg_details": [],
    "data": {
        "id": 1,
        "name": "Tom",
        "age": 25
    }
}
```

## 配置日志

```python
from yweb import setup_logger
import os

# 确保日志目录存在
os.makedirs("logs", exist_ok=True)

# 方式 1：配置根 logger（简单，所有日志都会输出）
setup_logger(level="INFO", console=True)  # 不指定 name，配置根 logger
logger = setup_logger(name="my_app", level="INFO", log_file="logs/app.log")  # 业务日志写入文件

# 方式 2：分别配置（推荐，更清晰）
setup_logger(name="yweb", level="INFO", console=True)  # 给中间件用
logger = setup_logger(name="my_app", level="INFO", log_file="logs/app.log", console=True)  # 给业务代码用

@app.on_event("startup")
def startup_event():
    logger.info("Application is starting up...")
```

> **说明：** 
> - 不指定 `name` 参数会配置根 logger，所有日志（包括 yweb 中间件）都会输出
> - 分别配置 `yweb` 和 `my_app` logger 可以更精确地控制日志输出
> - 详细的日志配置请参考 [日志指南](04_log_guide.md)

## 添加中间件

```python
from yweb import RequestIDMiddleware, RequestLoggingMiddleware, PerformanceMonitoringMiddleware

app.add_middleware(RequestIDMiddleware)

# 添加请求日志中间件
app.add_middleware(
    RequestLoggingMiddleware,
    max_body_size=1024 * 1024 * 5,  # 5MB，最大请求体记录大小
    skip_paths={"/health", "/metrics"}  # Set[str]，跳过日志记录的路径集合
)

# 添加性能监控中间件
app.add_middleware(
    PerformanceMonitoringMiddleware,
    slow_request_threshold=2.0  # 超过2秒记录警告
)
```

## 使用 DTO 和分页

### DTO 定义

DTO（数据传输对象）继承自 `yweb.orm.DTO`，用于 API 响应的数据序列化：

```python
from typing import Optional
from yweb import DTO

class UserDTO(DTO):
    """用户响应 DTO"""
    id: int = 0
    name: str = ""
    email: Optional[str] = None
```

> **说明**：
> - DTO 基于 Pydantic BaseModel，字段需要提供默认值
> - 详细配置请参考 [DTO 与响应处理规范](webapi项目开发规范/dto_response_guide.md)

### 分页查询

实际开发中，配合 ORM 使用分页功能：

```python
from fastapi import Query
from yweb import Resp, DTO, PageResponse, BaseModel
from sqlalchemy import Column, Integer, String, Boolean

# 定义 User 模型（继承自 BaseModel）
class User(BaseModel):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(50))
    email = Column(String(100))
    is_active = Column(Boolean, default=True)

# 定义 UserDTO
class UserDTO(DTO):
    id: int = 0
    name: str = ""
    email: str = ""

# 定义分页响应类型（用于 OpenAPI 文档）
UserPageResponse = PageResponse[UserDTO]

@app.get("/users", response_model=UserPageResponse)
def list_users(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
):
    page_result = User.query.order_by(User.id).paginate(
        page=page, page_size=page_size
    )
    return Resp.OK(UserDTO.from_page(page_result))
```

> **说明**：User 模型需要继承自 `BaseModel` 或 `CoreModel`，详细的模型定义请参考 [ORM 使用指南](03_orm_guide.md)

### DTO 转换方法

| 方法 | 数据源 | 适用场景 |
|------|--------|----------|
| `from_entity(entity)` | ORM 对象 | 单个对象详情 |
| `from_list(items)` | 列表 | 不分页列表 |
| `from_page(page_result)` | 分页结果对象 | 分页查询 |
| `from_dict(dict)` | 字典 | 从字典创建 |

```python
# 单个对象
user = User.get(1)
return Resp.OK(UserDTO.from_entity(user))

# 列表（不分页）
users = User.query.filter(User.is_active == True).all()
return Resp.OK(UserDTO.from_list(users))

# 从字典创建
user_dict = {"id": 1, "name": "Tom", "email": "tom@example.com"}
return Resp.OK(UserDTO.from_dict(user_dict))
```

## 下一步

- 查看 [DTO 与响应处理规范](webapi项目开发规范/dto_response_guide.md)
- 查看 [API 开发规范](webapi项目开发规范/development_guide.md)
- 查看 [ORM 使用指南](03_orm_guide.md)
- 查看 [日志指南](04_log_guide.md)

