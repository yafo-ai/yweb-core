# YWeb 定时任务模块设计文档

本文档描述 YWeb 定时任务模块的设计方案，基于 APScheduler 进行封装，提供简洁易用的 API。

## 目录

- [设计目标](#设计目标)
- [技术选型](#技术选型)
- [模块结构](#模块结构)
- [标识体系设计](#标识体系设计)
- [核心 API 设计](#核心-api-设计)
- [触发器设计](#触发器设计)
- [任务类型](#任务类型)
- [Builder 模式（链式配置）](#builder-模式链式配置)
- [多触发器支持](#多触发器支持)
- [失败重试策略](#失败重试策略)
- [HTTP 任务](#http-任务)
- [配置设计](#配置设计)
- [持久化设计（基于 YWeb ORM）](#持久化设计基于-yweb-orm)
- [FastAPI 集成](#fastapi-集成)
- [分布式支持](#分布式支持)
- [监控与管理](#监控与管理)
- [执行统计](#执行统计)
- [使用示例](#使用示例)
- [实现计划](#实现计划)

---

## 设计目标

| 目标 | 说明 |
|------|------|
| **一行代码添加任务** | 装饰器或链式配置，最小代码量 |
| **零配置启动** | 智能默认值，开箱即用 |
| **多样化触发方式** | Cron、间隔、特定时间、多触发器 |
| **丰富的任务类型** | 函数任务、类任务、HTTP 任务 |
| **完善的监控管理** | 暂停/恢复/删除/立即执行/统计 |
| **集群支持** | 分布式锁防止重复执行 |
| **失败重试** | 可配置的重试策略 |
| **FastAPI 原生** | 与 FastAPI 生命周期无缝集成 |

---

## 技术选型

### 为什么选择 APScheduler

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| **APScheduler** | 轻量、功能全、支持异步、多种存储后端 | 默认单进程 | ✅ 推荐 |
| Celery Beat | 分布式、成熟稳定 | 配置复杂、需要消息队列 | ❌ 过重 |
| arq | 异步原生、轻量 | 定时功能基础、必须 Redis | ❌ 功能不足 |
| schedule | 极简 | 无持久化、不适合生产 | ❌ 太简单 |

### 依赖

```
apscheduler>=3.10.0,<4.0.0  # 核心调度器
redis>=4.0.0                 # 可选：分布式锁
```

---

## 模块结构

```
yweb/
├── scheduler/
│   ├── __init__.py           # 导出 Scheduler, Job, cron, interval, once
│   ├── scheduler.py          # 核心调度器类
│   ├── triggers.py           # 触发器快捷函数
│   ├── job.py                # 任务包装类
│   ├── context.py            # 执行上下文（JobContext）
│   ├── stores/
│   │   ├── __init__.py
│   │   ├── base.py           # 存储抽象基类
│   │   ├── memory.py         # 内存存储（默认）
│   │   └── orm.py            # YWeb ORM 存储
│   ├── executors/
│   │   ├── __init__.py
│   │   ├── async_executor.py # 异步执行器
│   │   └── thread_executor.py# 线程执行器
│   ├── locks/
│   │   ├── __init__.py
│   │   ├── base.py           # 分布式锁抽象
│   │   └── redis_lock.py     # Redis 分布式锁
│   └── models.py             # ORM 模型（任务定义、执行历史、统计）
```

---

## 标识体系设计

### 两层结构

| 层级 | 概念 | 说明 |
|------|------|------|
| **任务定义（Job）** | 静态配置 | 描述"做什么、何时做"，一个任务只有一条记录 |
| **任务执行（Execution）** | 动态记录 | 每次运行产生一条记录，可追溯历史 |

### 任务定义标识

| 字段 | 用途 | 生成方式 | 说明 |
|------|------|----------|------|
| `id` | 内部唯一标识 | **自动生成**（UUID/雪花ID） | 用户无需关心，系统内部使用 |
| `code` | 业务编码 | **用户定义**（可选） | 用于 API 操作，不指定时默认为函数名 |
| `name` | 任务名称 | 用户定义 | 简短标题，用于界面展示 |
| `description` | 任务描述 | 用户定义（可选） | 详细说明任务用途 |

### 任务执行标识

| 字段 | 用途 | 生成方式 | 说明 |
|------|------|----------|------|
| `run_id` | 执行唯一标识 | **自动生成** | 每次执行唯一，用于追踪、日志关联 |
| `job_id` | 关联任务 | 自动关联 | 指向任务定义 |
| `attempt` | 尝试次数 | 自动计数 | 首次为1，重试递增 |

### 示例说明

```
任务定义（Job）
├── id: "550e8400-e29b-41d4-a716-446655440000"  # 自动生成
├── code: "REPORT_DAILY_SALES"                   # 用户定义
├── name: "每日销售报表"                          # 用户定义
├── description: "每天早上8点生成前一天的销售汇总" # 用户定义
└── trigger: cron("0 8 * * *")

执行记录（Executions）
├── run_id: "run_20260121_080000_a1b2c3"
│   ├── job_code: "REPORT_DAILY_SALES"
│   ├── scheduled_time: 2026-01-21 08:00:00
│   ├── status: success
│   ├── duration_ms: 14000
│   └── attempt: 1
│
├── run_id: "run_20260122_080000_d4e5f6"
│   ├── job_code: "REPORT_DAILY_SALES"
│   ├── scheduled_time: 2026-01-22 08:00:00
│   ├── status: failed
│   ├── error: "Database timeout"
│   └── attempt: 1
│       │
│       └── run_id: "run_20260122_080100_g7h8i9"  # 重试记录
│           ├── scheduled_time: 2026-01-22 08:00:00
│           ├── status: success
│           ├── attempt: 2
│           └── retry_of: "run_20260122_080000_d4e5f6"
```

### Code 命名建议

```python
# 推荐：模块_功能_细分（大写下划线）
code="REPORT_DAILY_SALES"
code="SYNC_USER_FROM_LDAP"
code="CLEANUP_LOG_90DAYS"
code="NOTIFY_ORDER_TIMEOUT"

# 或者用点号分隔（小写）
code="report.daily.sales"
code="sync.user.ldap"
```

### run_id 生成策略

```python
# 格式：run_{日期}_{时间}_{随机串}
run_id = f"run_{datetime.now():%Y%m%d_%H%M%S}_{random_string(6)}"
# 示例: run_20260121_080000_a1b2c3
```

---

## 核心 API 设计

### 快捷类设计（推荐）

```python
from yweb import Scheduler

# 创建调度器（全局单例模式）
scheduler = Scheduler()

# ========== 装饰器方式（推荐） ==========

# 最简写法：code 默认为函数名 "daily_report"
@scheduler.cron("0 8 * * *")
async def daily_report():
    """生成日报"""
    print("生成日报...")

# 完整写法：指定 code、name、description
@scheduler.cron(
    "0 8 * * *",
    code="REPORT_DAILY_SALES",           # 业务编码（用于API操作）
    name="每日销售报表",                   # 名称（用于展示）
    description="每天早上8点生成前一天的销售汇总报表",  # 描述
)
async def daily_report():
    pass

@scheduler.interval(minutes=30, code="SYNC_DATA", name="数据同步")
async def sync_data():
    """同步数据"""
    pass

@scheduler.interval(hours=1, start_date="2026-01-22 00:00:00")
async def hourly_task():
    """从指定时间开始，每小时执行"""
    pass

@scheduler.once("2026-01-22 10:00:00")  # 一次性任务
async def one_time_task():
    """只执行一次"""
    pass

@scheduler.once(run_date=datetime.now() + timedelta(minutes=5))
async def delayed_task():
    """5分钟后执行"""
    pass
```

### 动态任务管理

```python
from yweb import Scheduler, cron, interval, once

scheduler = Scheduler()

# ========== 动态添加任务 ==========

# 添加 cron 任务
scheduler.add_job(
    my_func,
    trigger=cron("*/5 * * * *"),  # 每5分钟
    code="MY_CRON_JOB",           # 业务编码（用于管理操作）
    name="我的定时任务",
    description="每5分钟执行一次的示例任务",
    replace_existing=True,        # 如果 code 存在则替换
)

# 添加 interval 任务
scheduler.add_job(
    sync_func,
    trigger=interval(minutes=10),
    code="SYNC_JOB",
    name="数据同步",
    args=["arg1"],                # 位置参数
    kwargs={"key": "value"},      # 关键字参数
)

# 添加一次性任务
scheduler.add_job(
    send_email,
    trigger=once("2026-01-22 15:00:00"),
    code="SEND_WELCOME_EMAIL",
    name="发送欢迎邮件",
)

# ========== 任务控制（通过 code 操作） ==========

scheduler.pause_job("MY_CRON_JOB")      # 暂停任务
scheduler.resume_job("MY_CRON_JOB")     # 恢复任务
scheduler.remove_job("MY_CRON_JOB")     # 删除任务
scheduler.reschedule_job(               # 修改调度
    "MY_CRON_JOB", 
    trigger=cron("0 */2 * * *")         # 改为每2小时
)

# ========== 立即执行 ==========

# 立即执行一次（不影响正常调度），返回 run_id
run_id = scheduler.run_job("MY_CRON_JOB")
print(f"任务已触发，执行ID: {run_id}")

# ========== 查询任务 ==========

jobs = scheduler.get_jobs()                    # 获取所有任务
job = scheduler.get_job("MY_CRON_JOB")         # 通过 code 获取单个任务

for job in jobs:
    print(f"{job.code}: {job.name}, 下次执行: {job.next_run_time}")

# ========== 查询执行记录 ==========

# 获取某任务的执行历史
executions = scheduler.get_executions(code="MY_CRON_JOB", limit=10)
for exe in executions:
    print(f"  {exe.run_id}: {exe.status}, 耗时: {exe.duration_ms}ms")

# 获取某次执行的详情
execution = scheduler.get_execution(run_id="run_20260121_080000_a1b2c3")
```

### 执行上下文（JobContext）

任务函数可以接收执行上下文，获取当前执行的详细信息：

```python
from yweb.scheduler import JobContext

@scheduler.cron("0 8 * * *", code="DAILY_REPORT", name="每日报表")
async def daily_report(context: JobContext):
    # 任务标识
    print(f"任务ID: {context.job_id}")           # 自动生成的UUID
    print(f"任务编码: {context.job_code}")        # DAILY_REPORT
    print(f"任务名称: {context.job_name}")        # 每日报表
    
    # 执行标识
    print(f"执行ID: {context.run_id}")           # run_20260121_080000_a1b2c3
    print(f"第几次尝试: {context.attempt}")       # 1 (首次) 或 2,3... (重试)
    
    # 时间信息
    print(f"计划时间: {context.scheduled_time}") # 2026-01-21 08:00:00
    print(f"实际开始: {context.start_time}")     # 2026-01-21 08:00:01
    
    # 触发信息
    print(f"触发类型: {context.trigger_type}")   # scheduled | manual | retry
    
    # 执行统计
    print(f"历史执行次数: {context.run_count}")   # 该任务累计执行次数
    
    # 日志关联（推荐）
    logger.info(f"[{context.run_id}] 开始生成报表...")
    
    # 业务逻辑
    result = await generate_report()
    
    logger.info(f"[{context.run_id}] 报表生成完成")
    return result
```

---

## 触发器设计

提供多样化的触发方式，支持简洁的快捷函数。

### 触发器快捷函数

```python
from yweb.scheduler import cron, interval, once

# ========== 1. Cron 表达式触发 ==========
cron("0 8 * * *")               # 每天 8:00
cron("*/5 * * * *")             # 每5分钟
cron("0 0 * * 0")               # 每周日 0:00
cron("0 9-17 * * 1-5")          # 工作日 9:00-17:00 每小时
cron("0 30 9 * * MON-FRI")      # 工作日 9:30

# Cron 关键字参数（更易读）
cron(hour=8, minute=0)                    # 每天 8:00
cron(day_of_week="mon-fri", hour=9)       # 工作日 9:00
cron(day=1, hour=0, minute=0)             # 每月1号 0:00

# ========== 2. 时间间隔触发 ==========
interval(seconds=30)            # 每30秒
interval(minutes=5)             # 每5分钟
interval(hours=1)               # 每小时
interval(days=1)                # 每天
interval(weeks=1)               # 每周
interval(minutes=5, start_date="2026-01-22 00:00:00")  # 指定开始时间

# ========== 3. 一次性触发 ==========
once("2026-12-31 23:59:59")                           # 指定时间字符串
once(datetime(2026, 12, 31, 23, 59, 59))              # datetime 对象
once(run_date=datetime.now() + timedelta(hours=1))   # 1小时后
```

### 触发器类型速查表

| 触发器 | 用途 | 示例 |
|--------|------|------|
| `cron()` | Cron 表达式 | `cron("0 8 * * *")` |
| `interval()` | 时间间隔 | `interval(minutes=5)` |
| `once()` | 一次性 | `once("2026-12-31 23:59:59")` |

---

## 任务类型

支持多种任务定义方式，满足不同场景需求。

### 1. 函数任务（装饰器方式）

```python
from yweb import Scheduler

scheduler = Scheduler()

# 异步函数
@scheduler.cron("0 8 * * *")
async def daily_report():
    print("生成日报...")

# 同步函数
@scheduler.interval(minutes=30)
def sync_data():
    print("同步数据...")
```

### 2. 类任务（声明式）

```python
from yweb.scheduler import Job, cron, interval

# 方式1：继承 Job 基类
class ReportJob(Job):
    """每日报表任务"""
    
    # 类级别配置
    trigger = cron("0 2 * * *")       # 每天凌晨2点
    name = "每日报表生成"
    concurrent = False                 # 禁止并发
    max_retries = 3                    # 失败重试3次
    
    async def execute(self, context: JobContext):
        """任务执行逻辑"""
        print(f"执行时间: {context.scheduled_time}")
        print(f"执行次数: {context.run_count}")
        # 业务逻辑...
        return {"status": "success", "records": 100}

# 方式2：使用装饰器配置
@cron("0 2 * * *")
@job_config(name="每日报表", concurrent=False, max_retries=3)
class ReportJob(Job):
    async def execute(self, context: JobContext):
        pass

# 注册类任务
scheduler.add_job_class(ReportJob)
```

### 3. 动态任务（运行时添加）

```python
# Lambda/匿名函数
scheduler.add_job(
    lambda: print("动态任务"),
    trigger=period(1000),
    id="dynamic_task"
)

# 带参数的函数
def process_user(user_id: int, action: str):
    print(f"处理用户 {user_id}: {action}")

scheduler.add_job(
    process_user,
    trigger=interval(minutes=10),
    id="process_user_task",
    args=[123],
    kwargs={"action": "sync"}
)
```

---

## Builder 模式（链式配置）

提供流畅的链式 API，适合复杂任务配置。

```python
from yweb.scheduler import JobBuilder, cron

# 链式配置
job = (
    JobBuilder(daily_report)              # 指定任务函数
    .id("daily_report")                   # 任务ID
    .name("每日报表生成")                  # 任务名称
    .description("每天凌晨2点生成销售报表")  # 描述
    .trigger(cron("0 2 * * *"))           # 触发器
    .concurrent(False)                    # 禁止并发执行
    .max_retries(3)                       # 失败重试次数
    .retry_delay(60)                      # 重试间隔（秒）
    .timeout(300)                         # 执行超时（秒）
    .on_success(notify_success)           # 成功回调
    .on_failure(notify_failure)           # 失败回调
    .build()
)

# 添加到调度器
scheduler.add_job(job)

# 简化版：一行代码
scheduler.add_job(
    JobBuilder(sync_data)
    .name("数据同步")
    .trigger(interval(minutes=30))
    .concurrent(False)
    .build()
)
```

### JobBuilder API

| 方法 | 说明 | 默认值 |
|------|------|--------|
| `.id(str)` | 任务ID | 自动生成 |
| `.name(str)` | 任务名称 | 函数名 |
| `.description(str)` | 任务描述 | None |
| `.trigger(Trigger)` | 触发器 | 必填 |
| `.concurrent(bool)` | 是否允许并发 | True |
| `.max_retries(int)` | 最大重试次数 | 0 |
| `.retry_delay(int)` | 重试延迟（秒） | 60 |
| `.timeout(int)` | 超时时间（秒） | None |
| `.enabled(bool)` | 是否启用 | True |
| `.on_success(func)` | 成功回调 | None |
| `.on_failure(func)` | 失败回调 | None |
| `.build()` | 构建任务 | - |

---

## 多触发器支持

一个任务可以绑定多个触发器，在不同时间点执行。

```python
from yweb.scheduler import cron, interval

# 方式1：装饰器叠加
@scheduler.cron("0 9 * * *")      # 早上9点
@scheduler.cron("0 14 * * *")     # 下午2点
@scheduler.cron("0 18 * * *")     # 晚上6点
async def send_reminder():
    """每天发送三次提醒"""
    pass

# 方式2：triggers 列表
@scheduler.job(
    triggers=[
        cron("0 9 * * *"),
        cron("0 14 * * *"),
        cron("0 18 * * *"),
    ],
    id="send_reminder",
    name="定时提醒"
)
async def send_reminder():
    pass

# 方式3：动态添加
scheduler.add_job(
    send_reminder,
    triggers=[
        cron("0 9 * * *"),
        cron("0 14 * * *"),
        cron("0 18 * * *"),
    ],
    id="send_reminder"
)

# 方式4：Builder 模式
job = (
    JobBuilder(send_reminder)
    .id("send_reminder")
    .name("定时提醒")
    .triggers([
        cron("0 9 * * *"),
        cron("0 14 * * *"),
        cron("0 18 * * *"),
    ])
    .build()
)
```

---

## 失败重试策略

提供灵活的失败重试机制。

### 配置重试

```python
# 装饰器方式
@scheduler.cron(
    "0 2 * * *",
    max_retries=3,              # 最多重试3次
    retry_delay=60,             # 重试间隔60秒
    retry_backoff=2,            # 指数退避因子（60, 120, 240秒）
)
async def daily_report():
    pass

# Builder 方式
job = (
    JobBuilder(daily_report)
    .trigger(cron("0 2 * * *"))
    .max_retries(3)
    .retry_delay(60)
    .retry_backoff(2)           # 指数退避
    .retry_on(ConnectionError, TimeoutError)  # 只对特定异常重试
    .build()
)
```

### 重试策略类型

```python
from yweb.scheduler import RetryStrategy

# 固定间隔重试
RetryStrategy.fixed(max_retries=3, delay=60)

# 指数退避重试
RetryStrategy.exponential(max_retries=5, initial_delay=10, factor=2, max_delay=300)

# 自定义重试
RetryStrategy.custom(
    max_retries=3,
    delay_func=lambda attempt: attempt * 30,  # 30, 60, 90秒
    should_retry=lambda exc: isinstance(exc, (ConnectionError, TimeoutError))
)

# 使用
@scheduler.cron("0 2 * * *", retry=RetryStrategy.exponential(max_retries=5))
async def daily_report():
    pass
```

### 重试事件监听

```python
@scheduler.on_job_retry
async def on_retry(event: JobRetryEvent):
    print(f"任务 {event.job_id} 第 {event.attempt} 次重试")
    print(f"原因: {event.error}")
    print(f"下次重试时间: {event.next_retry_time}")
```

---

## HTTP 任务

内置 HTTP 任务支持，无需编写代码即可调用 API。

### 基础用法

```python
from yweb.scheduler import HttpJob

# 方式1：快捷方法
scheduler.add_http_job(
    url="https://api.example.com/webhook",
    method="POST",
    trigger=cron("0 * * * *"),  # 每小时执行
    id="call_webhook",
    name="调用外部 Webhook"
)

# 方式2：详细配置
scheduler.add_http_job(
    url="https://api.example.com/sync",
    method="POST",
    headers={
        "Authorization": "Bearer xxx",
        "Content-Type": "application/json"
    },
    json={"action": "sync", "source": "scheduler"},
    timeout=30,
    trigger=interval(minutes=30),
    id="sync_api",
    # 响应处理
    success_codes=[200, 201],
    retry_on_codes=[500, 502, 503],
)

# 方式3：HttpJob 类
class WebhookJob(HttpJob):
    """Webhook 调用任务"""
    
    trigger = cron("0 * * * *")
    url = "https://api.example.com/webhook"
    method = "POST"
    timeout = 30
    max_retries = 3
    
    def build_request(self, context: JobContext) -> dict:
        """动态构建请求参数"""
        return {
            "headers": {"Authorization": f"Bearer {get_token()}"},
            "json": {
                "timestamp": context.scheduled_time.isoformat(),
                "job_id": context.job_id,
            }
        }
    
    async def on_response(self, response, context: JobContext):
        """处理响应"""
        if response.status_code == 200:
            data = response.json()
            print(f"Webhook 返回: {data}")

scheduler.add_job_class(WebhookJob)
```

### HTTP 任务配置

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `url` | 请求 URL | 必填 |
| `method` | HTTP 方法 | GET |
| `headers` | 请求头 | {} |
| `params` | URL 参数 | {} |
| `json` | JSON 请求体 | None |
| `data` | Form 请求体 | None |
| `timeout` | 超时时间（秒） | 30 |
| `success_codes` | 成功状态码 | [200] |
| `retry_on_codes` | 需重试的状态码 | [500, 502, 503, 504] |

---

## 配置设计

### SchedulerSettings

```python
# yweb/config/settings.py

class SchedulerSettings(BaseSettings):
    """定时任务配置
    
    使用示例:
        from yweb.config import SchedulerSettings
        
        config = SchedulerSettings(
            store="orm",              # 使用数据库持久化
            timezone="Asia/Shanghai",
            misfire_grace_time=60,
        )
    
    环境变量:
        YWEB_SCHEDULER_ENABLED=true
        YWEB_SCHEDULER_STORE=orm
        YWEB_SCHEDULER_TIMEZONE=Asia/Shanghai
    """
    
    # 基础配置
    enabled: bool = Field(default=True, description="是否启用定时任务")
    timezone: str = Field(default="Asia/Shanghai", description="时区")
    
    # 存储配置
    store: str = Field(
        default="memory", 
        description="任务存储方式: memory | orm"
    )
    
    # 执行器配置
    max_workers: int = Field(default=10, description="最大并发执行数")
    default_executor: str = Field(
        default="async", 
        description="默认执行器: async | thread"
    )
    
    # 容错配置
    misfire_grace_time: int = Field(
        default=60, 
        description="任务错过执行的宽限时间（秒），超过此时间的任务不再执行"
    )
    coalesce: bool = Field(
        default=True, 
        description="是否合并错过的多次执行为一次"
    )
    
    # 分布式配置（可选）
    distributed_lock: bool = Field(
        default=False, 
        description="是否启用分布式锁（需要 Redis）"
    )
    redis_url: Optional[str] = Field(
        default=None, 
        description="Redis URL，用于分布式锁"
    )
    lock_timeout: int = Field(
        default=300, 
        description="分布式锁超时时间（秒）"
    )
    
    # 监控配置
    enable_history: bool = Field(
        default=True, 
        description="是否记录执行历史"
    )
    history_retention_days: int = Field(
        default=30, 
        description="历史记录保留天数"
    )
    
    class Config:
        env_prefix = "YWEB_SCHEDULER_"
```

### 使用配置

```python
from yweb import Scheduler
from yweb.config import SchedulerSettings

# 方式1：使用默认配置
scheduler = Scheduler()

# 方式2：自定义配置
config = SchedulerSettings(
    store="orm",
    timezone="Asia/Shanghai",
    max_workers=20,
)
scheduler = Scheduler(settings=config)

# 方式3：从环境变量加载
# 设置 YWEB_SCHEDULER_STORE=orm
scheduler = Scheduler()  # 自动读取环境变量
```

---

## 持久化设计（基于 YWeb ORM）

### 任务定义模型

```python
# yweb/scheduler/models.py

from sqlalchemy import Column, String, Text, DateTime, Integer, Boolean, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from yweb.orm import CoreModel

class SchedulerJob(CoreModel):
    """定时任务表
    
    存储任务定义，支持应用重启后恢复任务。
    
    标识说明：
    - id: 继承自 CoreModel，自动生成（UUID/雪花ID）
    - code: 业务编码，用户定义，用于 API 操作
    - name: 任务名称，用于展示
    - description: 任务描述
    """
    __tablename__ = "scheduler_job"
    
    # ===== 任务标识 =====
    # id 继承自 CoreModel，自动生成
    code: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, 
        comment="业务编码，用于API操作"
    )
    name: Mapped[str] = mapped_column(String(200), comment="任务名称")
    description: Mapped[str] = mapped_column(Text, nullable=True, comment="任务描述")
    
    # ===== 触发器配置 =====
    trigger_type: Mapped[str] = mapped_column(
        String(50), comment="触发器类型: cron|interval|once"
    )
    trigger_args: Mapped[dict] = mapped_column(JSON, comment="触发器参数")
    
    # ===== 任务目标 =====
    func_ref: Mapped[str] = mapped_column(String(500), comment="函数引用路径")
    args: Mapped[list] = mapped_column(JSON, default=list, comment="位置参数")
    kwargs: Mapped[dict] = mapped_column(JSON, default=dict, comment="关键字参数")
    
    # ===== 执行配置 =====
    executor: Mapped[str] = mapped_column(String(50), default="async", comment="执行器")
    concurrent: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否允许并发执行")
    max_instances: Mapped[int] = mapped_column(Integer, default=1, comment="最大并发实例数")
    timeout: Mapped[int] = mapped_column(Integer, nullable=True, comment="执行超时（秒）")
    
    # ===== 重试配置 =====
    max_retries: Mapped[int] = mapped_column(Integer, default=0, comment="最大重试次数")
    retry_delay: Mapped[int] = mapped_column(Integer, default=60, comment="重试间隔（秒）")
    retry_backoff: Mapped[float] = mapped_column(Integer, default=1, comment="退避因子")
    
    # ===== 容错配置 =====
    misfire_grace_time: Mapped[int] = mapped_column(
        Integer, nullable=True, comment="错过执行宽限时间（秒）"
    )
    coalesce: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="是否合并错过的执行"
    )
    
    # ===== 状态 =====
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, index=True, comment="是否启用"
    )
    next_run_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=True, index=True, comment="下次执行时间"
    )
    
    # ===== 统计 =====
    run_count: Mapped[int] = mapped_column(Integer, default=0, comment="累计执行次数")
    success_count: Mapped[int] = mapped_column(Integer, default=0, comment="成功次数")
    fail_count: Mapped[int] = mapped_column(Integer, default=0, comment="失败次数")
    last_run_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=True, comment="上次执行时间"
    )
    last_run_id: Mapped[str] = mapped_column(
        String(50), nullable=True, comment="上次执行ID"
    )
    last_status: Mapped[str] = mapped_column(
        String(20), nullable=True, comment="上次执行状态"
    )


class SchedulerJobHistory(CoreModel):
    """任务执行历史表
    
    记录每次任务执行的详细信息。每次执行产生一条记录。
    
    标识说明：
    - id: 继承自 CoreModel，自动生成
    - run_id: 执行唯一标识，格式 run_{日期}_{时间}_{随机串}
    - job_id: 关联的任务ID
    - job_code: 关联的任务编码（冗余，便于查询）
    """
    __tablename__ = "scheduler_job_history"
    
    # ===== 执行标识 =====
    run_id: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, 
        comment="执行ID，如 run_20260121_080000_a1b2c3"
    )
    
    # ===== 任务关联 =====
    job_id: Mapped[str] = mapped_column(String(50), index=True, comment="任务ID")
    job_code: Mapped[str] = mapped_column(String(100), index=True, comment="任务编码")
    job_name: Mapped[str] = mapped_column(String(200), nullable=True, comment="任务名称（快照）")
    
    # ===== 时间信息 =====
    scheduled_time: Mapped[datetime] = mapped_column(DateTime, comment="计划执行时间")
    start_time: Mapped[datetime] = mapped_column(DateTime, comment="实际开始时间")
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="结束时间")
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=True, comment="执行耗时(毫秒)")
    
    # ===== 执行状态 =====
    status: Mapped[str] = mapped_column(
        String(20), index=True, 
        comment="状态: pending|running|success|failed|timeout|cancelled"
    )
    
    # ===== 结果信息 =====
    result: Mapped[str] = mapped_column(Text, nullable=True, comment="返回值(JSON)")
    error: Mapped[str] = mapped_column(Text, nullable=True, comment="错误信息")
    traceback: Mapped[str] = mapped_column(Text, nullable=True, comment="错误堆栈")
    
    # ===== 重试信息 =====
    attempt: Mapped[int] = mapped_column(Integer, default=1, comment="第几次尝试（首次为1）")
    retry_of: Mapped[str] = mapped_column(
        String(50), nullable=True, 
        comment="重试的原执行ID（首次执行为空）"
    )
    
    # ===== 触发信息 =====
    trigger_type: Mapped[str] = mapped_column(
        String(20), default="scheduled",
        comment="触发类型: scheduled|manual|retry"
    )
    
    # ===== 执行环境 =====
    hostname: Mapped[str] = mapped_column(String(100), nullable=True, comment="执行主机")
    process_id: Mapped[int] = mapped_column(Integer, nullable=True, comment="进程ID")
```

### ORM 存储实现

```python
# yweb/scheduler/stores/orm.py

from apscheduler.jobstores.base import BaseJobStore, JobLookupError
from yweb.orm import db_manager
from ..models import SchedulerJob

class ORMJobStore(BaseJobStore):
    """基于 YWeb ORM 的任务存储
    
    使用 YWeb 的 ORM 模块存储任务，支持：
    - 应用重启后任务恢复
    - 多实例部署时任务共享
    - 任务状态持久化
    """
    
    def __init__(self):
        super().__init__()
        self._session = None
    
    @property
    def session(self):
        if self._session is None:
            self._session = db_manager.get_session()
        return self._session
    
    def add_job(self, job):
        """添加任务"""
        scheduler_job = SchedulerJob(
            # id 自动生成
            code=job.code,
            name=job.name,
            description=job.description,
            trigger_type=job.trigger.__class__.__name__.lower().replace('trigger', ''),
            trigger_args=self._serialize_trigger(job.trigger),
            func_ref=f"{job.func.__module__}:{job.func.__qualname__}",
            args=list(job.args) if job.args else [],
            kwargs=dict(job.kwargs) if job.kwargs else {},
            executor=job.executor,
            concurrent=job.concurrent,
            max_instances=job.max_instances,
            max_retries=job.max_retries,
            retry_delay=job.retry_delay,
            misfire_grace_time=job.misfire_grace_time,
            coalesce=job.coalesce,
            next_run_time=job.next_run_time,
        )
        scheduler_job.save()
    
    def update_job(self, job):
        """更新任务"""
        scheduler_job = SchedulerJob.query.filter_by(code=job.code).first()
        if not scheduler_job:
            raise JobLookupError(job.code)
        
        scheduler_job.update(
            next_run_time=job.next_run_time,
            trigger_args=self._serialize_trigger(job.trigger),
        )
    
    def remove_job(self, job_id):
        """删除任务"""
        scheduler_job = SchedulerJob.query.filter_by(job_id=job_id).first()
        if scheduler_job:
            scheduler_job.delete()
    
    def get_all_jobs(self):
        """获取所有任务"""
        jobs = SchedulerJob.query.filter_by(is_enabled=True).all()
        return [self._reconstitute_job(j) for j in jobs]
    
    def get_due_jobs(self, now):
        """获取到期任务"""
        jobs = SchedulerJob.query.filter(
            SchedulerJob.is_enabled == True,
            SchedulerJob.next_run_time <= now
        ).order_by(SchedulerJob.next_run_time).all()
        return [self._reconstitute_job(j) for j in jobs]
    
    # ... 其他方法实现
```

---

## FastAPI 集成

### 基础集成

```python
from fastapi import FastAPI
from yweb import Scheduler

app = FastAPI()
scheduler = Scheduler()

# 方式1：使用 init_app（推荐）
scheduler.init_app(app)

# 方式2：手动管理生命周期
@app.on_event("startup")
async def startup():
    scheduler.start()

@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown()
```

### init_app 实现

```python
# yweb/scheduler/scheduler.py

class Scheduler:
    """定时任务调度器"""
    
    def init_app(self, app: FastAPI):
        """集成到 FastAPI 应用
        
        自动注册启动/关闭事件，无需手动管理生命周期
        """
        @app.on_event("startup")
        async def _start_scheduler():
            if self.settings.enabled:
                self.start()
                logger.info(f"Scheduler started with {len(self.get_jobs())} jobs")
        
        @app.on_event("shutdown")
        async def _shutdown_scheduler():
            if self._running:
                self.shutdown(wait=True)
                logger.info("Scheduler shutdown complete")
        
        # 挂载到 app.state 方便其他地方访问
        app.state.scheduler = self
```

### 依赖注入

```python
from fastapi import Depends
from yweb import Scheduler

def get_scheduler(request: Request) -> Scheduler:
    """获取调度器实例"""
    return request.app.state.scheduler

# 在路由中使用
@app.get("/jobs")
def list_jobs(scheduler: Scheduler = Depends(get_scheduler)):
    return [
        {
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time,
        }
        for job in scheduler.get_jobs()
    ]
```

---

## 分布式支持

### 分布式锁设计

多实例部署时，需要防止同一任务被多个实例同时执行。

```python
# yweb/scheduler/locks/redis_lock.py

import redis
from contextlib import contextmanager

class RedisDistributedLock:
    """Redis 分布式锁
    
    使用 Redis SETNX 实现分布式锁，确保同一任务同时只有一个实例执行
    """
    
    def __init__(self, redis_url: str, lock_timeout: int = 300):
        self.redis = redis.from_url(redis_url)
        self.lock_timeout = lock_timeout
    
    @contextmanager
    def acquire(self, job_id: str):
        """获取锁
        
        使用示例:
            with lock.acquire("my_job") as acquired:
                if acquired:
                    # 执行任务
                    pass
        """
        lock_key = f"scheduler:lock:{job_id}"
        lock_value = f"{socket.gethostname()}:{os.getpid()}:{time.time()}"
        
        # 尝试获取锁
        acquired = self.redis.set(
            lock_key, 
            lock_value, 
            nx=True,  # 仅当 key 不存在时设置
            ex=self.lock_timeout
        )
        
        try:
            yield acquired
        finally:
            if acquired:
                # 只释放自己的锁（Lua 脚本保证原子性）
                self._release_lock(lock_key, lock_value)
    
    def _release_lock(self, key: str, value: str):
        """释放锁（原子操作）"""
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        self.redis.eval(lua_script, 1, key, value)
```

### 使用分布式锁

```python
from yweb import Scheduler
from yweb.config import SchedulerSettings

# 启用分布式锁
config = SchedulerSettings(
    distributed_lock=True,
    redis_url="redis://localhost:6379/0",
    lock_timeout=300,
)

scheduler = Scheduler(settings=config)

# 任务会自动使用分布式锁
@scheduler.cron("0 8 * * *")
async def daily_report():
    # 多实例部署时，只有一个实例会执行此任务
    pass
```

---

## 监控与管理

### 任务事件监听

```python
from yweb import Scheduler
from yweb.scheduler import JobEvent

scheduler = Scheduler()

# 监听任务事件
@scheduler.on_job_executed
async def on_job_success(event: JobEvent):
    """任务执行成功"""
    print(f"Job {event.job_id} executed successfully")
    print(f"  Duration: {event.duration_ms}ms")
    print(f"  Result: {event.result}")

@scheduler.on_job_error
async def on_job_error(event: JobEvent):
    """任务执行失败"""
    print(f"Job {event.job_id} failed: {event.error}")
    # 可以在这里发送告警通知

@scheduler.on_job_missed
async def on_job_missed(event: JobEvent):
    """任务错过执行"""
    print(f"Job {event.job_id} missed at {event.scheduled_time}")
```

### 管理 API（可选）

```python
# yweb/scheduler/api/

from fastapi import APIRouter, Depends, HTTPException
from yweb import Resp, Scheduler

router = APIRouter(prefix="/scheduler", tags=["定时任务"])

@router.get("/jobs")
async def list_jobs(scheduler: Scheduler = Depends(get_scheduler)):
    """获取所有任务"""
    jobs = scheduler.get_jobs()
    return Resp.OK(data=[
        {
            "id": job.id,
            "name": job.name,
            "trigger": str(job.trigger),
            "next_run_time": job.next_run_time,
            "is_paused": job.next_run_time is None,
        }
        for job in jobs
    ])

@router.post("/jobs/{job_id}/run")
async def run_job(job_id: str, scheduler: Scheduler = Depends(get_scheduler)):
    """立即执行任务"""
    job = scheduler.get_job(job_id)
    if not job:
        return Resp.NotFound(message=f"任务 {job_id} 不存在")
    
    scheduler.run_job(job_id)
    return Resp.OK(message=f"任务 {job_id} 已触发执行")

@router.post("/jobs/{job_id}/pause")
async def pause_job(job_id: str, scheduler: Scheduler = Depends(get_scheduler)):
    """暂停任务"""
    scheduler.pause_job(job_id)
    return Resp.OK(message=f"任务 {job_id} 已暂停")

@router.post("/jobs/{job_id}/resume")
async def resume_job(job_id: str, scheduler: Scheduler = Depends(get_scheduler)):
    """恢复任务"""
    scheduler.resume_job(job_id)
    return Resp.OK(message=f"任务 {job_id} 已恢复")

@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str, scheduler: Scheduler = Depends(get_scheduler)):
    """删除任务"""
    scheduler.remove_job(job_id)
    return Resp.OK(message=f"任务 {job_id} 已删除")

@router.get("/history")
async def get_history(
    job_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
):
    """获取执行历史"""
    query = SchedulerJobHistory.query
    
    if job_id:
        query = query.filter_by(job_id=job_id)
    if status:
        query = query.filter_by(status=status)
    
    history = query.order_by(SchedulerJobHistory.start_time.desc()).limit(limit).all()
    
    return Resp.OK(data=[h.to_dict() for h in history])

@router.get("/stats")
async def get_stats(scheduler: Scheduler = Depends(get_scheduler)):
    """获取执行统计"""
    stats = scheduler.get_stats()
    return Resp.OK(data=stats)
```

---

## 执行统计

提供任务执行的统计信息，用于监控和分析。

### 统计数据模型

```python
# yweb/scheduler/models.py

class SchedulerJobStats(CoreModel):
    """任务执行统计表
    
    按天/小时聚合的执行统计
    """
    __tablename__ = "scheduler_job_stats"
    
    # 统计维度
    job_id: Mapped[str] = mapped_column(String(200), index=True, comment="任务ID")
    stat_date: Mapped[date] = mapped_column(Date, index=True, comment="统计日期")
    stat_hour: Mapped[int] = mapped_column(Integer, nullable=True, comment="统计小时（0-23），NULL表示天级统计")
    
    # 执行次数
    total_runs: Mapped[int] = mapped_column(Integer, default=0, comment="总执行次数")
    success_runs: Mapped[int] = mapped_column(Integer, default=0, comment="成功次数")
    failed_runs: Mapped[int] = mapped_column(Integer, default=0, comment="失败次数")
    timeout_runs: Mapped[int] = mapped_column(Integer, default=0, comment="超时次数")
    retry_runs: Mapped[int] = mapped_column(Integer, default=0, comment="重试次数")
    
    # 耗时统计（毫秒）
    min_duration: Mapped[int] = mapped_column(Integer, nullable=True, comment="最小耗时")
    max_duration: Mapped[int] = mapped_column(Integer, nullable=True, comment="最大耗时")
    avg_duration: Mapped[int] = mapped_column(Integer, nullable=True, comment="平均耗时")
    total_duration: Mapped[int] = mapped_column(Integer, default=0, comment="总耗时")
    
    # 唯一约束
    __table_args__ = (
        UniqueConstraint('job_id', 'stat_date', 'stat_hour', name='uix_job_stats'),
    )
```

### 获取统计信息

```python
# 获取全局统计
stats = scheduler.get_stats()
# {
#     "total_jobs": 10,
#     "active_jobs": 8,
#     "paused_jobs": 2,
#     "today": {
#         "total_runs": 156,
#         "success_runs": 150,
#         "failed_runs": 6,
#         "success_rate": 96.15,
#         "avg_duration_ms": 1234
#     },
#     "last_24h": {...},
#     "last_7d": {...}
# }

# 获取单个任务统计（通过 code）
job_stats = scheduler.get_job_stats("DAILY_REPORT")
# {
#     "code": "DAILY_REPORT",
#     "name": "每日报表",
#     "description": "每天早上8点生成销售报表",
#     "total_runs": 30,
#     "success_runs": 28,
#     "failed_runs": 2,
#     "success_rate": 93.33,
#     "avg_duration_ms": 5678,
#     "last_run_id": "run_20260121_080000_a1b2c3",
#     "last_run_time": "2026-01-21 08:00:00",
#     "last_status": "success",
#     "next_run_time": "2026-01-22 08:00:00"
# }

# 获取时间范围内的统计
stats = scheduler.get_stats(
    code="DAILY_REPORT",
    start_date="2026-01-01",
    end_date="2026-01-21",
    granularity="day"  # day | hour
)
```

### 统计面板数据

```python
@router.get("/dashboard")
async def get_dashboard(scheduler: Scheduler = Depends(get_scheduler)):
    """获取仪表板数据"""
    return Resp.OK(data={
        # 概览
        "overview": scheduler.get_stats(),
        
        # 最近执行
        "recent_executions": scheduler.get_recent_executions(limit=10),
        
        # 失败任务
        "failed_jobs": scheduler.get_failed_jobs(hours=24),
        
        # 即将执行
        "upcoming_jobs": scheduler.get_upcoming_jobs(limit=10),
        
        # 执行趋势（最近7天）
        "trend": scheduler.get_execution_trend(days=7),
    })
```

---

## 使用示例

### 1. 最简单的用法（零配置）

```python
from fastapi import FastAPI
from yweb import Scheduler

app = FastAPI()
scheduler = Scheduler()

# 一行代码添加定时任务
@scheduler.cron("0 8 * * *")
async def daily_report():
    """每天早上8点执行"""
    print("生成日报...")

@scheduler.interval(minutes=30)
async def sync_data():
    """每30分钟执行"""
    print("同步数据...")

# 集成到 FastAPI（自动启动/停止）
scheduler.init_app(app)
```

### 2. 带配置的任务

```python
@scheduler.cron(
    "0 2 * * *",
    code="CLEANUP_DAILY",                # 业务编码
    name="每日清理",                       # 名称
    description="每天凌晨2点清理90天前的过期数据",  # 描述
    max_retries=3,                        # 失败重试3次
    concurrent=False,                     # 禁止并发执行
)
async def daily_cleanup():
    await cleanup_expired_records()
```

### 3. 一次性任务（延迟执行）

```python
from datetime import datetime, timedelta

# 5分钟后执行
@scheduler.once(run_date=datetime.now() + timedelta(minutes=5))
async def send_welcome_email():
    await send_email(user_id=123, template="welcome")

# 指定时间执行
@scheduler.once("2026-12-31 23:59:59")
async def new_year_task():
    print("新年快乐！")
```

### 4. 动态添加任务

```python
from yweb import Scheduler, cron, interval

scheduler = Scheduler()

# 运行时动态添加
def create_user_reminder(user_id: int, cron_expr: str):
    async def reminder():
        await notify_user(user_id, "该喝水了！")
    
    scheduler.add_job(
        reminder,
        trigger=cron(cron_expr),
        code=f"REMINDER_USER_{user_id}",      # 业务编码（包含业务标识）
        name=f"用户 {user_id} 的提醒",
        description=f"用户 {user_id} 的喝水提醒任务",
        replace_existing=True,
    )

# API 中调用
@app.post("/users/{user_id}/reminder")
def set_reminder(user_id: int, cron_expr: str):
    create_user_reminder(user_id, cron_expr)
    return Resp.OK(message="提醒已设置")
```

### 5. 类任务（复杂逻辑）

```python
from yweb.scheduler import Job, cron, JobContext

class ReportJob(Job):
    """每日报表任务"""
    
    code = "REPORT_DAILY_SALES"
    name = "每日销售报表"
    description = "每天凌晨2点生成前一天的销售汇总报表"
    trigger = cron("0 2 * * *")
    concurrent = False
    max_retries = 3
    
    async def execute(self, context: JobContext):
        # 执行上下文包含完整信息
        print(f"任务编码: {context.job_code}")        # REPORT_DAILY_SALES
        print(f"执行ID: {context.run_id}")           # run_20260121_020000_a1b2c3
        print(f"计划时间: {context.scheduled_time}") # 2026-01-21 02:00:00
        print(f"第 {context.attempt} 次尝试")        # 1 或 2,3（重试时）
        
        # 业务逻辑
        data = await generate_report()
        await save_to_oss(data)
        await notify_admin("报表已生成")
        
        return {"status": "success", "records": len(data)}

# 注册类任务
scheduler.add_job_class(ReportJob)
```

### 6. HTTP 任务（调用外部 API）

```python
# 简单方式：调用 Webhook
scheduler.add_http_job(
    url="https://api.example.com/webhook",
    method="POST",
    headers={"Authorization": "Bearer xxx"},
    json={"action": "sync"},
    trigger=cron("0 * * * *"),  # 每小时执行
    code="WEBHOOK_SYNC",
    name="同步 Webhook",
)
```

### 7. Builder 模式（链式配置）

```python
from yweb.scheduler import JobBuilder, cron, RetryStrategy

job = (
    JobBuilder(send_notification)
    .code("NOTIFY_DAILY")
    .name("每日通知")
    .description("每天早上9点发送系统通知")
    .trigger(cron("0 9 * * *"))
    .concurrent(False)
    .retry(RetryStrategy.exponential(max_retries=5))
    .timeout(60)
    .build()
)

scheduler.add_job(job)
```

### 8. 多触发器（一个任务多个时间点）

```python
@scheduler.job(
    triggers=[
        cron("0 9 * * *"),   # 早上9点
        cron("0 14 * * *"),  # 下午2点
        cron("0 18 * * *"),  # 晚上6点
    ],
    code="REMINDER_REST",
    name="休息提醒",
    description="每天三次提醒员工休息"
)
async def send_reminder():
    await push_notification("记得休息！")
```

### 9. 任务管理操作

```python
# 通过 code 操作任务（推荐）

# 暂停任务
scheduler.pause_job("DAILY_REPORT")

# 恢复任务
scheduler.resume_job("DAILY_REPORT")

# 立即执行一次（不影响正常调度），返回 run_id
run_id = scheduler.run_job("DAILY_REPORT")
print(f"已触发执行，run_id: {run_id}")

# 删除任务
scheduler.remove_job("DAILY_REPORT")

# 查看所有任务
for job in scheduler.get_jobs():
    print(f"{job.code}: {job.name}")
    print(f"  描述: {job.description}")
    print(f"  下次执行: {job.next_run_time}")

# 获取单个任务
job = scheduler.get_job("DAILY_REPORT")
print(f"任务 {job.code} 累计执行 {job.run_count} 次")

# 获取执行历史
executions = scheduler.get_executions("DAILY_REPORT", limit=5)
for exe in executions:
    print(f"  {exe.run_id}: {exe.status}, 耗时 {exe.duration_ms}ms")
```

### 10. 事件监听（监控告警）

```python
@scheduler.on_job_error
async def on_error(event):
    """任务失败时发送告警"""
    await send_dingtalk_alert(
        f"任务 {event.job_code}({event.job_name}) 执行失败\n"
        f"执行ID: {event.run_id}\n"
        f"错误: {event.error}"
    )

@scheduler.on_job_executed
async def on_success(event):
    """任务成功时记录日志"""
    print(f"[{event.run_id}] 任务 {event.job_code} 执行成功，耗时 {event.duration_ms}ms")

@scheduler.on_job_retry
async def on_retry(event):
    """任务重试时通知"""
    print(f"[{event.run_id}] 任务 {event.job_code} 第 {event.attempt} 次重试")
```

### 11. 完整项目示例

```python
# main.py
from fastapi import FastAPI
from yweb import Scheduler, Resp
from yweb.config import SchedulerSettings
from yweb.scheduler import JobContext
from datetime import datetime

# ========== 配置 ==========
config = SchedulerSettings(
    store="orm",              # 使用数据库持久化
    timezone="Asia/Shanghai",
    enable_history=True,      # 记录执行历史
)

# ========== 创建调度器 ==========
scheduler = Scheduler(settings=config)

# ========== 定义定时任务 ==========

@scheduler.cron(
    "0 8 * * *",
    code="REPORT_DAILY",
    name="每日报表",
    description="每天早上8点生成销售日报"
)
async def generate_daily_report(context: JobContext):
    """每天8点生成日报"""
    print(f"[{context.run_id}] 开始生成日报...")
    # 业务逻辑
    return {"status": "success", "records": 100}

@scheduler.interval(
    minutes=30,
    code="SYNC_DATA",
    name="数据同步",
    description="每30分钟同步外部数据"
)
async def sync_external_data(context: JobContext):
    """每30分钟同步外部数据"""
    print(f"[{context.run_id}] 同步数据...")

@scheduler.cron(
    "0 0 * * 0",
    code="CLEANUP_WEEKLY",
    name="每周清理",
    description="每周日凌晨清理90天前的过期数据"
)
async def weekly_cleanup(context: JobContext):
    """每周日凌晨清理过期数据"""
    print(f"[{context.run_id}] 清理过期数据...")

# ========== 错误告警 ==========

@scheduler.on_job_error
async def handle_job_error(event):
    """任务失败时发送告警"""
    print(f"[{event.run_id}] 任务 {event.job_code} 执行失败: {event.error}")
    # 发送钉钉/企微/邮件告警

# ========== FastAPI 应用 ==========

app = FastAPI(title="My App")

# 集成调度器（自动管理生命周期）
scheduler.init_app(app)

@app.get("/")
def index():
    return Resp.OK(data={"message": "Hello World"})

# ========== 任务管理接口（通过 code 操作） ==========

@app.get("/scheduler/jobs")
def list_jobs():
    """查看所有定时任务"""
    return Resp.OK(data=[
        {
            "code": job.code,
            "name": job.name,
            "description": job.description,
            "next_run": str(job.next_run_time),
            "is_paused": job.next_run_time is None,
            "run_count": job.run_count,
        }
        for job in scheduler.get_jobs()
    ])

@app.post("/scheduler/jobs/{code}/run")
def trigger_job(code: str):
    """手动触发任务"""
    job = scheduler.get_job(code)
    if not job:
        return Resp.NotFound(message="任务不存在")
    run_id = scheduler.run_job(code)
    return Resp.OK(data={"run_id": run_id}, message=f"任务 {code} 已触发")

@app.post("/scheduler/jobs/{code}/pause")
def pause_job(code: str):
    """暂停任务"""
    scheduler.pause_job(code)
    return Resp.OK(message=f"任务 {code} 已暂停")

@app.post("/scheduler/jobs/{code}/resume")
def resume_job(code: str):
    """恢复任务"""
    scheduler.resume_job(code)
    return Resp.OK(message=f"任务 {code} 已恢复")

@app.delete("/scheduler/jobs/{code}")
def delete_job(code: str):
    """删除任务"""
    scheduler.remove_job(code)
    return Resp.OK(message=f"任务 {code} 已删除")

@app.get("/scheduler/jobs/{code}/executions")
def get_job_executions(code: str, limit: int = 20):
    """获取任务执行历史"""
    executions = scheduler.get_executions(code, limit=limit)
    return Resp.OK(data=[
        {
            "run_id": exe.run_id,
            "scheduled_time": str(exe.scheduled_time),
            "status": exe.status,
            "duration_ms": exe.duration_ms,
            "attempt": exe.attempt,
        }
        for exe in executions
    ])

@app.get("/scheduler/executions/{run_id}")
def get_execution_detail(run_id: str):
    """获取某次执行的详情"""
    execution = scheduler.get_execution(run_id)
    if not execution:
        return Resp.NotFound(message="执行记录不存在")
    return Resp.OK(data=execution.to_dict())

@app.get("/scheduler/stats")
def get_stats():
    """获取执行统计"""
    return Resp.OK(data=scheduler.get_stats())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### 12. 使用场景速查表

| 场景 | 推荐方式 | 示例 |
|------|----------|------|
| 简单定时任务 | 装饰器 | `@scheduler.cron("0 8 * * *")` |
| 复杂业务逻辑 | Job 类 | `class ReportJob(Job)` |
| 运行时创建 | add_job() | `scheduler.add_job(func, trigger=...)` |
| 调用外部 API | HTTP 任务 | `scheduler.add_http_job(url=...)` |
| 复杂配置 | Builder | `JobBuilder(func).name(...).build()` |
| 多时间点执行 | 多触发器 | `triggers=[cron(...), cron(...)]` |
| 延迟执行 | once() | `@scheduler.once(run_date=...)` |

---

## 实现计划

### 阶段一：核心功能（MVP）

| 功能 | 优先级 | 说明 |
|------|--------|------|
| Scheduler 核心类 | P0 | 基于 APScheduler 封装 |
| 装饰器 API | P0 | @scheduler.cron, @scheduler.interval, @scheduler.once |
| 触发器函数 | P0 | cron(), interval(), once() |
| 任务管理 | P0 | 暂停/恢复/删除/立即执行 |
| 内存存储 | P0 | 默认存储方式 |
| FastAPI 集成 | P0 | init_app() 方法 |
| SchedulerSettings | P0 | 配置类 |
| 并发控制 | P0 | max_instances, concurrent 参数 |

### 阶段二：持久化 & 任务类型

| 功能 | 优先级 | 说明 |
|------|--------|------|
| ORM 模型 | P1 | SchedulerJob, SchedulerJobHistory, SchedulerJobStats |
| ORM 存储 | P1 | 基于 YWeb ORM 的 JobStore |
| 执行历史 | P1 | 记录每次执行的结果 |
| Job 类支持 | P1 | 声明式类任务 |
| Builder 模式 | P1 | JobBuilder 链式配置 |
| 多触发器 | P1 | 一个任务多个触发器 |

### 阶段三：高级功能

| 功能 | 优先级 | 说明 |
|------|--------|------|
| 失败重试策略 | P2 | RetryStrategy（固定/指数退避/自定义） |
| HTTP 任务 | P2 | HttpJob，内置 HTTP 调用 |
| 分布式锁 | P2 | Redis 实现，防止重复执行 |
| 事件监听 | P2 | on_job_executed, on_job_error, on_job_retry |
| 执行统计 | P2 | 按天/小时聚合统计 |
| 管理 API | P2 | REST API 管理任务 |
| 仪表板数据 | P2 | 概览、趋势、失败任务等 |
| 历史清理 | P2 | 自动清理过期历史记录 |

---

## 导出设计

```python
# yweb/scheduler/__init__.py

from .scheduler import Scheduler
from .triggers import cron, interval, once
from .job import Job, JobContext, JobEvent, JobRetryEvent
from .builder import JobBuilder
from .http_job import HttpJob
from .retry import RetryStrategy
from .models import SchedulerJob, SchedulerJobHistory, SchedulerJobStats

__all__ = [
    # ===== 核心类（推荐） =====
    "Scheduler",            # 调度器
    "JobBuilder",           # 链式配置
    
    # ===== 触发器 =====
    "cron",                 # Cron 表达式
    "interval",             # 时间间隔
    "once",                 # 一次性
    
    # ===== 任务基类 =====
    "Job",                  # 任务基类
    "HttpJob",              # HTTP 任务基类
    
    # ===== 重试策略 =====
    "RetryStrategy",        # 重试策略
    
    # ===== 上下文/事件 =====
    "JobContext",           # 任务执行上下文
    "JobEvent",             # 任务事件
    "JobRetryEvent",        # 重试事件
    
    # ===== ORM 模型（高级用法） =====
    "SchedulerJob",         # 任务表
    "SchedulerJobHistory",  # 执行历史表
    "SchedulerJobStats",    # 统计表
]

# yweb/__init__.py 中添加
from .scheduler import (
    Scheduler,
    JobBuilder,
    JobContext,
    cron, interval, once,
    Job, HttpJob,
    RetryStrategy,
)
```

---

## 功能清单

| 功能 | 状态 | 说明 |
|------|------|------|
| **标识体系** | ✅ | id（自动）、code（业务）、name、description |
| **执行追踪** | ✅ | run_id 唯一标识每次执行 |
| 一行代码添加任务 | ✅ | 装饰器方式 |
| 零配置启动 | ✅ | 默认内存存储 |
| 链式配置 (Builder) | ✅ | JobBuilder |
| Cron 触发器 | ✅ | cron() |
| 间隔触发器 | ✅ | interval() |
| 特定时间触发 | ✅ | once() |
| 类任务 | ✅ | Job 基类 |
| 动态任务 | ✅ | add_job() |
| HTTP 任务 | ✅ | HttpJob |
| 暂停/恢复/删除 | ✅ | pause_job, resume_job, remove_job（通过 code） |
| 立即执行 | ✅ | run_job() 返回 run_id |
| 执行上下文 | ✅ | JobContext（job_code, run_id, attempt 等） |
| 执行历史查询 | ✅ | get_executions(), get_execution() |
| 集群支持 | ✅ | Redis 分布式锁 |
| 失败重试 | ✅ | RetryStrategy，attempt 计数 |
| 执行统计 | ✅ | SchedulerJobStats |
| 多触发器 | ✅ | triggers 列表 |
| 并发控制 | ✅ | concurrent, max_instances |

---

**版本:** v0.3.0 (设计稿) | **更新日期:** 2026-01-21

**设计原则:**
- 一行代码添加任务，零配置启动
- 清晰的标识体系：id 自动生成、code 业务编码、run_id 执行追踪
- 遵循 YWeb 的 API 风格（快捷类、装饰器、配置类）
- 多样化触发方式，丰富的任务类型
- 完善的监控管理，失败重试支持
- 集群支持，防止重复执行
- 与 YWeb ORM 深度集成
