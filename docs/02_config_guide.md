# YWeb 配置指南

本指南介绍如何在 YWeb 项目中配置应用程序，支持 YAML 文件和环境变量，可混合使用。

## 目录

- [快速开始](#快速开始)
- [AppSettings 基础配置](#appsettings-基础配置)
- [YAML 配置文件](#yaml-配置文件)
- [环境变量配置](#环境变量配置)
- [容器化 / 云原生部署](#容器化--云原生部署)
- [配置加载器](#配置加载器)
- [配置管理器](#配置管理器)
- [配置项参考](#配置项参考)
- [最佳实践](#最佳实践)

---

## 快速开始

### 安装依赖

```bash
pip install pyyaml pydantic pydantic-settings
```

### 最简示例

```python
from yweb.config import AppSettings, load_yaml_config

# 1. 定义项目配置（继承 AppSettings，只写业务特有字段）
class Settings(AppSettings):
    app_name: str = "My App"

# 2. 从 YAML 加载
settings = load_yaml_config("config/settings.yaml", Settings)

# 3. 使用嵌套配置
print(settings.jwt.secret_key)
print(settings.database.url)
print(settings.app_name)
```

### 配置优先级

```
环境变量 > YAML 配置文件 > 代码中的默认值
```

### 配置原则

**不需要写全所有配置项。** YAML 文件中只需写你要覆盖默认值的配置，未写的配置项会自动使用框架默认值。

#### 必填配置（默认值为空，不填则功能不可用）

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `database.url` | `""` | 数据库连接 URL，不填则无法连接数据库 |

#### 强烈建议填写（有默认值但存在安全风险）

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `jwt.secret_key` | `"change-me-in-production"` | JWT 签名密钥，不修改则任何人都能伪造 Token |

#### 按需填写（默认值为空，用到对应功能时才需配置）

| 配置项 | 说明 |
|--------|------|
| `redis.url` | 用到 Redis 缓存或分布式锁时才需配置 |
| `storage.oss.*` | 用到阿里云 OSS 存储时才需配置 |
| `storage.s3.*` | 用到 AWS S3 / MinIO 存储时才需配置 |
| `scheduler.redis_url` | 用到定时任务分布式锁时才需配置 |

#### 无需填写（均有合理默认值）

以下配置全部有合理的默认值，不写也能正常运行，按需调整即可：

`logging.*`、`middleware.*`、`pagination.*`、`scheduler.*`（除 `redis_url`）、`storage.local.*`

**最小可运行配置示例：**

```yaml
database:
  url: "sqlite:///./app.db"

jwt:
  secret_key: "your-secret-key"
```

---

## AppSettings 基础配置

`AppSettings` 是 YWeb 提供的应用基础配置类，内置了所有常用子配置，业务项目继承后只需添加特有字段。

### 内置子配置

| 属性 | 配置类 | 环境变量前缀 | 说明 |
|------|--------|-------------|------|
| `database` | DatabaseSettings | `YWEB_DB_` | 数据库连接 |
| `redis` | RedisSettings | `YWEB_REDIS_` | Redis 连接 |
| `jwt` | JWTSettings | `YWEB_JWT_` | JWT 认证 |
| `logging` | LoggingSettings | `YWEB_LOG_` | 日志配置 |
| `middleware` | MiddlewareSettings | `YWEB_MW_` | 中间件配置 |
| `pagination` | PaginationSettings | `YWEB_PAGE_` | 分页配置 |
| `scheduler` | SchedulerSettings | `YWEB_SCHEDULER_` | 定时任务 |
| `storage` | StorageSettings | `YWEB_STORAGE_` | 文件存储 |

### 继承并扩展

```python
from yweb.config import AppSettings, load_yaml_config
from pydantic import Field

class Settings(AppSettings):
    """项目配置，只写业务特有的字段"""
    app_name: str = Field(default="My App", description="应用名称")
    enable_sms: bool = Field(default=False, description="是否启用短信通知")
    admin_email: str = Field(default="admin@example.com", description="管理员邮箱")

settings = load_yaml_config("config/settings.yaml", Settings)
```

### 使用独立子配置类

如果只需要部分配置，也可以单独使用：

```python
from yweb.config import JWTSettings, DatabaseSettings

jwt_config = JWTSettings(secret_key="my-secret", access_token_expire_minutes=60)
db_config = DatabaseSettings(url="postgresql://localhost/mydb", pool_size=10)
```

---

## YAML 配置文件

### 完整配置示例

创建 `config/settings.yaml`：

```yaml
# ==================== 数据库配置 ====================
database:
  url: "postgresql://user:password@localhost:5432/mydb"
  echo: false
  pool_size: 5
  max_overflow: 10
  pool_timeout: 30
  pool_recycle: 3600
  pool_pre_ping: true

# ==================== Redis 配置 ====================
redis:
  url: "redis://localhost:6379/0"
  max_connections: 10

# ==================== JWT 认证配置 ====================
jwt:
  secret_key: "your-secret-key-change-in-production"
  algorithm: "HS256"
  access_token_expire_minutes: 30
  refresh_token_expire_days: 7
  refresh_token_sliding_days: 2

# ==================== 日志配置 ====================
logging:
  level: "INFO"
  file_path: "logs/app_{date}.log"
  file_max_bytes: "10MB"
  file_backup_count: 30
  enable_console: true
  max_retention_days: 30
  max_total_size: "1GB"
  # 写缓存配置（高性能场景可启用）
  buffer_enabled: false
  buffer_capacity: 100
  buffer_flush_interval: 5.0
  buffer_flush_level: "ERROR"
  # SQL 日志
  sql_log_enabled: false
  sql_log_file_path: "logs/sql_{date}.log"
  sql_log_level: "DEBUG"
  sql_log_max_bytes: "50MB"
  sql_log_backup_count: 10

# ==================== 中间件配置 ====================
middleware:
  request_log_max_body_size: "10KB"
  slow_request_threshold: 1.0
  request_log_skip_paths:
    - "/health"
    - "/metrics"
    - "/docs"
    - "/redoc"
    - "/openapi.json"

# ==================== 分页配置 ====================
pagination:
  max_page_size: 1000
  default_page_size: 10

# ==================== 业务特有配置 ====================
app_name: "My Application"
enable_sms: false
```

### 多环境配置

推荐创建多个配置文件：

```
config/
├── settings.yaml          # 基础配置（通用）
├── settings.dev.yaml      # 开发环境覆盖
├── settings.prod.yaml     # 生产环境覆盖
└── settings.test.yaml     # 测试环境覆盖
```

**settings.dev.yaml**:

```yaml
database:
  url: "sqlite:///./dev.db"
  echo: true
logging:
  level: "DEBUG"
  sql_log_enabled: true
```

**settings.prod.yaml**:

```yaml
database:
  url: "${DATABASE_URL}"
jwt:
  secret_key: "${JWT_SECRET}"
logging:
  level: "WARNING"
```

---

## 环境变量配置

每个子配置类定义了独立的环境变量前缀，可直接覆盖 YAML 中的值。

### 环境变量命名规则

格式：`{前缀}{字段名大写}`

| 配置项 | 环境变量 |
|--------|----------|
| `database.url` | `YWEB_DB_URL` |
| `jwt.secret_key` | `YWEB_JWT_SECRET_KEY` |
| `jwt.access_token_expire_minutes` | `YWEB_JWT_ACCESS_TOKEN_EXPIRE_MINUTES` |
| `redis.url` | `YWEB_REDIS_URL` |
| `logging.level` | `YWEB_LOG_LEVEL` |
| `middleware.slow_request_threshold` | `YWEB_MW_SLOW_REQUEST_THRESHOLD` |
| `pagination.default_page_size` | `YWEB_PAGE_DEFAULT_PAGE_SIZE` |
| `scheduler.enabled` | `YWEB_SCHEDULER_ENABLED` |
| `storage.default` | `YWEB_STORAGE_DEFAULT` |

### .env 文件示例

```bash
# .env - 本地开发环境
YWEB_DB_URL="postgresql://user:pass@localhost:5432/mydb"
YWEB_JWT_SECRET_KEY="dev-secret-key"
YWEB_JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
YWEB_REDIS_URL="redis://localhost:6379/0"
YWEB_LOG_LEVEL="DEBUG"
```

### 加载 .env 文件

```python
from yweb.config import set_env_from_file

# 在应用启动时加载
set_env_from_file(".env")

# 或指定文件路径
set_env_from_file(".env.production")

# 覆盖已存在的环境变量
set_env_from_file(".env", override=True)
```

---

## 容器化 / 云原生部署

`AppSettings` 天然支持容器化部署——通过环境变量注入敏感配置，覆盖 YAML 中的默认值，无需修改代码或配置文件。

### Docker Compose

```yaml
# docker-compose.yml
services:
  app:
    image: my-app:latest
    environment:
      - YWEB_DB_URL=postgresql://user:pass@db:5432/production
      - YWEB_JWT_SECRET_KEY=production-secret-very-long-and-random
      - YWEB_REDIS_URL=redis://redis:6379/0
      - YWEB_LOG_LEVEL=WARNING
    volumes:
      - ./config:/app/config  # 挂载通用 YAML 配置（可选）
    depends_on:
      - db
      - redis
  
  db:
    image: postgres:16
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
      - POSTGRES_DB=production
  
  redis:
    image: redis:7-alpine
```

### Kubernetes

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  template:
    spec:
      containers:
        - name: app
          image: my-app:latest
          env:
            # 普通配置
            - name: YWEB_LOG_LEVEL
              value: "WARNING"
            # 从 Secret 引用敏感值
            - name: YWEB_DB_URL
              valueFrom:
                secretKeyRef:
                  name: app-secrets
                  key: database-url
            - name: YWEB_JWT_SECRET_KEY
              valueFrom:
                secretKeyRef:
                  name: app-secrets
                  key: jwt-secret-key
            - name: YWEB_REDIS_URL
              valueFrom:
                secretKeyRef:
                  name: app-secrets
                  key: redis-url
```

```yaml
# secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: app-secrets
type: Opaque
stringData:
  database-url: "postgresql://user:pass@db-service:5432/production"
  jwt-secret-key: "production-secret-very-long-and-random"
  redis-url: "redis://redis-service:6379/0"
```

### 推荐做法

| 配置类型 | 存放位置 | 示例 |
|----------|----------|------|
| 通用配置 | YAML 文件 | 分页大小、日志格式、跳过路径 |
| 环境相关 | 环境变量 | 日志级别、调试开关 |
| 敏感数据 | 环境变量 / Secret | 数据库密码、JWT 密钥、Redis URL |

---

## 配置加载器

`ConfigLoader` 用于从 YAML 文件加载配置，支持缓存和重新加载。

### 基本用法

```python
from yweb.config import ConfigLoader

# 加载配置
config = ConfigLoader.load("config/settings.yaml")

# 获取配置值
db_url = config.get("database", {}).get("url")
jwt_secret = config.get("jwt", {}).get("secret_key")
```

### 缓存管理

```python
# 重新加载配置（忽略缓存）
config = ConfigLoader.reload("config/settings.yaml")

# 禁用缓存
config = ConfigLoader.load("config/settings.yaml", use_cache=False)

# 清除所有缓存
ConfigLoader.clear_cache()

# 查看已缓存的配置文件
cached_paths = ConfigLoader.get_cached_paths()
```

### 指定基础目录

```python
config = ConfigLoader.load(
    "settings.yaml",
    base_dir="/path/to/project/config"
)
```

---

## 配置管理器

`ConfigManager` 用于管理多个配置文件，支持配置合并和点号路径访问。

### 基本用法

```python
from yweb.config import ConfigManager

manager = ConfigManager(base_dir="config")

# 加载主配置
manager.load("settings.yaml")

# 加载环境配置并合并
manager.load("settings.dev.yaml", merge=True)
```

### 点号路径访问

```python
db_url = manager.get("database.url")
jwt_secret = manager.get("jwt.secret_key")
log_level = manager.get("logging.level", default="INFO")

# 设置配置值
manager.set("database.pool_size", 20)

# 获取完整配置
full_config = manager.to_dict()
```

### 多环境配置加载

```python
import os

manager = ConfigManager(base_dir="config")
manager.load("settings.yaml")

env = os.getenv("APP_ENV", "dev")
manager.load(f"settings.{env}.yaml", merge=True)

database_url = manager.get("database.url")
```

---

## 配置项参考

### JWT 配置 (JWTSettings)

| 配置项 | 类型 | 默认值 | 环境变量 | 说明 |
|--------|------|--------|----------|------|
| `secret_key` | str | "change-me-in-production" | `YWEB_JWT_SECRET_KEY` | JWT 密钥（**生产环境必须修改**） |
| `algorithm` | str | "HS256" | `YWEB_JWT_ALGORITHM` | JWT 算法 |
| `access_token_expire_minutes` | int | 30 | `YWEB_JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | 访问令牌过期时间（分钟） |
| `refresh_token_expire_days` | int | 7 | `YWEB_JWT_REFRESH_TOKEN_EXPIRE_DAYS` | 刷新令牌过期时间（天） |
| `refresh_token_sliding_days` | int | 2 | `YWEB_JWT_REFRESH_TOKEN_SLIDING_DAYS` | 刷新令牌滑动过期阈值（天） |

### 数据库配置 (DatabaseSettings)

| 配置项 | 类型 | 默认值 | 环境变量 | 说明 |
|--------|------|--------|----------|------|
| `url` | str | "" | `YWEB_DB_URL` | 数据库连接 URL |
| `echo` | bool | false | `YWEB_DB_ECHO` | 是否打印 SQL 语句 |
| `pool_size` | int | 5 | `YWEB_DB_POOL_SIZE` | 连接池大小 |
| `max_overflow` | int | 10 | `YWEB_DB_MAX_OVERFLOW` | 连接池最大溢出 |
| `pool_timeout` | int | 30 | `YWEB_DB_POOL_TIMEOUT` | 连接超时（秒） |
| `pool_recycle` | int | 3600 | `YWEB_DB_POOL_RECYCLE` | 连接回收时间（秒） |
| `pool_pre_ping` | bool | true | `YWEB_DB_POOL_PRE_PING` | 连接前检查 |

#### 数据库 URL 格式

```yaml
# SQLite
database:
  url: "sqlite:///./app.db"

# PostgreSQL
database:
  url: "postgresql://user:password@localhost:5432/dbname"

# MySQL
database:
  url: "mysql+pymysql://user:password@localhost:3306/dbname"
```

### Redis 配置 (RedisSettings)

| 配置项 | 类型 | 默认值 | 环境变量 | 说明 |
|--------|------|--------|----------|------|
| `url` | str | "" | `YWEB_REDIS_URL` | Redis 连接 URL |
| `max_connections` | int | 10 | `YWEB_REDIS_MAX_CONNECTIONS` | 最大连接数 |

### 日志配置 (LoggingSettings)

#### 基础日志

| 配置项 | 类型 | 默认值 | 环境变量 | 说明 |
|--------|------|--------|----------|------|
| `level` | str | "INFO" | `YWEB_LOG_LEVEL` | 日志级别 |
| `file_path` | str | "logs/app_{date}.log" | `YWEB_LOG_FILE_PATH` | 日志文件路径，`{date}` 替换为日期 |
| `file_max_bytes` | str | "10MB" | `YWEB_LOG_FILE_MAX_BYTES` | 单个日志文件最大大小 |
| `file_backup_count` | int | 30 | `YWEB_LOG_FILE_BACKUP_COUNT` | 保留的备份文件数量（同一天内的序号备份） |
| `file_encoding` | str | "utf-8" | `YWEB_LOG_FILE_ENCODING` | 日志文件编码 |
| `file_when` | str | "midnight" | `YWEB_LOG_FILE_WHEN` | 日志轮转时间点（midnight / S / M / H / D） |
| `file_interval` | int | 1 | `YWEB_LOG_FILE_INTERVAL` | 日志轮转间隔 |
| `enable_console` | bool | true | `YWEB_LOG_ENABLE_CONSOLE` | 启用控制台日志 |
| `max_retention_days` | int | 0 | `YWEB_LOG_MAX_RETENTION_DAYS` | 日志保留天数，0 不限制 |
| `max_total_size` | str | "0" | `YWEB_LOG_MAX_TOTAL_SIZE` | 日志总大小限制，0 不限制 |

#### 写缓存（高性能场景可启用）

| 配置项 | 类型 | 默认值 | 环境变量 | 说明 |
|--------|------|--------|----------|------|
| `buffer_enabled` | bool | false | `YWEB_LOG_BUFFER_ENABLED` | 启用写缓存，日志先缓存再批量写入 |
| `buffer_capacity` | int | 100 | `YWEB_LOG_BUFFER_CAPACITY` | 缓冲区容量（条数），达到后刷新 |
| `buffer_flush_interval` | float | 5.0 | `YWEB_LOG_BUFFER_FLUSH_INTERVAL` | 缓冲区刷新间隔（秒） |
| `buffer_flush_level` | str | "ERROR" | `YWEB_LOG_BUFFER_FLUSH_LEVEL` | 触发立即刷新的日志级别，ERROR 及以上立即落盘 |

#### SQL 日志

| 配置项 | 类型 | 默认值 | 环境变量 | 说明 |
|--------|------|--------|----------|------|
| `sql_log_enabled` | bool | false | `YWEB_LOG_SQL_LOG_ENABLED` | 是否启用 SQL 日志 |
| `sql_log_file_path` | str | "logs/sql_{date}.log" | `YWEB_LOG_SQL_LOG_FILE_PATH` | SQL 日志文件路径 |
| `sql_log_level` | str | "DEBUG" | `YWEB_LOG_SQL_LOG_LEVEL` | SQL 日志级别 |
| `sql_log_max_bytes` | str | "50MB" | `YWEB_LOG_SQL_LOG_MAX_BYTES` | SQL 日志文件最大大小 |
| `sql_log_backup_count` | int | 10 | `YWEB_LOG_SQL_LOG_BACKUP_COUNT` | SQL 日志备份文件数量 |
| `sql_log_max_retention_days` | int | 0 | `YWEB_LOG_SQL_LOG_MAX_RETENTION_DAYS` | SQL 日志保留天数，0 不限制 |
| `sql_log_max_total_size` | str | "0" | `YWEB_LOG_SQL_LOG_MAX_TOTAL_SIZE` | SQL 日志总大小限制，0 不限制 |
| `sql_log_buffer_enabled` | bool | false | `YWEB_LOG_SQL_LOG_BUFFER_ENABLED` | SQL 日志是否启用写缓存 |
| `sql_log_buffer_capacity` | int | 100 | `YWEB_LOG_SQL_LOG_BUFFER_CAPACITY` | SQL 日志缓冲区容量 |
| `sql_log_buffer_flush_interval` | float | 5.0 | `YWEB_LOG_SQL_LOG_BUFFER_FLUSH_INTERVAL` | SQL 日志缓冲区刷新间隔（秒） |

### 中间件配置 (MiddlewareSettings)

| 配置项 | 类型 | 默认值 | 环境变量 | 说明 |
|--------|------|--------|----------|------|
| `request_log_max_body_size` | str | "10KB" | `YWEB_MW_REQUEST_LOG_MAX_BODY_SIZE` | 请求体日志最大大小 |
| `request_log_skip_paths` | list | [...] | - | 跳过日志记录的路径 |
| `slow_request_threshold` | float | 1.0 | `YWEB_MW_SLOW_REQUEST_THRESHOLD` | 慢请求阈值（秒） |

### 分页配置 (PaginationSettings)

| 配置项 | 类型 | 默认值 | 环境变量 | 说明 |
|--------|------|--------|----------|------|
| `max_page_size` | int | 1000 | `YWEB_PAGE_MAX_PAGE_SIZE` | 最大页大小 |
| `default_page_size` | int | 10 | `YWEB_PAGE_DEFAULT_PAGE_SIZE` | 默认页大小 |

### 定时任务配置 (SchedulerSettings)

| 配置项 | 类型 | 默认值 | 环境变量 | 说明 |
|--------|------|--------|----------|------|
| `enabled` | bool | true | `YWEB_SCHEDULER_ENABLED` | 是否启用 |
| `timezone` | str | "Asia/Shanghai" | `YWEB_SCHEDULER_TIMEZONE` | 时区 |
| `store` | str | "memory" | `YWEB_SCHEDULER_STORE` | 存储方式: memory / orm |
| `max_workers` | int | 10 | `YWEB_SCHEDULER_MAX_WORKERS` | 最大并发执行数 |
| `misfire_grace_time` | int | 60 | `YWEB_SCHEDULER_MISFIRE_GRACE_TIME` | 错过执行的宽限时间（秒） |
| `coalesce` | bool | true | `YWEB_SCHEDULER_COALESCE` | 是否合并错过的多次执行为一次 |
| `distributed_lock` | bool | false | `YWEB_SCHEDULER_DISTRIBUTED_LOCK` | 是否启用分布式锁（需要 Redis） |
| `redis_url` | str | null | `YWEB_SCHEDULER_REDIS_URL` | Redis URL，用于分布式锁 |
| `lock_timeout` | int | 300 | `YWEB_SCHEDULER_LOCK_TIMEOUT` | 分布式锁超时时间（秒） |
| `enable_history` | bool | true | `YWEB_SCHEDULER_ENABLE_HISTORY` | 是否记录执行历史 |
| `history_retention_days` | int | 30 | `YWEB_SCHEDULER_HISTORY_RETENTION_DAYS` | 历史记录保留天数 |

### 存储配置 (StorageSettings)

| 配置项 | 类型 | 默认值 | 环境变量 | 说明 |
|--------|------|--------|----------|------|
| `default` | str | "local" | `YWEB_STORAGE_DEFAULT` | 默认存储后端 |

包含以下子配置（环境变量支持 `__` 嵌套分隔符，如 `YWEB_STORAGE_OSS__BUCKET_NAME`）：

| 子配置 | 配置类 | 环境变量前缀 | 说明 |
|--------|--------|-------------|------|
| `local` | LocalStorageConfig | `YWEB_STORAGE_LOCAL_` | 本地存储（base_path / base_url / create_dirs） |
| `memory` | MemoryStorageConfig | `YWEB_STORAGE_MEMORY_` | 内存存储（max_size / max_files / auto_cleanup） |
| `oss` | OSSStorageConfig | `YWEB_STORAGE_OSS_` | 阿里云 OSS（access_key_id / access_key_secret / endpoint / bucket_name） |
| `s3` | S3StorageConfig | `YWEB_STORAGE_S3_` | AWS S3 / MinIO（access_key_id / secret_access_key / bucket_name / endpoint_url） |
| `secure_url` | SecureURLConfig | `YWEB_STORAGE_SECURE_` | 安全 URL（secret_key / base_url / default_expires） |

详细的存储配置请参考 [存储指南](10_storage_guide.md)。

---

## 最佳实践

### 1. 敏感信息不要写入 YAML

```yaml
# ❌ 不要这样做
jwt:
  secret_key: "my-actual-secret-key"

# ✅ 通过环境变量注入
# YWEB_JWT_SECRET_KEY=my-actual-secret-key
```

YAML 中可以写开发用的默认值，生产环境通过环境变量覆盖。

### 2. 配置验证

```python
from yweb.config import AppSettings
from pydantic import Field, field_validator

class Settings(AppSettings):
    app_name: str = Field(default="My App")
    
    @field_validator("app_name")
    @classmethod
    def validate_app_name(cls, v):
        if not v.strip():
            raise ValueError("应用名称不能为空")
        return v
```

### 3. 配置类型转换

YWeb 支持文件大小的字符串表示：

```yaml
# 支持的格式
logging:
  file_max_bytes: "10MB"      # 10 * 1024 * 1024
middleware:
  request_log_max_body_size: "100KB"  # 100 * 1024
```

---

## 完整应用示例

```python
# app/config.py
import os
from yweb.config import AppSettings, load_yaml_config, ConfigLoader
from pydantic import Field

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class Settings(AppSettings):
    """项目配置"""
    enable_console_logging: bool = Field(default=False)
    base_url: str = Field(default="http://localhost:8000")

def load_settings() -> Settings:
    return load_yaml_config("config/settings.yaml", Settings, base_dir=PROJECT_ROOT)

def reload_settings() -> Settings:
    global settings
    ConfigLoader.clear_cache()
    settings = load_settings()
    return settings

settings = load_settings()
```

```python
# main.py
from fastapi import FastAPI
from app.config import settings

app = FastAPI(title="My App")

@app.on_event("startup")
def startup():
    print(f"Database: {settings.database.url}")
    print(f"JWT expire: {settings.jwt.access_token_expire_minutes}min")
    print(f"Log level: {settings.logging.level}")
```

---

## 更多文档

- [快速开始](01_quickstart.md)
- [ORM 使用指南](03_orm_guide.md)
- [日志指南](04_log_guide.md)
- [认证指南](06_auth_guide.md)
- [定时任务指南](09_scheduler_guide.md)
- [存储指南](10_storage_guide.md)
