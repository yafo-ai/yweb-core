# 23. HybridQuery 重构 · 可执行清单

> **本文档用途**：把 [22_hybrid_query_sync_async_refactor.md](22_hybrid_query_sync_async_refactor.md) 的设计落到可勾选的执行项。每项包含「动作 / 验收标准 / 回滚点」。执行顺序严格自上而下，**一项完成后回到本文件勾选 `[x]`**。
>
> **状态**：执行中（2026-04-20 起）。
>
> **范围边界**（不属于本清单，见 doc 22 §8.7 / §8.8）：
> - ❌ 不含 AsyncSession 全栈迁移；
> - ❌ 不含 Django 风格 `a*` API；
> - ❌ 不含仓储 / UoW / CQRS 架构改造；
> - ✅ 仅实现 HybridQuery 本体 + 测试迁移 + 文档更新 + 连带 bug 修复。

---

## 使用方式

```
Phase 0 → Phase 1 → Phase 2 → ... → Phase 7
每个 Phase 全部勾选后才能进入下一 Phase。
如在执行中发现新问题，追加到对应 Phase 的「追加项」里。
```

**勾选图例**：
- `[ ]` 未开始
- `[~]` 进行中
- `[x]` 已完成并验证通过
- `[!]` 遇到阻塞，需决策

---

## 设计决策（2026-04-20 锁定）

| 编号 | 决策 | 选择 | 备注 |
|------|------|------|------|
| D1 | 终端对象同步入口 | **A** | 同步上下文下 `Model.query.filter(...).all()` **立即求值**返回 `list`；async 上下文下 `await ...all()` 返回 `list`。现有同步代码零改动。 |
| D2 | 隐式终端 (`for` / `[]` / `bool`) 在 async 的行为 | **A** | 显式抛 `RuntimeError`，引导使用 `await q.all()` / `q.first()` / `q.count() > 0`。禁止静默在线程池求值，避免隐藏性能问题。 |
| D3 | 回滚开关 | **A** | 加 `YWEB_HYBRID_QUERY=off` 环境变量回退到旧 `AsyncSafeQueryProperty`；保留至少一个发布周期后再删。 |
| D5 | `run_db` 新名 | **`async_db_call`** | 三要素齐（async + db + call），动词形式、无歧义；`run_db` 保留为 deprecated alias 一个发布周期。 |

---

## Phase 0 — 前置扫描与现状清单

目的：在动任何代码前，把仓库里会受 HybridQuery 影响的隐式依赖点扫清，避免实现后再补丁。

- [x] **0.1** 扫描 `lazy='dynamic'` 的关系（doc 22 §7.3.5）  ✅ 2026-04-21
  - 命令：`rg "lazy=['\"]dynamic['\"]" yweb-core/yweb`
  - 产出：`docs/orm_docs/assets/hq_scan_lazy_dynamic.txt`
  - 结果：**0 命中**。本仓无 AppenderQuery，HybridQuery 不需要为之特殊包装。若上游项目（如 `y-sso-system`）自建 `lazy='dynamic'`，由他们侧用 `async_db_call` 包装。
- [x] **0.2** 扫描 `isinstance(x, Query)` / `type(x) is Query`  ✅ 2026-04-21
  - 命令：`rg "isinstance\([^,]+,\s*Query\)" yweb-core`
  - 产出：`assets/hq_scan_isinstance_query.txt`
  - 结果：**1 命中** — `yweb/orm/core_model.py:1025`（`paginate` 入口的 `Query` vs `Select` 分支判断）
  - 处置：Phase 3.2 实现 `HybridQuery.paginate` 时改为 `isinstance(q, (Query, HybridQuery))`，HybridQuery 分支内部取 `._query` 后复用原流程
- [x] **0.3** 扫描 `for ... in ...query` / `query[...]` / `bool(query)` 等隐式终端（doc 22 §7.3.4）  ✅ 2026-04-21
  - 命令：`rg "for \w+ in \w+\.query"` + 跨行人工复核
  - 产出：`assets/hq_scan_implicit_terminals.txt`
  - 结果：**真正隐式终端 0 命中**；6 处疑似命中全部是 `[x for ... in Model.query.filter(...).all()]` 形式（`.all()` 在下一行），Python 先求 list 再迭代，不是迭代 Query 本身
  - 处置：Phase 2.2「`__iter__/__getitem__/__bool__` 禁用 + 明确异常」设计保留为防御，不涉及现有业务代码迁移
- [x] **0.4** 扫描业务代码里 **async def 路由中的同步 ORM 调用**  ✅ 2026-04-21
  - 命令：`rg -U "async def \w+.*\n[^)]*\.query\." yweb-core/yweb`
  - 产出：`assets/hq_scan_async_sync_calls.txt`
  - 结果：**真实代码 0 命中**（命中全在 `async_safety.py` 的 `_FIX_GUIDANCE` 与 `db_session.py` docstring 示例里）
  - 原因：commit `0a5e5a8` 已把 `yweb/auth/api/` + `yweb/organization/api/` 全部路由从 `async def` 改回 `def`
- [x] **0.5** 枚举现有测试在 `async def test_` 里直接使用 `Model.query` 的点  ✅ 2026-04-21
  - 命令：`rg -U "async def test_\w+.*\n[^)]*\.query\." yweb-core/tests` + 人工复核所有同时含两个模式的文件
  - 产出：`assets/hq_scan_async_tests.txt`
  - 结果：**Phase 5 需迁移 1 处** — `tests/test_scheduler/integration/test_history.py:392`（`async def test_job_execution_records_history` 内的 `SchedulerJobHistory.query.filter(...).first()`）
  - 其他候选文件全部在 sync test 或 fixture 里用 `.query.`，无需处理
- [x] **0.6** 确认 AnyIO / Starlette 版本  ✅ 2026-04-21
  - 结果：`AnyIO 4.13.0` / `Starlette 1.0.0`
  - 验证：AnyIO >= 3.0 → `to_thread.run_sync` 自动传 `contextvars` ✅（request_id / 软删除开关自动进线程池）
