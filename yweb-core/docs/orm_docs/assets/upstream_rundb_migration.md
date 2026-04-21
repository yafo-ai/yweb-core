# 上游项目 `run_db` → `async_db_call` 迁移指南

> 本文件是 Phase 8.7 的产物：yweb-core 2026-04 把 `run_db` 重命名为 `async_db_call`，
> 旧名保留为 deprecated alias（DeprecationWarning）。上游项目升级 yweb 版本后按本
> 指南迁移。每个上游项目一个章节，记录扫描结果与改动清单，可追溯。

- 关联 commit：`ff97dc6 refactor(orm)! 将 run_db 重命名为 async_db_call，保留旧名为 deprecated alias`
- 关联文档：`../22_hybrid_query_sync_async_refactor.md`（设计）、`../23_hybrid_query_execution_checklist.md`（落地清单）

---

## 通用迁移步骤模板

每个依赖 `yweb.orm.run_db` 的上游项目都按下面 3 步走。

### 步骤 1：扫描命中点

```bash
# 在上游项目根目录执行
rg "\brun_db\b" .
rg "from yweb\.orm import.*run_db"
rg "yweb\.orm\.run_db"
```

把命中清单记入下面「项目清单」的对应章节。

### 步骤 2：逐处判定改法

对每一处命中，按下列决策树判定：

```
调用形如 run_db(fn) 或 await run_db(fn)?
├── 纯 DB 操作，路由是 async def
│   ├── 可以改成 def 路由？        → ⭐推荐：改 def 路由，删掉 run_db 包装
│   └── 必须保持 async def？       → 改 async_db_call(fn)
│
├── 混合 async I/O + DB
│   └── 必须保持 async def         → 改 async_db_call(fn)（语义等价）
│
└── 定时任务 / 脚本里用 await run_db(...)
    └── 改 async_db_call(fn)（语义等价）
```

三种改法示例：

**A. 最佳 — 改 `def` 路由（如果不需要 async I/O）**

```python
# 改前
from yweb.orm import run_db

@app.get("/users")
async def list_users():
    return await run_db(User.get_all)

# 改后
@app.get("/users")
def list_users():
    return User.get_all()
```

**B. 保守 — 改名，保持 async def**

```python
# 改前
from yweb.orm import run_db

@app.get("/users")
async def list_users():
    return await run_db(User.get_all)

# 改后
from yweb.orm import async_db_call

@app.get("/users")
async def list_users():
    return await async_db_call(User.get_all)
```

**C. lambda 包裹复杂查询**

```python
# 改前
users = await run_db(lambda: User.query.filter_by(is_active=True).all())

# 改后
users = await async_db_call(lambda: User.query.filter_by(is_active=True).all())
```

### 步骤 3：回归测试

```bash
# 跑上游项目全量测试
pytest

# 如果 yweb 版本带 async-safety 检测（默认 error 模式），重点关注
# SynchronousOnlyOperation 是否被触发 → 说明有未改干净的 async def
export YWEB_ASYNC_SAFETY=error   # Linux/macOS
$env:YWEB_ASYNC_SAFETY="error"   # Windows PowerShell
pytest
```

验收:
- `rg "\brun_db\b" .` 在业务代码中零命中（测试桩/历史 changelog 除外）
- 全量测试通过
- 不再有 `DeprecationWarning: run_db is deprecated, use async_db_call` 噪声

---

## 项目清单

### y-sso-system

- 仓库：`E:\GPT\y-sso\y-sso-system`（根据 README_DEV.md 安装指引）
- 迁移状态：**未开始**
- 负责人：`__________________`
- 迁移日期：`__________________`
- 命中扫描结果：
  ```
  TODO: 在上游仓执行 rg "\brun_db\b" 后填入此处
  示例格式：
    app/api/user_api.py:45   await run_db(lambda: User.query.all())
    app/api/order_api.py:112 await run_db(Order.recent_orders)
  ```
- 命中处改法清单：

  | 文件:行 | 原写法 | 改法 | 备注 |
  |---|---|---|---|
  | | | | |

- 测试结果：`__________________`
- commit 链接：`__________________`

### （其他项目模板 — 复制上面的章节结构）

- 仓库：`__________________`
- 迁移状态：**未开始** / 进行中 / 完成
- 命中扫描结果：
  ```
  ```
- 改法清单：

  | 文件:行 | 原写法 | 改法 | 备注 |
  |---|---|---|---|
  | | | | |

---

## 常见坑与排查

### 1. 改完后仍然有 DeprecationWarning

- 可能是通过 `from yweb.orm import *` 间接导入，检查 `__init__.py`
- 可能是测试 fixture / mock 里残留，`rg "run_db"` 扫描也要包含 tests 目录

### 2. 改 `def` 后触发连接池耗尽

- 原先 `async def + run_db` 是通过 AnyIO 默认线程池（40 tokens）执行的
- 改成 `def` 路由后走 FastAPI/Starlette 的线程池，默认也是 40
- 两者默认一致，但如果业务自定义过 `AnyIO.to_thread.current_default_thread_limiter`，
  确认容量与 DB `pool_size + max_overflow`（yweb 默认 15）对齐

### 3. 改 `def` 后测试 fixture 报错 "cannot use sync fixture with async test"

- 说明这处 `async def test_` 其实可以改为 `def test_`
- 如果测试本身同时调用 async HTTP mock，保持 `async def test_` + `await async_db_call(...)`

### 4. 上游项目升级 yweb 时 pin 错版本

- yweb 2026-04 之前（含）：`run_db` 是原名
- yweb 2026-04 及之后：`run_db` 是 deprecated alias，`async_db_call` 是新名
- yweb **下一个发版**（待定）：`run_db` 将被移除
- 升级策略建议：
  - 小步升级：先升到带 deprecated alias 的版本，跑测试确认零回归，再做改名
  - 大步升级：改名与升级同一次完成，一次 PR 内搞定

---

## 完成状态

- [ ] `y-sso-system` 迁移完成
- [ ] 其他项目：`__________________` 迁移完成
- [ ] 所有已知上游项目 `rg "\brun_db\b"` 业务代码零命中
- [ ] yweb-core 本仓可以进入「下一版本移除 `run_db` alias」发版流程
