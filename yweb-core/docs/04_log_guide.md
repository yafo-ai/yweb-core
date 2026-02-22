# 日志模块使用指南

yweb 框架提供了完整的日志解决方案，包括：
- 自动推断模块名的日志记录器
- 时间+大小双重轮转的日志处理器
- 带写缓存的高性能处理器
- 敏感数据过滤

---

## 目录

- [快速开始](#快速开始)
- [get_logger 详细用法](#get_logger-详细用法)
- [预定义日志记录器](#预定义日志记录器)
- [日志配置](#日志配置)
- [日志层级继承](#日志层级继承)
- [自定义日志处理器](#自定义日志处理器)
- [敏感数据过滤](#敏感数据过滤)
- [最佳实践](#最佳实践)
- [API 参考](#api-参考)

---

## 快速开始

### 获取日志记录器（推荐方式）

使用 `get_logger()` 自动推断当前模块名，无需手动指定：

```python
from yweb.log import get_logger

# 自动推断模块名（推荐，零硬编码）
logger = get_logger()

# 使用日志记录器
logger.info("这是一条日志消息")
logger.error("发生错误", exc_info=True)
```

### 自动推断规则

| 调用位置 | 自动推断的 logger 名称 |
|---------|------------------------|
| `yweb/orm/db_session.py` | `yweb.orm.db_session` |
| `yweb/middleware/auth.py` | `yweb.middleware.auth` |
| `app/api/v1/users.py` | `app.api.v1.users` |

---

## get_logger 详细用法

### 1. 自动推断（推荐）

```python
from yweb.log import get_logger

# 无参数调用，自动使用当前模块的 __name__
logger = get_logger()
```

### 2. 显式指定（简写）

```python
from yweb.log import get_logger

# 简写会自动添加 yweb 前缀
logger = get_logger("api")        # -> "yweb.api"
logger = get_logger("orm")        # -> "yweb.orm"
logger = get_logger("auth")       # -> "yweb.auth"
```

### 3. 显式指定（完整名称）

```python
from yweb.log import get_logger

# 已有 yweb 前缀不重复添加
logger = get_logger("yweb.custom")           # -> "yweb.custom"
logger = get_logger("yweb.orm.transaction")  # -> "yweb.orm.transaction"
```

### 4. 外部模块日志

```python
from yweb.log import get_logger

# 包含点号的外部模块名不添加 yweb 前缀
logger = get_logger("sqlalchemy.engine")  # -> "sqlalchemy.engine"
logger = get_logger("uvicorn.access")     # -> "uvicorn.access"
```

---

## 预定义日志记录器

为了向后兼容，框架提供了一些预定义的日志记录器：

```python
from yweb.log import (
    api_logger,          # yweb.api
    auth_logger,         # yweb.auth
    sql_logger,          # yweb.sql
    orm_logger,          # yweb.orm
    transaction_logger,  # yweb.orm.transaction
    logger,              # yweb（根日志器）
)
```

> **推荐**：新代码直接使用 `get_logger()` 自动推断，减少硬编码。

---

## 日志配置

### 配置根日志记录器

```python
from yweb.log import setup_root_logger

# 方式1：传统参数
logger = setup_root_logger(
    level="INFO",
    log_file="logs/app.log",
    console=True
)

# 方式2：配置对象（推荐）
logger = setup_root_logger(
    config=settings.logging,
    console=True
)

# 方式3：配置文件路径
logger = setup_root_logger(
    config_path="config/settings.yaml"
)
```

### 配置 SQL 日志

```python
from yweb.log import setup_sql_logger

# 单独配置 SQL 日志（输出到独立文件）
sql_logger = setup_sql_logger(
    level="DEBUG",
    log_file="logs/sql.log",
    console=False
)
```

---

## 日志层级继承

Python logging 模块支持层级继承，yweb 框架利用这一特性：

```
yweb                              <- 根配置
├── yweb.api                      <- 继承 yweb 配置
├── yweb.auth                     <- 继承 yweb 配置
├── yweb.orm                      <- 继承 yweb 配置
│   ├── yweb.orm.db_session       <- 继承 yweb.orm 配置
│   └── yweb.orm.transaction      <- 继承 yweb.orm 配置
└── yweb.middleware
    ├── yweb.middleware.request_logging
    └── yweb.middleware.performance
```

只需配置 `yweb` 根日志器，所有子日志器自动继承配置。

---

## 自定义日志处理器

### 时间+大小双重轮转

```python
from yweb.log import TimeAndSizeRotatingFileHandler

handler = TimeAndSizeRotatingFileHandler(
    filename="logs/app_{date}.log",
    maxBytes=10*1024*1024,    # 10MB
    backupCount=5,
    encoding="utf-8",
    when="midnight",          # 每天轮转
    interval=1,
    maxRetentionDays=30,      # 保留最近30天
    maxTotalBytes=1024*1024*1024  # 总大小限制1GB
)
```

**关键参数说明：**

- **`backupCount=5`**：当天日志文件大小切分的数量限制
  - 当单个日志文件达到 `maxBytes`（10MB）时，会自动切分成新文件
  - 轮转时所有备份文件序号递增：`.1` → `.2`，`.2` → `.3`，依此类推
  - `.1` 永远是最新的备份，序号越大内容越旧
  - 最多保留 5 个序号备份，第 6 个（最旧的）会被删除
  - 作用：防止单个日志文件过大，便于查看和传输

- **`maxRetentionDays=30`**：历史日志保留天数
  - 只删除超过 30 天的历史日期文件
  - 当天的所有文件（主文件和序号备份）不会被删除
  - 例如：2026-01-28 运行时，会删除 2025-12-28 及之前的日志

- **`maxTotalBytes=1GB`**：所有日志文件总大小限制
  - 超过限制时，优先删除最旧的历史日期文件
  - 当天的所有文件受保护，不会被删除
  - 确保当天日志完整性

### 每日轮转

```python
from yweb.log import DailyRotatingFileHandler

handler = DailyRotatingFileHandler(
    filename="logs/app_{date}.log",
    backupCount=30,           # 保留30天
    encoding="utf-8",
    maxRetentionDays=30       # 自动清理超过30天的日志
)
```

### 带写缓存的处理器（高性能）

适用于高并发场景，通过批量写入提升性能：

```python
from yweb.log import BufferedRotatingFileHandler
import logging

handler = BufferedRotatingFileHandler(
    filename="logs/app_{date}.log",
    maxBytes=10*1024*1024,     # 10MB
    backupCount=5,
    bufferCapacity=100,        # 缓存100条后刷新
    flushInterval=5.0,         # 或每5秒刷新
    flushLevel=logging.ERROR   # ERROR及以上立即刷新
)
```

**缓冲处理器特性：**
- 批量写入：累积指定数量的日志后一次性写入
- 定时刷新：后台线程定期刷新缓冲区
- 级别刷新：ERROR/CRITICAL 级别日志立即落盘
- 优雅关闭：程序退出时确保所有日志落盘

### 带写缓存的每日轮转

```python
from yweb.log import BufferedDailyRotatingFileHandler

handler = BufferedDailyRotatingFileHandler(
    filename="logs/app_{date}.log",
    maxRetentionDays=30,
    bufferCapacity=100,
    flushInterval=5.0
)
```

### 处理器参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `filename` | 日志文件名模板，使用 `{date}` 作为日期占位符 | - |
| `maxBytes` | 单个文件最大字节数，0 表示不限制 | 0 |
| `backupCount` | 保留的备份文件数量 | 0 |
| `encoding` | 文件编码 | None |
| `when` | 时间轮转策略，目前仅支持 "midnight" | "midnight" |
| `interval` | 轮转间隔（天数） | 1 |
| `maxRetentionDays` | 日志保留天数，0 表示不限制 | 0 |
| `maxTotalBytes` | 日志文件总大小限制，0 表示不限制 | 0 |
| `bufferCapacity` | 缓冲区容量（条数） | 100 |
| `flushInterval` | 刷新间隔（秒） | 5.0 |
| `flushLevel` | 触发立即刷新的日志级别 | ERROR |

---

## 敏感数据过滤

yweb 框架提供了日志敏感数据过滤功能，可以自动检测并过滤日志中的敏感信息（如密码、token、密钥等），保护用户隐私和系统安全。

### 默认行为（自动启用）

使用 `RequestLoggingMiddleware` 时，敏感数据过滤**默认启用**：

```python
from fastapi import FastAPI
from yweb.middleware import RequestLoggingMiddleware

app = FastAPI()

# 敏感数据过滤默认启用
app.add_middleware(RequestLoggingMiddleware)
```

### 禁用敏感数据过滤

```python
app.add_middleware(
    RequestLoggingMiddleware,
    enable_sensitive_filter=False  # 禁用敏感数据过滤
)
```

### 默认过滤规则

#### 敏感字段名模式

以下字段名会被自动过滤（不区分大小写）：

| 模式 | 匹配示例 |
|-----|---------|
| `.*password.*` 或 `.*pwd.*` 或 `.*passwd.*` | password, user_password, oldPwd |
| `.*token.*` 或 `.*access_token.*` 或 `.*refresh_token.*` | token, access_token |
| `.*secret.*` 或 `.*key.*` 或 `.*apikey.*` 或 `.*api_key.*` | secret, apiKey |
| `.*credential.*` | credential, credentials |
| `.*auth.*` 或 `.*authentication.*` | auth, authentication |

#### 敏感 URL 路径

以下路径的请求体会被深度过滤：

- `/auth/login`
- `/auth/token`
- `/admin/login`

### 过滤效果示例

**原始日志数据：**

```json
{
  "url": "/auth/login",
  "request_body_preview": {
    "username": "admin",
    "password": "123456",
    "remember_me": true
  }
}
```

**过滤后日志数据：**

```json
{
  "url": "/auth/login",
  "request_body_preview": {
    "username": "admin",
    "password": "*SENSITIVE DATA FILTERED*",
    "remember_me": true
  }
}
```

### 自定义过滤规则

#### 添加自定义敏感字段

```python
from yweb.log import SensitiveDataFilterHook, log_filter_hook_manager

# 创建自定义过滤器
custom_filter = SensitiveDataFilterHook(
    sensitive_patterns=[
        r'.*password.*',
        r'.*credit_card.*',      # 信用卡
        r'.*card_number.*',      # 卡号
        r'.*cvv.*',              # CVV
        r'.*ssn.*',              # 社会安全号
        r'.*phone.*',            # 电话号码
        r'.*id_card.*',          # 身份证
    ],
    sensitive_paths=[
        '/auth/login',
        '/payment',              # 支付接口
        '/user/profile',         # 用户资料
    ]
)

# 注册自定义过滤器
log_filter_hook_manager.register_hook(custom_filter)
```

#### 创建完全自定义的过滤器

```python
from yweb.log import LogFilterHook, log_filter_hook_manager
from typing import Dict, Any

class IPAddressFilterHook(LogFilterHook):
    """IP 地址脱敏过滤器"""
    
    def should_apply(self, log_data: Dict[str, Any]) -> bool:
        # 只对包含 client_ip 的日志应用
        return 'client_ip' in log_data
    
    def filter(self, log_data: Dict[str, Any]) -> Dict[str, Any]:
        filtered = log_data.copy()
        ip = filtered.get('client_ip', '')
        if ip:
            # 将 IP 最后一段替换为 ***
            parts = ip.split('.')
            if len(parts) == 4:
                parts[-1] = '***'
                filtered['client_ip'] = '.'.join(parts)
        return filtered

# 注册自定义过滤器
log_filter_hook_manager.register_hook(IPAddressFilterHook())
```

### 日志过滤 API

#### SensitiveDataFilterHook

敏感数据过滤器类。

```python
SensitiveDataFilterHook(
    sensitive_patterns: List[str] = None,  # 敏感字段名正则模式
    sensitive_paths: List[str] = None      # 敏感 URL 路径
)
```

#### LogFilterHookManager

日志过滤钩子管理器（单例）。

```python
from yweb.log import log_filter_hook_manager

# 注册过滤器
log_filter_hook_manager.register_hook(hook)

# 注销过滤器
log_filter_hook_manager.unregister_hook(hook)

# 清除所有过滤器
log_filter_hook_manager.clear_hooks()

# 获取所有已注册的过滤器
hooks = log_filter_hook_manager.get_hooks()

# 手动应用过滤器
filtered_data = log_filter_hook_manager.apply_filters(log_data)
```

#### LogFilterHook

自定义过滤器基类。

```python
from yweb.log import LogFilterHook

class MyFilterHook(LogFilterHook):
    def should_apply(self, log_data: Dict[str, Any]) -> bool:
        """判断是否应该应用此过滤器"""
        return True
    
    def filter(self, log_data: Dict[str, Any]) -> Dict[str, Any]:
        """过滤日志数据"""
        filtered = log_data.copy()
        # 自定义过滤逻辑
        return filtered
```

### 默认常量

```python
from yweb.log import DEFAULT_SENSITIVE_PATTERNS, DEFAULT_SENSITIVE_PATHS

# 默认敏感字段模式
DEFAULT_SENSITIVE_PATTERNS = [
    r'.*(password|pwd|passwd).*',
    r'.*(token|access_token|refresh_token).*',
    r'.*(secret|key|apikey|api_key).*',
    r'.*(credential|credentials).*',
    r'.*(auth|authentication).*'
]

# 默认敏感路径
DEFAULT_SENSITIVE_PATHS = [
    '/auth/login',
    '/auth/token',
    '/admin/login'
]
```

---

## 最佳实践

### 1. 模块级日志记录器

在每个模块顶部定义日志记录器：

```python
# my_module.py
from yweb.log import get_logger

logger = get_logger()  # 自动推断为模块名

def my_function():
    logger.info("执行操作")
```

### 2. 类级日志记录器

```python
from yweb.log import get_logger

class MyService:
    def __init__(self):
        self.logger = get_logger()  # 使用模块名
    
    def process(self):
        self.logger.info("处理中...")
```

### 3. 避免硬编码

```python
# ❌ 不推荐
import logging
logger = logging.getLogger("yweb.my_module")

# ✅ 推荐
from yweb.log import get_logger
logger = get_logger()  # 自动推断，无硬编码
```

### 4. 日志级别使用

| 级别 | 使用场景 |
|------|---------|
| DEBUG | 详细调试信息，生产环境关闭 |
| INFO | 常规运行信息 |
| WARNING | 警告，但不影响正常运行 |
| ERROR | 错误，影响部分功能 |
| CRITICAL | 严重错误，系统无法继续运行 |

### 5. 敏感数据过滤

1. **生产环境始终启用** - 敏感数据过滤应在生产环境始终启用
2. **根据业务扩展** - 根据业务需求添加自定义敏感字段模式
3. **定期审查** - 定期审查日志，确保没有敏感信息泄露
4. **多层防护** - 日志过滤是最后一道防线，应在业务层面也做好数据保护

### 6. 高性能场景使用缓冲处理器

```python
from yweb.log import BufferedRotatingFileHandler
import logging

# 高并发场景推荐配置
handler = BufferedRotatingFileHandler(
    filename="logs/app_{date}.log",
    maxBytes=50*1024*1024,     # 50MB
    backupCount=10,
    bufferCapacity=200,        # 较大的缓冲区
    flushInterval=10.0,        # 较长的刷新间隔
    flushLevel=logging.ERROR   # ERROR 立即刷新
)
```

---

## API 参考

### get_logger

```python
def get_logger(name: str = None) -> logging.Logger:
    """获取日志记录器，支持自动推断模块名
    
    Args:
        name: 日志记录器名称
              - None: 自动使用调用模块的 __name__
              - 字符串: 使用指定名称（简单名称自动添加 yweb 前缀）
    
    Returns:
        日志记录器实例
    """
```

### setup_logger

```python
def setup_logger(
    name: str = None,
    level: str = "INFO",
    log_file: str = None,
    log_format: str = None,
    console: bool = True,
    use_microseconds: bool = True,
    propagate: bool = True,
    file_handler_options: dict = None
) -> logging.Logger:
    """设置并返回配置好的日志记录器"""
```

### setup_root_logger

```python
def setup_root_logger(
    level: str = "INFO",
    log_file: str = None,
    console: bool = True,
    use_microseconds: bool = True,
    file_handler_options: dict = None,
    config: Any = None,
    config_path: str = None,
    config_base_dir: str = None,
    setup_sql_logger: bool = True
) -> logging.Logger:
    """设置根日志记录器"""
```

### 日志处理器

```python
from yweb.log import (
    TimeAndSizeRotatingFileHandler,    # 时间+大小双重轮转
    DailyRotatingFileHandler,          # 每日轮转
    BufferedRotatingFileHandler,       # 带写缓存的轮转处理器
    BufferedDailyRotatingFileHandler,  # 带写缓存的每日轮转
)
```

### 日志过滤

```python
from yweb.log import (
    LogFilterHook,                    # 自定义过滤器基类
    SensitiveDataFilterHook,          # 敏感数据过滤器
    LogFilterHookManager,             # 过滤器管理器类
    log_filter_hook_manager,          # 全局过滤器管理器实例
    DEFAULT_SENSITIVE_PATTERNS,       # 默认敏感字段模式
    DEFAULT_SENSITIVE_PATHS,          # 默认敏感路径
)
```

---

**版本:** v1.0.0 | **更新日期:** 2026-01-18