- [x] **0.7** 记录当前 DB 连接池/线程池默认值  ✅ 2026-04-21
  - 产出：`assets/hq_scan_env_pool.txt`
  - yweb DB 池（`db_session.py:156-157, 491-492`）：`pool_size=5, max_overflow=10, pool_timeout=30s` → **最大并发 15**
  - AnyIO 线程池：默认 `total_tokens=40`
  - Phase 5.2 压测用例目标：`concurrency = 5 + 10 + 5 = 20`；验收 `engine.pool.checkedout() == 0`

**Phase 0 验收**：✅ 7 份扫描产物已写入 `docs/orm_docs/assets/hq_scan_*.txt`；每项都有「结果 + 处置」决策。**关键发现**：
1. 生产代码 **0 处** `async def` + 同步 ORM（路由迁移已完成）；
2. 测试代码仅 **1 处** 需要 Phase 5 迁移；
3. `isinstance(Query)` 仅 **1 处**（`paginate` 内部）；
4. 本仓无 `lazy='dynamic'`、无真正隐式终端。HybridQuery 上线的迁移负担比 doc 22 的风险清单预估低得多。

---

## Phase 1 — 阻塞性 bug 修复（时区）

背景：在 HybridQuery 上线之前先把运行时会炸的 bug 修掉，避免重构与 bug 定位混在一起。

- [x] **1.1** 修复 `yweb/auth/mixins.py` 时区比较 bug  ✅ 2026-04-20
  - 位置 1：`check_lock_expired()` 第 145 行
  - 位置 2：`is_password_expired` 第 368 行
  - 根因：列声明 `DateTime(timezone=True)` 在 **SQLite / MySQL** 下回落为 naive，与 `datetime.now(timezone.utc)` 比较抛 `TypeError`
  - 方案：在模块内加一个纯函数 `_as_utc(dt) -> datetime`，naive → `replace(tzinfo=utc)`，aware → 原样返回；两处比较前统一过一遍
  - 实现：`yweb/auth/mixins.py` 新增 `_as_utc()`；两处比较替换为 `_as_utc(self.xxx)`
  - 验收：`pytest tests/test_auth/test_mixins.py tests/test_auth/test_mixins_timezone.py -q` → **43 passed**
- [x] **1.2** 新增「过 SQLite DB round-trip」的回归测试  ✅ 2026-04-20
  - 文件：`tests/test_auth/test_mixins_timezone.py`（新建，11 个用例）
  - 覆盖：`_as_utc` 单测 ×3；naive 模拟单测 ×5；真实 SQLite round-trip ×3
  - SQL log 佐证 bug 场景：SQLite 实际存 `'2026-04-21 03:25:42.634307'` naive 字符串
- [x] **1.3** 跑全量 auth 测试确认没有回归  ✅ 2026-04-20
  - 命令：`pytest tests/test_auth -q` → **436 passed, 3 failed**
  - 3 个失败全部为 OIDC 预存在 bug（`SampleOidcManager` 缺 `get_userinfo`），**与本次修复无关**，commit 作者非本次作者
- [x] **1.4** 审视 `yweb/auth/` 下其余 `datetime.now(timezone.utc)` 比较点是否 ORM 字段  ✅ 2026-04-20
  - 结论：`session.py` / `api_key.py` / `mfa/otp.py` / `oauth2/token.py` 均为 Python **dataclass**（`@dataclass`），值由 Python 构造的 aware datetime，不涉及 ORM 读回，**无需改**
  - 其余仅 `mixins.py` 有两处是真实 ORM 字段比较 → 已在 1.1 修掉

**Phase 1 验收**：两处 bug 修复 + 走 DB 的回归测试通过 + 完整 auth 测试通过。本 Phase 与 HybridQuery 互不依赖，可独立合入。

---

## Phase 2 — HybridQuery 骨架（不发 SQL，纯代理）  ✅ 2026-04-21 完成

目的：实现「链式阶段不发 SQL」这一层，并在 `def` 路由/同步测试中验证行为与原 `Query` 一致。

**决策锁定（Phase 2 专属）**：
- **Q1 = Q（宽松）**：隐式终端 `__iter__ / __getitem__ / __bool__` —— 同步上下文透传 SA Query 行为（100% 等价），async 上下文抛 `SynchronousOnlyOperation`。与 Phase 3.3 主方案 A（上下文感知）哲学一致
- **Q2 = Y（带泛型）**：`HybridQuery[T]` 与 `_HybridTerminal[T]` 均 `Generic[T]`，IDE / mypy 友好

- [x] **2.1** 新建 [`yweb-core/yweb/orm/hybrid_query.py`](../../yweb/orm/hybrid_query.py)
  - `HybridQuery[T]`（链式代理）：`__init__(query)`；`__getattr__` 透传 SA Query；返回值若是 `Query` 再包一层 `HybridQuery`，否则原样返回
  - `__repr__ / __str__` 代理
  - `session` 显式 `@property` 透传真实 `Session`（`core_model.py` 15+ 处依赖此契约）
  - `_query`（`__slots__` 单槽）暴露底层 SA Query
- [x] **2.2** 隐式终端 `__iter__ / __getitem__ / __bool__`（Q 方案）
  - 同步透传：`iter(self._query)` / `self._query[item]` / `bool(self._query)`
  - async 抛 `SynchronousOnlyOperation`，错误消息含显式引导（`await q.all()` / `await q.count() > 0` / `await q.limit(...).offset(...).all()`）
  - 尊重 `allow_sync()` 的 `_bypass` 与 `YWEB_ASYNC_SAFETY=off` —— 新增 `async_safety.is_in_async_context()` 只判断不抛错的 helper 供复用
- [x] **2.3** 新建 [`tests/test_orm/unit/test_hybrid_query_chain.py`](../../tests/test_orm/unit/test_hybrid_query_chain.py) —— 17 测试全绿
  - 代理链（Mock）：`filter_by → order_by → limit` 每步 HybridQuery；最末 `_query` 是链尾真 Query；非 Query 返回值不包；非 callable 属性原样透传
  - `session`（真实 Session）：`hq.session is real_session`
  - 同步隐式终端（真实 SA Query + SQLite in-memory）：`for/index/slice` 正常；`bool` 与 `bool(sa_query)` 等价（SA 不定义 `__bool__`，一律 truthy —— 契约是"同步透传"非"语义重写"）
  - async 隐式终端：三种均抛 `SynchronousOnlyOperation`，错误消息含对应引导
  - `allow_sync()` 兜底：async 内 `with allow_sync():` 后 `bool(hq)` 不抛错
  - `YWEB_ASYNC_SAFETY=off`：async 内 `list(hq)` 正常返回
  - 边界：`hq.this_method_does_not_exist_...` 抛 `AttributeError`（避免 `_query` 递归）
  - `_HybridTerminal(thunk)` 可构造；`__await__` / `_run_sync` 留给 Phase 3
