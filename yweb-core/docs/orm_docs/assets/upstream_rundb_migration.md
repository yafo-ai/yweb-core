# 上游项目迁移指南 · yweb-core 2026-04 升级

> 本文件原为 Phase 8.7「`run_db` → `async_db_call` 重命名」迁移指南，后续 Phase 4 / 5B / 6
> 陆续完成 HybridQuery 落地、`db_session_scope` async 兼容、文档范式升级，本文件同步
> 扩展为 **yweb-core 2026-04 完整升级指南**，覆盖上游项目从老版本升到当前版本的全部改动点。
> 文件名 `upstream_rundb_migration.md` 保留以不破坏旧 commit / 文档的外链。
>
> 上游项目升级 yweb 版本后按本指南迁移，每个上游项目一个章节，记录扫描结果与改动清单，可追溯。

## 本次升级一览

| 升级点 | 影响 | 是否必须 |
|---|---|---|
| `run_db` → `async_db_call`（重命名，保留 deprecated alias） | 仅改引用名 | 推荐（不改也能跑，有 DeprecationWarning） |
| `Model.query` 升级为 HybridQuery | async 读路径新增首选范式 `await Model.query.xxx()` | 可选（旧代码继续可用，详见下文兼容矩阵） |
| `db_session_scope()` 在 async 上下文可直接用 | 内部自动 `allow_sync` | 可选（不涉及旧代码） |
| 回滚开关 `YWEB_HYBRID_QUERY=off` | async 下退回「原地抛 `SynchronousOnlyOperation`」旧行为 | 可选（紧急回滚用） |

## 关联材料

- 关联 commit：
  - `ff97dc6 refactor(orm)! 将 run_db 重命名为 async_db_call，保留旧名为 deprecated alias`
  - Phase 4（HybridQuery 接入 `CoreModel.query`）、Phase 5B.1（scheduler async 修复）、
    Phase 5B.2（`db_session_scope` async 兼容）、Phase 6（文档范式升级）
- 关联文档：
  - [`../22_hybrid_query_sync_async_refactor.md`](../22_hybrid_query_sync_async_refactor.md)（设计文档）
  - [`../23_hybrid_query_execution_checklist.md`](../23_hybrid_query_execution_checklist.md)（落地清单 + 变更日志）
  - [`../12_db_session.md`](../12_db_session.md) / [`../15_fastapi_integration.md`](../15_fastapi_integration.md)（用户手册）

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

## 可选升级：async 读路径改用 HybridQuery 范式

> 这一节是本次升级的**新内容**，与 `run_db` 改名无关，可以独立执行，也可以合并一次 PR。

### 为什么值得改

升级到 yweb-core 2026-04 后，`Model.query` 已经是 **HybridQuery**。同步代码 0 改动；
`async def` 路由里**链式不变、终端加 `await`**，不再需要 `async_db_call(lambda: ...)` 包裹
单句查询：

```python
# 老写法（仍可用，但拐弯多）
from yweb.orm import async_db_call

@app.get("/users")
async def list_users():
    return await async_db_call(lambda: User.query.filter_by(is_active=True).all())

# 新写法（推荐）
@app.get("/users")
async def list_users():
    return await User.query.filter_by(is_active=True).all()
```

好处：
- 省掉 lambda 包裹，定义期语义清晰
- `await` 漏写时在**调用点**抛 `TypeError`（终端返回 `_HybridTerminal` 对象），定位比
  老方案（调用深处抛 `SynchronousOnlyOperation`）更直观
- 多个查询连续 `await` 时依然共享同一个 Session（中间件结束统一清理）

### 扫描命中点

```bash
# 1. 找所有 async def 路由里的 async_db_call(lambda: .query. ...) 模式
rg -U "async def \w+.*?\n(?:[^\n]*\n){0,5}?[^\n]*async_db_call\(.*?\.query\." .

# 2. 找所有 async def 里直接用 async_db_call(SomeModel.method) 的情形
rg "async_db_call\([A-Z]\w+\." .

# 3. 找所有仍在用老形式（lambda 包裹的 .query.）的地方
rg -U "await async_db_call\(\s*lambda.*\.query\." .
```

### 决策树

```
async def 路由 / 协程里有 `await async_db_call(...)` ?
│
├── 调用形如 `await async_db_call(lambda: Model.query.xxx())`
│   ├── 只有一条 DB 语句                → ⭐推荐改 `await Model.query.xxx()`
│   └── 有多条 DB 语句 / 写操作           → 保留 `async_db_call`，把 lambda 拆成命名函数
│
├── 调用形如 `await async_db_call(Model.get_all)` / `Model.some_sync_method`
│   ├── 方法内部只做只读查询             → ⭐改为 `async def` 包装 + `await Model.query...`，或者直接 `await Model.method_v2()`（如果 Model 提供 v2）
│   └── 方法内部做写 / 多语句事务         → 保留 `async_db_call`
│
└── 调用涉及 save/add/update/delete/commit
    └── 保留 `async_db_call`（写路径兜底，这是 HybridQuery 的设计边界）
```

### 改法示例

**A. 单句只读查询 — 直接改 `await Model.query.xxx()`**

```python
# 改前
users = await async_db_call(lambda: User.query.filter_by(is_active=True).all())

# 改后
users = await User.query.filter_by(is_active=True).all()
```

**B. paginate — 终端上直接加 await**

```python
# 改前
page = await async_db_call(
    lambda: User.query.order_by(User.id.desc()).paginate(page=1, page_size=20)
)

# 改后
page = await User.query.order_by(User.id.desc()).paginate(page=1, page_size=20)
```

**C. 写路径 / 多语句 — 保留 `async_db_call`（但推荐把 lambda 改为命名函数）**