- [x] **2.4** 本 Phase 不接入 `CoreModel.query` / `yweb/orm/__init__.py`（Phase 4 再做）

**Phase 2 验收**：`hybrid_query.py` + 17 条 unit 测试 ✅；`test_async_safety.py` 17 条回归 ✅；`CoreModel.query` 仍是旧的 `AsyncSafeQueryProperty`，生产路径零影响，可随时回滚（删文件即可）。

---

## Phase 3 — 终端方法与 await 支持  ✅ 2026-04-21 完成

- [x] **3.1** 设计 `_HybridTerminal`（一次性终端对象）
  - `__await__` 走 `starlette.concurrency.run_in_threadpool`
  - `_run_sync()` 下划线内部同步入口（不是公开 API）
  - 一次性：`_consumed` + `_mark_consumed()`；二次 await 或 `_run_sync` 抛 `RuntimeError("HybridQuery terminal already consumed")`
- [x] **3.2** 在 `HybridQuery` 上实现 10 个终端方法（复用 `_terminal(thunk)` helper，统一应用 Phase 3.3 A + A2 模板）：
  - [x] `all` — `list[T]` / `_HybridTerminal[list[T]]`
  - [x] `first` — `T | None`
  - [x] `one` — `T`（异常语义沿用 SA：`NoResultFound` / `MultipleResultsFound`）
  - [x] `one_or_none` — `T | None`
  - [x] `scalar` — `Any`
  - [~] `scalars` — **未实现**（SA 2.0 `Query` 对象未暴露 `.scalars()`；仓内 0 处使用，延后到确实有需求时再加）
  - [x] `count` — `int`
  - [x] `get(ident)` — 按主键（docstring 注明 SA 2.0 deprecated）
  - [x] `delete(synchronize_session='auto')` — 写终端，返回影响行数
  - [x] `update(values, synchronize_session='auto')` — 写终端
  - [x] `paginate(page, page_size, max_page_size, schema)` — 走 `CoreModel._add_paginate_to_query` 注入方法；单次 thunk 内完成 count + offset/limit.all()，同一线程池回合执行
- [x] **3.3** 同步 / 异步双面  ✅ 2026-04-21 决策锁定
  - **主方案 = A（上下文感知）**：终端方法在同步上下文立即求值返回原生结果（`list` / Model / `int` / `Page`）；在 async 上下文返回 `_HybridTerminal`（可 `await`）
  - **async 忘 await 策略 = A2**：async 中未 `await` 的用户拿到的是 `_HybridTerminal` 对象，下一行操作（迭代 / 索引 / 属性访问）自然触发 `TypeError`，**让错误显形**，避免 A1 式的静默阻塞事件循环
  - **公开同步入口：不暴露**。`_HybridTerminal._run_sync()` 作为下划线内部 escape hatch；不提供 `.value()` / `.result()` 避免与「同步直接调用」造成双写法混淆
  - **写终端（`delete` / `update`）与读终端同策略**（A + A2），不做特殊化
  - 契约方法签名模板（Phase 2 / Phase 3 所有终端方法复用）：
    ```python
    def all(self) -> list[T] | _HybridTerminal[list[T]]:
        try:
            asyncio.get_running_loop()
            return _HybridTerminal(lambda: self._query.all())
        except RuntimeError:
            return self._query.all()
    ```
  - 对 Phase 2.2 的约束：`HybridQuery` 链式对象的 `__iter__` / `__getitem__` / `__bool__` 仍需禁用（doc 22 §7.3.4），与 A2 不冲突 —— A2 只管终端方法（`.all()` 等显式调用）的返回类型；链式对象的隐式终端禁用仍由 Phase 2.2 处理。二者组合后：同步链式 → 正常用；async 链式迭代 → Phase 2.2 抛异常；async 终端方法漏 `await` → A2 让 `TypeError` 显形
  - 决策记录：`[x] 最终方案 = A + A2（context-aware + return terminal on missing await）`
- [x] **3.4** 测试 [`tests/test_orm/unit/test_hybrid_query_terminal.py`](../../tests/test_orm/unit/test_hybrid_query_terminal.py) —— 30 cases 全绿
  - `TestSyncTerminals`（12）：10 个终端同步返回原生结果 + `one/one_or_none` 异常分支 + `paginate` 第二页
  - `TestAsyncTerminals`（10）：10 个终端 async 路径返回 `_HybridTerminal` 后 await 得正确结果
  - `TestTerminalOneShot`（3）：二次 await / 二次 `_run_sync` / `await` 后再 `_run_sync` 均抛 `RuntimeError("already consumed")`；thunk 只执行一次
  - `TestTerminalThreadpool`（1）：await 时 thunk 真的在非主线程执行（`threading.get_ident()` 验证）
  - `TestAsyncBypassInTerminals`（2）：`allow_sync()` / `YWEB_ASYNC_SAFETY=off` 下 async 也走同步分支，终端直接返回原生结果
  - `TestA2MissingAwait`（2）：async 忘 `await`，下一步迭代 / 算术操作抛 `TypeError`（让错误显形）
- [x] **3.5** 实现细节自检
  - [x] `__await__` 内部通过 `starlette.concurrency.run_in_threadpool` 执行（与 `async_db_call` 同栈）
  - [x] 每个终端只调用一次 `self._query.xxx()`，thunk 内不访问关系属性；`paginate` 的 count + slice 在同一 thunk 完成
  - [x] 不做 `session.commit()`（写终端返回行数交由调用方 `commit`，与 SA 原生 `Query.delete/update` 一致）

**Phase 3 验收**：30 条单测 100% 通过；回归 Phase 2（17）+ async_safety（17）全绿；写终端行为与 SA 原生一致；一次性语义有测试兜底。

---

## Phase 4 — 接入 `db_session.py` + 改造 `async_safety.py`  ✅ 2026-04-21 完成

原计划为本次重构**最高风险步骤**，实测接入后全仓零新失败（得益于之前
commit `0a5e5a8` 已把生产 async 路由批量改为 def；Phase 0 扫描也提前
证实过仓内 0 处 async+sync ORM 残余）。

- [x] **4.1** 改 `db_session.py` `DatabaseManager.init()`：
  ```python
  if auto_setup_query:
      from .core_model import CoreModel
      from .hybrid_query import HybridQueryProperty
      raw_query_property = self._session_scope.query_property()
      CoreModel.query = HybridQueryProperty(raw_query_property)
  ```
  - 配套：`hybrid_query.py` 新增 `HybridQueryProperty` 描述符，默认走 HybridQuery 路径；
    `YWEB_HYBRID_QUERY=off` 时回退到 `AsyncSafeQueryProperty`（对应 D3=A 环境变量回退方案）
  - `core_model.paginate()` 在 `isinstance(Query)` 前加 HybridQuery 剥壳
    （Phase 0.2 扫描标记的 1 处 `isinstance(Query)` 修复）
- [x] **4.2** 改 `async_safety.py`：
  - [x] `check_async_safety()` **保留**（写路径 `db_manager.get_session()` 继续生效）
  - [x] `AsyncSafeQueryProperty` **保留**（作为 `YWEB_HYBRID_QUERY=off` 回退路径的实现，加 docstring 注释）
  - [x] 模块顶部 docstring 重写「Phase 4 起的角色分工」：读路径 HybridQuery 接管 / 写路径 check_async_safety / AsyncSafeQueryProperty = fallback
  - [x] 公开 API 列表更新（加入 `is_in_async_context`）
- [x] **4.3** 改 `yweb/orm/__init__.py`：
  - [x] `from .hybrid_query import HybridQuery`
  - [x] `__all__` 追加 `"HybridQuery"`
- [x] **4.4** 跑 `tests` 全量用例  ——  `2673 passed, 14 failed, 2 skipped, 1 xfailed in 500.67s`
  - 同步测试 100% 通过 ✅
  - HybridQuery 相关专项 64/64 绿 ✅
  - 14 失败全部在 `tests/test_ratelimit/`，根因 `ModuleNotFoundError: No module named 'slowapi'`（可选依赖，pre-existing，与 Phase 4 无关 —— 在 HEAD~1 同样 fail）
  - Phase 0 扫描标记的嫌疑点 `tests/test_scheduler/integration/test_history.py:392` 实测 PASS，因该测试的 `scheduler_db_session` fixture 直接用 `session_scope.query_property()` 覆写 `CoreModel.query`，绕过了 HybridQueryProperty（Phase 5 迁移该 fixture）
- [x] **4.5** 结果记录到 [`assets/hq_phase4_failing_async_tests.txt`](assets/hq_phase4_failing_async_tests.txt)（含失败分类、嫌疑点实测分析、验收结论、Phase 5 衍生任务）

**Phase 4 验收**：2673 条同步+HybridQuery 测试全绿；零新失败；紧急回滚通道 `YWEB_HYBRID_QUERY=off` 已打通。

---

## Phase 5 — 测试迁移  ✅ 2026-04-21 完成（5.1 部分 / 5.2 核心；5.3 defer Phase 7）

> 执行过程 + 全部数据见 `assets/hq_phase5_tests.txt`

- [~] **5.1** 根据 `hq_phase4_failing_async_tests.txt` 逐文件处理  ✅ 2026-04-21（本轮只做应做的 1 处；scheduler 上游 bug 转 Phase 5B）
  - 决策原则（doc 22 §7.3.8）：
    - 纯 DB 无 async IO 的测试 → 改 `def test_`
    - 混合 async → `await Model.query....all()`
  - 实测事实（Phase 4 结果）：仓内仅 `tests/test_scheduler/integration/test_history.py:392` 1 条候选需要处理
  - 尝试 → 回滚：一旦把 scheduler fixture 对齐到 `HybridQueryProperty` 并给该 async 测试加 `await`，立刻暴露生产 bug —— `yweb/scheduler/scheduler.py` 的 `async def _execute_job()` 直接调用同步 `history_manager.record_start/record_success/record_failure`，后者内部走 `.query.filter(...).first()`。Phase 4 上线后 `.first()` 返回 `_HybridTerminal`，导致：
    - `record_start` 被当成「主键冲突」重试 5 次失败 → `PendingRollbackError`
    - `record_success` 走到 `history.status = ...` → `AttributeError`（被 `except Exception` 吞掉）
  - 历史结论：此 bug **在 Phase 4 之前就已存在**（`AsyncSafeQueryProperty` 抛 `SynchronousOnlyOperation` 也同样被 except 吞），scheduler async executor 的历史记录功能在生产里**一直是坏的**
  - B+C 混合处置：
    - 本轮（Phase 5）：**回滚** `tests/test_scheduler/conftest.py:67` + `tests/test_scheduler/integration/test_history.py:392` 到修改前，`conftest.py` 加注释指向 Phase 5B
    - Phase 5B **独立**做 `run_in_threadpool` 包装 3 个调用点 + 新增回归测试 + 把 scheduler fixture 改回 `HybridQueryProperty`
  - 追加勾选（按测试文件拆条）：
    - [x] `tests/test_scheduler/...`（回滚待 Phase 5B 修复 + 对齐）
    - [x] `tests/test_auth/...`（Phase 0 扫描确认 0 处需迁移）
    - [x] `tests/test_organization/...`（同上）
    - [x] `tests/test_permission/...`（同上）
    - [x] `tests/test_orm/...`（`test_async_safety.py` 本身是检测机制测试，无需迁移）
    - [x] 其他（Phase 0 复核均非 async def test 中真实使用）