```python
# 改前（仍可用，但不直观）
result = await async_db_call(lambda: (
    User(name="x").save(commit=True),
    User.query.count()
))

# 改后（推荐：命名函数，可读性更好）
def _create_and_count():
    User(name="x").save(commit=True)
    return User.query.count()

result = await async_db_call(_create_and_count)
```

**D. async_db_call(Model.classmethod) 形式**

```python
# 改前
users = await async_db_call(User.get_all)

# 改后（如果 get_all 内部只是 `return cls.query.all()`）
users = await User.query.all()
```

### 不改的情形

- 写路径（save/add/update/delete/commit、批量 update/delete、`bulk_*` 系列）→ 仍用 `async_db_call`
- 多语句事务 → 仍用 `async_db_call`，把 lambda 拆成命名函数
- `def` 路由 → 无须改（HybridQuery 在同步上下文里就是普通 Query，0 差异）

### 回归验证

```bash
# 如果把所有 async_db_call(lambda: .query.) 都改成 await Model.query.xxx()
# 漏写 await 的话，测试会在访问属性时抛 TypeError（不会静默通过）
pytest

# 如果想让测试更严格，可以临时开启回滚开关跑一遍：
$env:YWEB_HYBRID_QUERY="off"
pytest
# 回滚开关下，漏 await 会直接抛 SynchronousOnlyOperation，比 TypeError 更精确
Remove-Item Env:\YWEB_HYBRID_QUERY
```

---

## 紧急回滚预案

如果升级后线上出现与 HybridQuery 相关的异常，按以下优先级处理：

### 级别 1：环境变量回滚（秒级，推荐）

```bash
# Linux/macOS
export YWEB_HYBRID_QUERY=off

# Windows PowerShell
$env:YWEB_HYBRID_QUERY="off"

# 重启进程生效
```

作用：`CoreModel.query` 切回老的 `AsyncSafeQueryProperty`，async 下直接 `.query.xxx()`
会原地抛 `SynchronousOnlyOperation`（和升级前一样），新的 `await Model.query.xxx()`
写法会抛 `TypeError: object Query is not awaitable`。

风险矩阵：

| 升级前代码是老写法 `await async_db_call(...)` | 不受影响 ✅ |
| 升级后已改成 `await Model.query.xxx()` | 这些点会抛 `TypeError`，需要先 revert |
| 同步 `Model.query.xxx()` | 不受影响 ✅ |

### 级别 2：配合 `YWEB_ASYNC_SAFETY`

```bash
# 双开关，最保守
export YWEB_HYBRID_QUERY=off
export YWEB_ASYNC_SAFETY=warn   # 只告警不抛异常，给定位留时间
```

### 级别 3：git revert（分钟级）

如果环境变量无法缓解（例如已经全面改成新写法），按提交顺序 revert：

1. `revert` Phase 6 的文档（只是 docs，可不 revert）
2. `revert` Phase 5B 的三个 commits（scheduler + db_session_scope + test metadata 隔离）
3. `revert` Phase 4 的 HybridQuery 接入 commit —— **真正的 ORM 行为回滚点**
4. Phase 2/3 的 HybridQuery 模块本身可以不 revert（未接入 `CoreModel.query` 时它只是死代码）

涉及的 commit 范围见 23 号清单「变更日志」倒序定位。

### 什么时候该回滚

| 现象 | 级别 1 | git revert |
|---|---|---|
| 某处 async 路由漏 `await` → `_HybridTerminal` `TypeError` | ❌ 不要回滚，直接补 `await` | ❌ |
| 某处 async 路由性能回归（耗时↑） | ✅ 先开关回滚 + 排查 | 若开关无效再考虑 |
| 某处 async 路由抛未预期的 `SynchronousOnlyOperation` | ❌ 不应该发生，排查 `allow_sync` / `db_session_scope` 使用 | ❌ |
| 连接池耗尽 | ✅ 先回滚 + 加大 pool_size | 若和 HybridQuery 无关则不回滚 |
| 测试套大面积失败 | 先在本地复现，区分是**漏 await** 还是 **HybridQuery bug** | 极罕见才需要 revert |

---

## 兼容矩阵（老代码是否需要改）

| 老写法 | 升级后表现 | 建议 |
|---|---|---|
| `def` 路由 + `Model.query.all()` | 完全不变 | 不改 |
| `async def` 路由 + `await run_db(...)` | `DeprecationWarning`，功能正常 | 改成 `async_db_call` |
| `async def` 路由 + `await async_db_call(lambda: .query.)` | 完全不变 | 可选改 `await Model.query.xxx()` 提高可读性 |
| `async def` 路由 + 同步 `Model.query.all()`（老代码漏改） | 默认：返回 `_HybridTerminal` 对象，用的时候抛 `TypeError` | 必须加 `await`（或关 `YWEB_HYBRID_QUERY=off` 先定位） |
| `with db_session_scope(): ...` 在同步函数 | 完全不变 | 不改 |
| `with db_session_scope(): ...` 在 `async def` | 以前抛 `SynchronousOnlyOperation`，现在可直接用 | 如果之前为此写了绕过代码，现在可以删掉 |
| FastAPI 中间件 / `on_request_end` / `get_db` | 完全不变 | 不改 |

---

## 完成状态

- [ ] `y-sso-system` 迁移完成（`run_db` → `async_db_call` + 可选 HybridQuery 升级）
- [ ] 其他项目：`__________________` 迁移完成
- [ ] 所有已知上游项目 `rg "\brun_db\b"` 业务代码零命中
- [ ] 所有已知上游项目 async 路由已评估是否升级 HybridQuery 范式
- [ ] yweb-core 本仓可以进入「下一版本移除 `run_db` alias」发版流程