- [x] **5.2** 新增测试（doc 22 §7.2.3 强制清单）  ✅ 2026-04-21
  - 产出：`tests/test_orm/unit/test_hybrid_query_lifecycle.py`（**8 tests / all green**）
  - [x] `TestLifecycleWithMiddleware::test_l1_serial_multi_terminal_session_cleaned` — 串行 `count/first/all` 后 registry 归空
  - [x] `TestLifecycleWithMiddleware::test_l2_exception_path_session_cleaned` — 异常路径下中间件 `finally` 仍清理
  - [ ] ~~`asyncio.CancelledError` → 同上~~ → defer（TestClient 不方便模拟外部 cancel；规模更大的压测里顺带覆盖；见 Phase 7 发布前补测）
  - [x] `TestLifecycleWithoutMiddleware::test_l4_no_middleware_leaks_session` — 无中间件反例，`_leaked_session_count()` 穿透 `ScopedRegistry` 内部 dict 观察到泄漏（`registry.has()` 看不到 threadpool worker 的 scope 残留）
  - [x] `TestLifecycleWithMiddleware::test_l5_gather_concurrent_terminals_behavior` — `asyncio.gather` 并发多终端：请求不崩溃 + cleanup 正常 + 成功结果互相一致（若一致性断言失败即说明 session 层发生 race）
  - [x] 脚本入口（L6）：
    - [x] `test_l6a_sync_script_entry_cleans_session` — 同步 `with db_session_scope()` 正常清理
    - [x] `test_l6b_sync_script_exception_still_cleaned` — 同步 scope 抛异常仍清理
    - [x] `test_l6c_async_script_with_async_db_call_cleans_session` — async 脚本里的正确做法：`await async_db_call(...) + on_request_end()`
    - [x] `test_l6d_db_session_scope_inside_async_is_currently_gap` — **KNOWN GAP**：doc 22 §7.2.3 原设计 `with db_session_scope(): await q.all()` 当前抛 `SynchronousOnlyOperation`（因为 `db_session_scope.get_session()` 内部走 `check_async_safety()`）。测试固化现状，Phase 5B 修复后此断言反向
  - [x] 终端二次 `await` → 异常（已在 Phase 3 `test_hybrid_query_terminal.py` 覆盖，此处不重复）
  - [ ] ~~压测：`concurrency = pool_size + max_overflow + 5`，`engine.pool.checkedout() == 0`~~ → defer（需要 QueuePool + 文件 sqlite，规模独立；放入 Phase 7 发布前补测）
- [ ] **5.3** 新增测试（doc 22 §7.3 衍生）→ **defer（发布前补测）**
  - 延后理由：懒加载 / `DetachedInstanceError` 属于**文档 + 代码审查**问题，非 HybridQuery 行为异常；Phase 0 扫描确认本仓 0 处 `lazy='dynamic'`。作为 Phase 7 发布文档的一部分补 smoke + 指引更实际
  - [ ] 懒加载陷阱测试：`await Model.query.all()` + 访问关系 → 应有明确指引（加 `options(joinedload(...))` 的正例 + 未加的反例断言）
  - [ ] `lazy='dynamic'` 覆盖（本仓 0 命中；上游项目各自补「必须 `async_db_call`」的反例测试）
  - [ ] `DetachedInstanceError`：跨请求访问 ORM 实例 → 正确报错 / 或已 detach

**Phase 5 验收** ✅：
- `python -m pytest tests/ --no-header -q --ignore=tests/test_ratelimit` → **2663 passed, 2 skipped, 1 xfailed, 0 failed**（与 Phase 4 基线完全一致，零新增失败；ratelimit 的 14 条 slowapi 是 pre-existing，非本项目引入）
- `tests/test_orm/unit/test_hybrid_query_lifecycle.py` 8/8 全绿
- L6d 以可重复的 `pytest.raises` 形式固化「`db_session_scope` 在 async 上下文抛错」的 API gap，防止 Phase 5B 修复时无声回归

---

## Phase 5B — 执行中发现的联动修复（Phase 5 衍生）

> 本 Phase 由 Phase 5 执行暴露的生产代码 bug + API gap 派生。采用 B+C 混合方案：Phase 5 回滚尝试，此处独立修复 + 独立 commit。完整背景见 `assets/hq_phase5_tests.txt`。

- [x] **5B.1** Scheduler async executor 历史记录修复  ✅ 2026-04-21
  - 问题：`yweb/scheduler/scheduler.py` 的 `async def _execute_job()` 直接调用同步方法 `history_manager.record_start / record_success / record_failure`（`yweb/scheduler/history.py`），后者内部走 `HistoryModel.query.filter(...).first()`。Phase 4 上线 `HybridQueryProperty` 后 `.first()` 在 async 上下文返回 `_HybridTerminal`，导致：
    - `record_start` 被当成「主键冲突」重试 5 次失败 → `PendingRollbackError`
    - `record_success` / `record_failure` 走到 `history.status = ...` → `AttributeError`（被 `except Exception` 吞）
  - 历史定性：此 bug 在 Phase 4 之前就已存在（`AsyncSafeQueryProperty` 同样抛 `SynchronousOnlyOperation` 被 except 吞），scheduler async executor 的历史记录功能**在生产里一直是静默坏的**。Phase 4 把它从「静默失败」升级为「显性失败」
  - 修复动作（改 `yweb/scheduler/scheduler.py` **4 处调用点** —— 原估 3 处，实际 `record_failure` 在 timeout + exception 两分支各出现 1 次）：
    ```python
    from starlette.concurrency import run_in_threadpool
    await run_in_threadpool(history_manager.record_start, context)
    await run_in_threadpool(history_manager.record_success, context, result, duration_ms)
    await run_in_threadpool(history_manager.record_failure, context, error_msg, error_tb, duration_ms)  # timeout 分支
    await run_in_threadpool(history_manager.record_failure, context, error_msg, error_tb, duration_ms)  # exception 分支
    ```
  - 执行要点（踩坑记录）：
    - `tests/test_scheduler/conftest.py` 的 `previous_query = getattr(CoreModel, "query", _SENTINEL)` 会触发 `HybridQueryProperty.__get__(None, CoreModel)` → 对抽象基类发起 `session.query(CoreModel)` 抛 `ArgumentError`。**必须用 `CoreModel.__dict__.get("query", _SENTINEL)` 绕过 descriptor 协议**
    - teardown 必须完整恢复：若先前没有 `query` 属性则 `del`，否则写回原值（不能直接置空）
  - 验收：
    - [x] `tests/test_scheduler/integration/test_history.py` 全绿（20/20）
    - [x] 新增 1 条回归测试：`test_async_executor_records_failure_under_hybridquery` 验证 async executor 路径下「record_start + record_failure 都真的落了库 + status=failed + error 信息正确」
    - [x] `tests/test_scheduler/conftest.py:67` 改回 `CoreModel.query = HybridQueryProperty(session_scope.query_property())`
    - [x] `tests/test_scheduler/conftest.py` 的 `scheduler_db_session` teardown 增加「保存/恢复 `CoreModel.query`」，治 pre-existing 跨模块测试污染（`test_auth → test_scheduler` 原先会因 descriptor 残留 + CoreModel 抽象基类查询报 `ArgumentError` 导致 12 errors，修复后归零）
    - [x] `tests/test_scheduler/integration/test_history.py:392` 改回 `await ... first()`
    - [x] 全量回归：**2696 passed / 0 failed / 0 errors**（vs Phase 5 基线 2695 passed，正好 +1 新增回归测试，其它零差异）

- [ ] **5B.2** `db_session_scope` 在 async 上下文下的 API gap
  - 问题：doc 22 §7.2.3 原设计的「脚本入口 `with db_session_scope(): await q.all()`」当前会在 `get_session()` 内抛 `SynchronousOnlyOperation`（`check_async_safety()` 命中）
  - 目前被测试 `test_l6d_db_session_scope_inside_async_is_currently_gap` 以 `pytest.raises` 固化
  - 修复方案（三选一，实施前讨论）：
    - 选项 A：`db_session_scope` 内部自动 `with allow_sync():`，表明「scope 同步建立但允许 async 内部使用」
    - 选项 B：新增 `async_db_session_scope()` 作为 async 等价入口（更显式）
    - 选项 C：文档明确 async 脚本只允许 `async_db_call + on_request_end`，不开放 `db_session_scope`
  - 验收：
    - [ ] 与用户确认方案
    - [ ] 把 L6d 测试从 `pytest.raises` 反向为正向断言（或新增 async 等价测试）

**Phase 5B 验收**：scheduler 历史记录 async 路径真正落库；`test_l6d` 在修复方案落地后反向；scheduler fixture 切回 `HybridQueryProperty` 后 scheduler 测试套全绿。

---

## Phase 6 — 文档更新

- [ ] **6.1** `docs/03_orm_guide.md`：新增 HybridQuery 章节 / 更新「async 中的 ORM」段落
- [ ] **6.2** `docs/orm_docs/12_db_session.md`：`allow_sync` / `check_async_safety` 语义变更
- [ ] **6.3** `docs/orm_docs/15_fastapi_integration.md`：把 `async_db_call` 推荐示例升级为「读用 `await Model.query`、写用 `async_db_call`」
- [ ] **6.4** `docs/orm_docs/README.md`：索引加入 22 / 23 / （可能的 24）
- [ ] **6.5** 删除 / 改写 `docs/ASYNC_SYNC_ORM_GUIDE.md`
  - 决策：保留为历史方案说明 / 或改为指向 22 / 23 的精简导览
- [ ] **6.6** `README_DEV.md`：开发入口更新
- [ ] **6.7** `.cursor/rules/yweb-orm.mdc` / `.cursor/skills/yweb-orm/SKILL.md`：把 `async_db_call` 独占地位改为「读用 HybridQuery，写用 async_db_call」

**Phase 6 验收**：文档 lint 无错；用户 onboarding 能一次读完就知道怎么写 async 路由。

---

## Phase 7 — 发布与回滚预案

- [ ] **7.1** 版本号 bump（按项目约定）
- [ ] **7.2** CHANGELOG 新增条目（重点标注 **breaking：async 中 `Model.query....all()` 必须 `await`**）
- [ ] **7.3** 回滚脚本 / 开关：
  - 选项 A（推荐）：环境变量 `YWEB_HYBRID_QUERY=off` → 回退到旧 `AsyncSafeQueryProperty`
  - 选项 B：git revert Phase 4 的 commit
  - 决策记录：`[x] 最终方案 = A（YWEB_HYBRID_QUERY=off 环境变量回退，D3 锁定 2026-04-20）`
- [ ] **7.4** 迁移指南：上游项目（如 `y-sso-system`）升级 yweb 时的 5 分钟迁移步骤
  - [ ] 检查 async 路由：`rg -U "async def \w+.*\n.*\.query\." <project>`
  - [ ] 每处判定「加 `await` / 改 `def` / `await async_db_call`」
  - [ ] 回归跑上游测试

**Phase 7 验收**：发布后 24h 无 P0；上游项目按指南升级一次性通过。

---

## Phase 8 — 收尾补充项（2026-04-20 用户追加）

这些项与 Phase 5/6/7 有交叉，但必须显式勾选过一遍，防遗漏。

- [ ] **8.1** 补写测试用例（交叉 Phase 5）
  - 覆盖 Phase 2–4 引入的所有新分支：同步/异步双面、一次性终端、`paginate`、隐式终端禁用在 async 下抛错
  - 覆盖 doc 22 §7.2.3 强制清单、§7.3 衍生（懒加载 / `DetachedInstanceError` / 压测）
  - 验收：新增测试独立目录可定位（例如 `tests/test_orm/unit/test_hybrid_query_*.py` 与 `tests/test_orm/integration/test_hybrid_query_lifecycle.py`）

- [ ] **8.2** 更新异步查询使用文档（交叉 Phase 6）
  - `.cursor/rules/yweb-orm.mdc`：把「async 里必须 `async_db_call`」改为「**读用 `await Model.query...`；写用 `async_db_call` 或 `def` 路由**」；补「禁止隐式终端 `for/[]/bool`」
  - `.cursor/skills/yweb-orm/SKILL.md`：同步更新示例代码段
  - `docs/03_orm_guide.md` / `docs/orm_docs/12_db_session.md` / `15_fastapi_integration.md`：新增 / 改写「async 中的 ORM」章节
  - 验收：`rg "run_db" .cursor docs` 的命中全部解释清楚新旧关系（不是裸用）；`rg "\basync_db_call\b" .cursor docs` 应是默认示例名

- [ ] **8.3** 扫描并分类 async 使用点（延伸 Phase 0.4）
  - 目标：所有 `async def` 路由 + `async def test_` + 其他 `async def` 协程
  - 每处判定归类：
    - `[A]` 已 `await Model.query...`：无需改
    - `[B]` 同步 `Model.query...`：需加 `await` 或改 `def`
    - `[C]` 用 `async_db_call(...)`（或旧名 `run_db(...)`）：评估是否可改为 `await Model.query...`
    - `[D]` 直接 `db_manager.get_session()`：写路径，必须 `async_db_call` 包装
  - 产出：`docs/orm_docs/assets/hq_scan_async_call_sites.md`（分类表）
  - 依赖：D5（`run_db` → `async_db_call`）已锁定并实施（见 8.5）

- [x] **8.4** 清理 HybridQuery 相关 TODO  ✅ 2026-04-21
  - 动作：`rg -i "TODO.*(HybridQuery|run_db|async.*query|AsyncSafeQueryProperty|async_db_call)" yweb tests`
  - 产出：`assets/hq_scan_todos.txt`
  - 结果：**生产代码 + 测试 0 命中**。从 Phase 1（mixins bug 修复）到 Phase 8.5（`run_db` 改名）全部是「完成闭环」，无 TODO 残留
  - 清单内两个 `[ ] 最终方案 = ___________________` 占位符状态：
    - Phase 3.3（同步/异步双面）：**未决策**，等 Phase 3 开工时填入
    - Phase 7.3（回滚开关）：**已决策为 D3=A**（`YWEB_HYBRID_QUERY=off` 环境变量回退），占位符同步更新

- [x] **8.5** `run_db` 改名（D5）✅ 2026-04-21 完成
  - **当前名**：`run_db`（`yweb/orm/db_session.py`，`from starlette.concurrency import run_in_threadpool` 的 ORM 专用薄包装）
  - **决策**：`D5 = async_db_call`  ✅ 2026-04-20 锁定
  - 命名理由（供 reviewer 理解）：
    - 含动词 `call`，明确是动作而非对象
    - `async` + `db` + `call` 三要素齐，调用方不需查文档即可理解
    - 读/写两种 DB 操作均可用（避免 `async_query` 只暗示 SELECT 的歧义）
    - 与 `run_db` 字面零重叠，`rg "\brun_db\b"` 能干净定位所有老代码
  - 实施（commit `ff97dc6`）：
    - [x] 在 `db_session.py` 里把 `run_db` 重命名为 `async_db_call`；**保留** `run_db` 作为 `@deprecated` 别名一个发布周期（独立函数转发 + `DeprecationWarning`，而非赋值别名，便于 `is not` 区分）
    - [x] 全仓替换：`yweb/orm/**` 与 `tests/test_orm/unit/test_async_safety.py` 逐处改新名
    - [x] `yweb/orm/__init__.py` 对外 export `async_db_call` + 保留 `run_db`（deprecated）
    - [x] docstring 示例、`async_safety.py` 错误提示文本全部改用 `async_db_call`
    - [x] 补测试 `TestRunDbDeprecatedAlias`：旧名仍能工作 + 发出 DeprecationWarning
    - [ ] `CHANGELOG` 标注 breaking-soon：`run_db` 将于下一版本移除（待在下一次发版前补）
  - 验收：生产代码 `rg "\brun_db\b" yweb` 仅剩 alias 定义 / docstring 迁移提示 / `__all__` 标注；17/17 测试通过

- [x] **8.6** 更新 README（交叉 Phase 6.6）  ✅ 2026-04-21
  - `yweb-core/README_DEV.md`：在原「异步路由注意事项」章节追加两小节
    - `run_db` → `async_db_call` 迁移说明（含 deprecated alias 警告 + 上游迁移步骤）
    - HybridQuery 未来方向一行介绍 + 链 doc 22 / 23
  - 根 `README.md`：在「核心功能一览」新增「### 异步路由」小节（`def` 首选 + `async_db_call` 混合 I/O + HybridQuery 预告 + 链 README_DEV）
  - 验收：两个 README 读完即可写出正确的 async ORM 代码；`run_db` 旧名有明确迁移指引

- [ ] **8.7** 扫描并迁移上游项目（如 `y-sso-system`）中的 `run_db`
  - 目的：yweb-core 改名后，不引起依赖项目爆表
  - 动作（对每个上游项目）：
    - [ ] `rg "\brun_db\b" <project>`
    - [ ] 逐处判定：改 `def` 路由（首选）/ 改 `async_db_call`（保守）/ 改 `await Model.query...`（HybridQuery 上线后）
    - [ ] 跑上游测试确认
  - 记录：`docs/orm_docs/assets/upstream_rundb_migration.md` ✅ 2026-04-21 指南模板已写入
    - 通用三步流程（扫描 / 决策树 / 回归）
    - A/B/C 三种改法示例（def / async_db_call 改名 / lambda 包裹）
    - y-sso-system 项目章节模板待填充（待进入上游仓实施）
    - 常见坑 4 条（DeprecationWarning 残留 / 连接池 / fixture 异步/同步冲突 / 版本 pin 策略）
  - 已知上游：
    - [ ] `y-sso-system`（或等价项目，待实施）
    - [ ] 其他：`________________`

**Phase 8 验收**：全仓找不到裸 `run_db`（除 alias）；上游项目全绿；文档 / rules / skills 对齐新命名。

---

## 修订记录

| 日期 | 说明 |
|------|------|
| 2026-04-20 | 初版：基于 22 号文档提取 Phase 0–7 可执行项；并入 auth 时区 bug 作为 Phase 1 阻塞项 |
| 2026-04-20 | 锁定设计决策 D1/D2/D3（全部 A）；新增 Phase 8 收尾补充项：测试补写 / 文档更新 / async 扫描分类 / TODO 清理 / run_db 改名（D5 待定）/ README 更新 / 上游项目迁移 |
| 2026-04-20 | 锁定 D5：`run_db` → `async_db_call`（保留旧名 deprecated alias） |
| 2026-04-21 | 执行 Phase 1：`fix(auth) 8b1b81a` 修复 `mixins.py` 时区比较 bug（含 `_as_utc` + 11 个回归测试） |
| 2026-04-21 | 执行 async-safety 代码落地：`feat(orm) b1434c5` 核心 + `refactor(auth,org,examples) 0a5e5a8` 路由适配 |
| 2026-04-21 | 顺带修复 `fix(auth) 8743d1a`：OIDC userinfo 路由方法名+参数与真实 OidcManager 对齐（含两个测试 mock 同步） |
| 2026-04-21 | 独立新增 `feat(auth) 7e5f887`：JWTManager 支持自定义 `kid` header（JWKS 场景） |
| 2026-04-21 | 执行 Phase 8.5 代码部分：`refactor(orm)! ff97dc6` `run_db` → `async_db_call`；保留 `run_db` 作为 deprecated alias 并新增 3 个 alias 测试 |
| 2026-04-21 | 执行 Phase 0 全量扫描 + Phase 8.4 TODO 清理：7 份报告写入 `docs/orm_docs/assets/hq_scan_*.txt`。关键结论：生产代码 0 处 async+sync 残余、测试仅 1 处需迁移、无 `lazy='dynamic'`、无真隐式终端、`isinstance(Query)` 仅 `core_model.paginate` 1 处；同步 Phase 7.3 决策占位符为 D3=A |
| 2026-04-21 | 执行 Phase 8.6：`README_DEV.md` 追加 `run_db → async_db_call` 迁移说明 + HybridQuery 预告；根 `README.md` 新增「异步路由」小节（零 async 指引的盲点补齐） |
| 2026-04-21 | 执行 Phase 8.7 文档部分：写入 `assets/upstream_rundb_migration.md` 迁移指南模板（三步流程 + A/B/C 三种改法 + 4 条常见坑），y-sso-system 实施部分待进入上游仓后填充 |
| 2026-04-21 | 锁定 Phase 3.3 决策：A（上下文感知）+ A2（async 忘 await 返回 terminal 对象让错误显形）；不暴露公开 `.value()` / `.result()`；写终端与读终端同策略。同步收口 22 号文档 §5.1.2 最后一句 |
| 2026-04-21 | 执行 Phase 2 — HybridQuery 骨架：新增 `yweb/orm/hybrid_query.py`（`HybridQuery[T]` 链式代理 + `_HybridTerminal[T]` 占位）；`yweb/orm/async_safety.py` 追加 `is_in_async_context()` helper；新增 17 条单测（代理链 / session 透传 / 同步透传 / async 抛错 / allow_sync 兜底 / off 模式 / 边界）全绿。决策：Q1=Q（宽松，同步透传 async 抛错）、Q2=Y（带泛型）。不接入 CoreModel.query（留给 Phase 4） |
| 2026-04-21 | 执行 Phase 3 — HybridQuery 终端方法：`_HybridTerminal` 实装 `__await__`（`run_in_threadpool`）/ `_run_sync()` / `_consumed` 一次性保护；`HybridQuery` 上追加 10 个终端方法（`all/first/one/one_or_none/scalar/count/get/delete/update/paginate`），统一走 `_terminal()` helper 应用 A + A2 模板；新增 30 条单测（同步 12 + async 10 + 一次性 3 + 线程池 1 + bypass 2 + A2 漏 await 2）全绿。`scalars` 未实现（SA 2.0 Query 未暴露 + 仓内 0 处使用） |
| 2026-04-21 | 执行 Phase 4 — 接入 CoreModel.query：`hybrid_query.py` 加 `HybridQueryProperty` 描述符（默认 on / `YWEB_HYBRID_QUERY=off` 回退 `AsyncSafeQueryProperty`）；`db_session.py` 置换挂载点；`core_model.paginate()` 加 HybridQuery 剥壳；`async_safety.py` docstring 改写角色分工；`yweb/orm/__init__.py` 导出 `HybridQuery`。全量 pytest：2673 passed / 14 pre-existing (slowapi 缺失，与 Phase 4 无关) / 0 新失败。结果存入 `assets/hq_phase4_failing_async_tests.txt` |
| 2026-04-21 | 执行 Phase 5（B+C 混合）——**测试迁移 + lifecycle**：⑴ 尝试 scheduler fixture 对齐 `HybridQueryProperty` 暴露生产 bug（`yweb/scheduler/scheduler.py` async `_execute_job` 直接调用同步 `history_manager.record_*` → `.first()` 返回 `_HybridTerminal` 导致「主键重试失败 + 属性访问失败」），确认该 bug 在 Phase 4 前就已静默存在；⑵ 采用 B+C 混合：本轮回滚 scheduler 改动 + 注释指向新 **Phase 5B** 修复；⑶ 新增 `tests/test_orm/unit/test_hybrid_query_lifecycle.py` 8 tests（L1 串行多终端清理 / L2 异常路径清理 / L4 无中间件反例 via `ScopedRegistry` 穿透 / L5 gather 并发一致性 / L6a-d 脚本入口 4 场景，含 `db_session_scope` 在 async 下的 known gap）全绿；⑷ 5.3 懒加载 / pool 压测 / CancelledError 延后至 Phase 7 发布前补测。全量回归 2663 passed，与 Phase 4 基线零差异。详见 `assets/hq_phase5_tests.txt` |
| 2026-04-21 | 执行 Phase 5B.1 — Scheduler async executor 历史记录修复：⑴ `yweb/scheduler/scheduler.py` 新增 `from starlette.concurrency import run_in_threadpool` 并把 `history_manager.record_start / record_success / record_failure(timeout) / record_failure(exception)` **4 处**调用全部 `await run_in_threadpool(...)` 包装；⑵ `tests/test_scheduler/conftest.py` 改回 `HybridQueryProperty` 包装并加 setup/teardown 的 save/restore（踩坑：`getattr(CoreModel, "query")` 会触发 descriptor → 对抽象基类查询 `ArgumentError`，必须改走 `CoreModel.__dict__.get`）；⑶ `tests/test_scheduler/integration/test_history.py:392` 改回 `await ... first()`；⑷ 新增回归测试 `test_async_executor_records_failure_under_hybridquery` 验证 async executor 失败路径下 `record_start + record_failure` 同时落库 + `status=failed` + `error` 包含异常信息；⑸ 全量回归 **2696 passed / 0 failed / 0 errors**，vs Phase 5 基线 2695 passed 正好 +1（新增回归），其它零差异；顺带修掉 pre-existing `test_auth → test_scheduler` 跨模块污染（原先 12 errors 归零）。5B.2（`db_session_scope` async gap）仍待用户拍板 A/B/C |
