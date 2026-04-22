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

- [x] **5B.2** `db_session_scope` 在 async 上下文下的 API gap  ✅ 2026-04-21（选定方案 A）
  - 问题：doc 22 §7.2.3 原设计的「脚本入口 `with db_session_scope(): await q.all()`」当前会在 `get_session()` 内抛 `SynchronousOnlyOperation`（`check_async_safety()` 命中）
  - Phase 5 下被测试 `test_l6d_db_session_scope_inside_async_is_currently_gap` 以 `pytest.raises` 固化
  - **选定方案 A**：`db_session_scope` 内部用 `with allow_sync():` 包裹整个 scope 生命周期
    - 决策理由：保持 22 号文档 §7.2.3 已有 API 不变；一处改动，语义简单；「显式开 scope = 显式声明『这段允许同步 DB 操作』」，符合用户心智
    - 未选 B（新增 `async_db_session_scope()`）：多一个公共 API，容易让使用者在"同步 vs 异步入口"上产生不必要的决策成本
    - 未选 C（仅 `async_db_call + on_request_end`）：与 §7.2.3 已有文档和 `with_db_session` 装饰器语义冲突
  - 修复动作：
    - `yweb/orm/db_session.py::db_session_scope` 内部用 `with allow_sync():` 包裹 `_set_request_id + get_session + yield + commit/rollback + on_request_end` 全过程
    - `async_safety.py` 模块 docstring 补一行「`async def + with db_session_scope(): → 放行（scope 内部自动 allow_sync）`」
    - `docs/orm_docs/22_hybrid_query_sync_async_refactor.md` §7.3.7 追加「Phase 5B.2 后续」说明
  - 验收：
    - [x] `test_l6d` 翻正向：`test_l6d_db_session_scope_usable_in_async`（进入 / 查询 / 退出清理）
    - [x] 新增 `test_l6e_db_session_scope_in_async_commits_on_exit`（async 下 auto_commit 真落库）
    - [x] 新增 `test_l6f_db_session_scope_in_async_rolls_back_on_exception`（async 下异常路径 rollback + 清理）
    - [x] `TestLifecycleScriptEntry` 类 6 条全绿（原 4 条 + 新增 2 条）
    - [x] 全量回归 **2698 passed / 0 failed / 0 errors**（vs Phase 5B.1 的 2696，+2 正好对应 L6e/L6f；L6d 翻正向不改数量）

- [x] **5B.3** `tests/test_scheduler/unit/` 跨模块 metadata 污染修复  ✅ 2026-04-21
  - 问题：`pytest tests/test_scheduler/ tests/test_orm/unit/` 组合下出现 **6 failed / 515 errors**（单跑 test_orm 全绿），表现为 test_orm 的 `BaseModel.metadata.create_all(memory_engine)` 抛 `sqlite3.OperationalError: index ix_scheduler_job_next_run_time already exists`
  - 定性：pre-existing 测试污染，与 Phase 5B.1 / 5B.2 改动无关（在 Phase 5 `hq_phase5_tests.txt` 已首次记录）。生产代码零影响，仅在特定测试顺序 / 子集下触发；pytest 默认字母序（`test_orm` < `test_scheduler`）下恰好不触发，所以 CI 未暴露
  - 根因：以下两处调用了**无前缀 / 自定义前缀**的 `create_scheduler_models(...)` / `setup_scheduler(...)`，会把 `scheduler_job / scheduler_job_history / scheduler_job_stats`（及 `sys_` / `x_` 等前缀的变体）**永久注册进全局 `BaseModel.metadata`**；且因 `_create_model_class` 内置 `__table_args__ = {"extend_existing": True}`，同名 Table 虽然复用但每次调用都会 append 一份 Index 定义，后续任何 `create_all(新 engine)` 都会在新 DB 上尝试创建同名 Index 多次 → 报 `already exists`：
    - `tests/test_scheduler/unit/test_models.py::TestCreateSchedulerModels`（3 条无前缀 + 1 条 `sys_` + 1 条自定义表名）
    - `tests/test_scheduler/unit/test_executor_lock_store_factory_extra_more.py::TestFactoryExtra::test_setup_scheduler`（`setup_scheduler(app=...)` 默认 `table_prefix=""`）与同类 `test_customizers_singletons_and_mount`（`x_` 前缀）
  - 修复动作（外科手术，只改测试文件，不动生产代码）：
    - 两个污染类各加一份 `@pytest.fixture(autouse=True)` 做 **metadata 快照 + teardown 移除新增表**：
      ```python
      @pytest.fixture(autouse=True)
      def _isolate_metadata(self):
          from yweb.orm import BaseModel
          pre_tables = set(BaseModel.metadata.tables.keys())
          yield
          for name in set(BaseModel.metadata.tables.keys()) - pre_tables:
              BaseModel.metadata.remove(BaseModel.metadata.tables[name])
      ```
    - 类 docstring 补写「污染说明 + 为何需要 fixture」备忘，防止后续有人删掉
  - 为何不做「scheduler/unit 层统一 autouse 保护伞」：Karpathy §3 外科手术原则 —— 只治已知污染源，不给无关测试加全局副作用；且未来新的污染点会在首次对应子集组合下显性失败，便于精准定位
  - 验收：
    - [x] `pytest tests/test_scheduler/unit/test_models.py tests/test_orm/unit/test_async_safety.py` 从 14 errors → **45 passed**
    - [x] `pytest tests/test_scheduler/unit/ tests/test_orm/unit/` 从 6 failed / 515 errors → **967 passed**
    - [x] `pytest tests/test_scheduler/ tests/test_orm/unit/` 从 6 failed / 515 errors → **1035 passed**
    - [x] 全量回归 **2698 passed / 0 failed / 0 errors**（与 Phase 5B.2 基线完全一致，零回归）

**Phase 5B 验收**：scheduler 历史记录 async 路径真正落库；`test_l6d` 已翻正向；scheduler fixture 切回 `HybridQueryProperty` 后 scheduler 测试套全绿；跨模块 metadata 污染清零。**Phase 5B 全部完成**。

---

## Phase 6 — 文档更新  ✅ 2026-04-21

> 目标：把 async 读路径的首选从 `async_db_call(lambda: ...)` 升级为「`await Model.query.xxx()`」（HybridQuery），`async_db_call` 降级为**写操作 / 多语句事务 / 混合 async I/O** 场景的兜底工具。所有改动统一用同一套措辞模板，避免后续漂移。

- [x] **6.1** `docs/03_orm_guide.md`：§10.1 Session 管理规则表改写；**新增 §10.1.1「HybridQuery：async 下的查询首选」**，含示例 + 终端列表 + 漏 `await` 的报错形态 + `YWEB_HYBRID_QUERY=off` 回滚说明
- [x] **6.2** `docs/orm_docs/12_db_session.md`：「推荐方式」小节把「方式 1 = def 路由 / 方式 2 = async_db_call」重写为「方式 1 = HybridQuery（读路径首选）/ 方式 2 = def 或 async_db_call（写路径兜底）」；场景选择指南表同步更新；Q8 FAQ 改写为「漏 await → `_HybridTerminal` → 后续 TypeError」并保留 `YWEB_HYBRID_QUERY=off` 路径
- [x] **6.3** `docs/orm_docs/15_fastapi_integration.md`：`async def vs def 路由` 表加 HybridQuery 行；新增「async 读路径首选：HybridQuery」段；旧「混合场景：async def + async_db_call()」重命名为「混合 async I/O / 写路径 / 多语句：`async_db_call()`」；底部快速参考同步更新
- [x] **6.4** `docs/orm_docs/README.md`：§「同步 / 异步查询统一」加 banner「HybridQuery 已上线」+ 跳转链接；模块树注释 `hybrid_query.py` 从「规划中」改为已交付；功能矩阵新增一行「异步查询 / HybridQuery + YWEB_HYBRID_QUERY 回滚」；修掉 22/23 号条目里 `async_db_call → async_db_call` 的拼写错误
- [x] **6.5** `.cursor/rules/yweb-orm.mdc`：第 8 条单条「async 安全」拆成 **8（async 读路径 HybridQuery）+ 9（async 写路径兜底）+ 10（回滚开关）**，含完整示例代码块
- [x] **6.6** `.cursor/skills/yweb-orm/SKILL.md`：「async 安全（必读）」表格改为 5 行（同步 / async 读 / async 写 / 启动脚本 / 漏 await），示例代码块改写成三段（def 路由 / HybridQuery / async_db_call 写路径）
- [x] **6.7** `docs/orm_docs/04_query_and_filter.md`：页尾新增「async 路由下的查询写法」小节（链式不变、终端加 await），跳转 15
- [x] **6.8** `docs/orm_docs/05_pagination.md`：页尾新增「async 路由下的分页写法」小节，点明 paginate 的 count+fetch 由 HybridQuery 合并为单次 threadpool
- [ ] **6.9**（不做）`README_DEV.md`：Phase 8.6 已完成 HybridQuery + `async_db_call` 段落，无需重复；Phase 6 不再动
- [ ] **6.10**（不做）`docs/ASYNC_SYNC_ORM_GUIDE.md`：保留为历史调研文档，不做删除 / 改写；新文档已通过 12 / 15 / 03 三处入口完整覆盖

**Phase 6 验收**：
- [x] 新老文档措辞统一（HybridQuery 读 / async_db_call 写 / def 路由最简 / `YWEB_HYBRID_QUERY=off` 回滚 4 句话）
- [x] 全量回归 **2698 passed / 0 failed / 0 errors**（与 Phase 5B.3 基线完全一致，纯 md 零回归）
- [x] 文档入口链条闭合：`README.md → orm_docs/README.md → 12 / 15 / 03` 任一起点都能找到 HybridQuery 范式

---

## Phase 7 — 发布与回滚预案（2026-04-21 部分完成）

> 本 Phase 分两部分：**文档闭环**（可在发版前独立完成）+ **实际发版动作**（版本号 / CHANGELOG / tag）。本轮完成前者；后者延到你决定具体发版节点再做。

- [ ] **7.1**（延后）版本号 bump —— 等实际发版节点由你决定
  - 当前 `pyproject.toml` version = `0.1.3`
  - 建议：本次含两项用户可感知的变更（`run_db` 重命名 + HybridQuery 范式升级），按语义化版本建议至少 minor bump（`0.2.0`）；如果上游认为"async 下漏 `await` 由 `SynchronousOnlyOperation` → `TypeError` 的行为变化"属于 breaking，走 major bump
  - 延后理由：版本号是发版动作，和文档/代码改动不同步；发版前再统一做
- [ ] **7.2**（延后）CHANGELOG 新增条目 —— 项目暂无 `CHANGELOG.md`，首建是工程约定决策，留给发版节点统一拍板
  - 已在 `docs/orm_docs/assets/upstream_rundb_migration.md` 顶部「本次升级一览」表与「兼容矩阵」节完整记录所有变更点与兼容性影响，发版时可直接搬到 `CHANGELOG.md`
- [x] **7.3** 回滚脚本 / 开关  ✅ 2026-04-21
  - 开关已在 Phase 4 实现（`HybridQueryProperty` 读 `YWEB_HYBRID_QUERY` 环境变量）
  - 文档集中到 `docs/orm_docs/assets/upstream_rundb_migration.md`「紧急回滚预案」节，分 3 级：
    - 级别 1：`YWEB_HYBRID_QUERY=off` 环境变量回退（秒级，推荐）
    - 级别 2：配合 `YWEB_ASYNC_SAFETY=warn` 告警模式，给定位留时间
    - 级别 3：git revert（分钟级；按 Phase 6 → 5B → 4 倒序）
  - 配套「什么时候该回滚」决策表覆盖 5 类典型现象
  - 决策记录：`[x] 最终方案 = A（YWEB_HYBRID_QUERY=off 环境变量回退，D3 锁定 2026-04-20）`
- [x] **7.4** 迁移指南：上游项目升级指南  ✅ 2026-04-21
  - 从「仅 `run_db` 改名」扩展为「yweb-core 2026-04 完整升级指南」，文件名保留 `upstream_rundb_migration.md`（不破坏旧 commit 引用）
  - 新增章节：
    - 「可选升级：async 读路径改用 HybridQuery 范式」—— 扫描命令 / 决策树 / 4 组改法示例（A 单句只读 / B paginate / C 多语句命名函数 / D classmethod）+ 不改的情形 + 回归验证
    - 「紧急回滚预案」—— 见 7.3
    - 「兼容矩阵」—— 7 种老写法的升级后表现与建议
  - 原 `run_db → async_db_call` 章节保留不变
  - 文件开头加「本次升级一览」表，可作为 CHANGELOG 条目的雏形

**Phase 7（文档部分）验收**：
- [x] 上游项目按指南可以一次性完成升级（扫描 → 决策 → 改法 → 验证 → 回滚路径 完整闭环）
- [x] 紧急回滚可在不读代码的前提下走完 —— 运维只看迁移指南就够
- [x] 全量回归 **2698 passed / 0 failed / 0 errors**（纯 md 零回归）

**Phase 7（发版动作）延后项**：`7.1 版本号 bump` + `7.2 CHANGELOG 首建`，在你决定发版节点时一起做。

---

## Phase 7B — 补测（Phase 5 延期项）

> 原计划 Phase 5 做的「衍生测试」在 Phase 5 收口时评估后显性延后至发版前补测，单独建 Phase 7B 便于独立跟踪。每一项都是代码 + 测试双维度，不再夹带其它文档改动。

- [ ] **7B.1** `asyncio.CancelledError` 路径下中间件 `finally` 的 session 清理覆盖
  - 场景：client 在 async 路由执行中途断开 → 中间件 finally 是否仍跑 `on_request_end()`
  - 测试：用 `httpx.AsyncClient` 模拟 `timeout` 短于服务端逻辑，验证 `_registry_has() is False`
  - 预估：新增 2 条测试，`test_hybrid_query_lifecycle.py` 追加
- [ ] **7B.2** 连接池压测
  - 条件：`concurrency = pool_size + max_overflow + 5`，`engine.pool.checkedout() == 0` 恢复
  - 测试：切 `QueuePool` + 文件 SQLite，gather 起 25 个 await 终端，全部返回后验证池清零
  - 预估：新增 1 条集成测试，`tests/test_orm/integration/test_hybrid_query_pool.py` 新建
- [x] **7B.3** Lazy 加载 trap 示例  ✅ 2026-04-22
  - 新增 `tests/test_orm/unit/test_hybrid_query_edge_cases.py` 合并实现 7B.3/7B.4/7B.5（三者共享 Author/Post + Team/Member 关系模型）
  - **7B.3 交付**：3 条测试
    - `test_lazy_load_within_live_session_works`：sync session 活着时懒加载正常（基线）
    - `test_access_relationship_after_session_closed_raises_detached`：session 关闭后访问未预载关系 → `DetachedInstanceError`（反例）
    - `test_async_route_with_joinedload_returns_relations`：async def + `joinedload` + TestClient 端到端，JSON 返回齐整（正例）
  - 文档侧：04_query_and_filter.md 的「async 路由下的查询写法」章节已有 joinedload 引导，本次未再叠加（避免重复）
- [x] **7B.4** `lazy='dynamic'` 固化  ✅ 2026-04-22
  - **3 条测试**（同一文件 `TestLazyDynamicIsAppenderNotHybrid`）：
    - `test_dynamic_relation_returns_sa_appender_query`：`team.members` 是 SA 原生 Query 子类，**不是** HybridQuery
    - `test_dynamic_relation_terminal_returns_python_native`：AppenderQuery `.all()/.count()` 直接返回 list/int（不是 `_HybridTerminal`）
    - `test_dynamic_relation_terminal_await_on_list_raises_typeerror`：对 list 做 await 必然 TypeError；用 `asyncio.run` 模拟，避开「Phase 7B 发现项 1」的生产 trap
  - 结论：HybridQuery **不**覆盖 relationship 级别的 AppenderQuery。未来若有人用 `lazy='dynamic'`，他需要走 `options(joinedload(...))` 或 `await async_db_call(lambda: team.members.filter(...).all())`
- [x] **7B.5** `DetachedInstanceError` 处理策略  ✅ 2026-04-22
  - 与 7B.3 合并实现，共 2 条对照测试（`TestLazyLoadSessionLifecycle`）：
    - 反例：`test_access_relationship_after_session_closed_raises_detached`（session 关闭 + 未预载 → 抛）
    - 正例：`test_joinedload_keeps_relationship_accessible_after_session_closed`（joinedload 预载 → 关闭后仍可访问）

**Phase 7B（3/5）交付**：`test_hybrid_query_edge_cases.py` 7 条测试全绿；全量跨模块回归 **1072 passed**（`tests/test_orm/ + tests/test_scheduler/`），无污染。

### Phase 7B 发现项 1（生产 trap，同 Phase 5B 性质） —— 主键生成器在 async 上下文死循环  ✅ 2026-04-22 已修

- **位置**：`yweb/orm/primary_key_generators.py::PrimaryKeyGenerator.generate_with_retry`
- **原代码**：
  ```python
  existing = model_class.query.filter_by(id=new_id).first()
  if existing is None:
      return new_id
  ```
- **现象**：在 `async def` 里**不套** `db_session_scope` / `async_db_call` 直接 `Model(name=...).save()`，`before_insert` 钩子调用 `.query.first()` 在 async 上下文返回 `_HybridTerminal`（不是 `None`），被判为「主键冲突」→ 死循环重试 → `RuntimeError: 生成主键失败：5次尝试后仍然冲突`
- **触发条件**：与 Phase 5B 的 scheduler 同性质 —— 生产代码在 async 上下文直接调同步 `.query.first()`，返回 `_HybridTerminal` 被误判
- **为何此前未暴露**：所有已知 async + save 场景都走 `db_session_scope`（Phase 5B.2 后内部自动 `allow_sync`）或 `async_db_call`，两条路径都绕开 async 检测。直接在 `async def` 里裸 `save()` 本就不是推荐写法，文档也劝退
- **修复**：在 `generate_with_retry` 内部用 `with allow_sync():` 包裹冲突检测查询（从 `yweb.orm.async_safety` 延迟导入）。声明这是本地幂等的主键检测，强制走 sync 路径（不论 `YWEB_HYBRID_QUERY` 开关状态都拿真值 / None）。sync 路径完全不受影响（`allow_sync` 在 sync 上下文 no-op）
- **回归测试**：`test_hybrid_query_edge_cases.py::TestPrimaryKeyInAsyncContext`
  - `test_save_in_async_def_does_not_loop_primary_key`：async def 里直接 save，验证 id 落库、`await .first()` 能查回
  - `test_consecutive_saves_in_async_def_yield_unique_ids`：连续 3 次 save 生成不同 id（若修复失效必 RuntimeError 死循环）
- **跨模块回归** `test_orm/ + test_scheduler/`：**1074 passed**（vs 基线 1072 正好 +2），零回归
- **遗留说明**：修复**不代表推荐**在 async def 里裸 save —— 它依然阻塞事件循环。文档继续引导 `def` 路由 / `async_db_call` / `db_session_scope`。修复的价值是**框架不再向用户抛一个指向错误方向的 RuntimeError**

### 其余两项（7B.1 / 7B.2）继续延后到本 phase 后续独立 commit

- [x] **7B.1** `asyncio.CancelledError` 路径下中间件 `finally` 的 session 清理覆盖  ✅ 2026-04-22
  - 新增 `TestLifecycleCancelledError::test_cancelled_error_still_triggers_on_request_end` 到 `tests/test_orm/unit/test_hybrid_query_lifecycle.py`
  - 实现方式：不走 TestClient（同步客户端对 CancelledError 的模拟依赖框架版本），而是直接构造 ASGI 调用 —— 手写 scope / receive / send + fake app，app 内用 `allow_sync()` 开主协程 scope 的 session，再 `raise asyncio.CancelledError`；middleware 的 `try/finally` 跑完后断言 `_registry_has() is False`
  - 价值：L1（正常）/ L2（普通异常）/ 7B.1（CancelledError）三条路径现在全部覆盖
  - 回归：`test_hybrid_query_lifecycle.py` 11/11 绿（vs 基线 10 正好 +1），未触及生产代码
- [ ] **7B.2** 连接池压测（待做）

**Phase 7B 是否发版前必须完成**：否。这些是**稳定性加固**而不是功能正确性；发版可以不等 7B 完成，但发版后 1 个迭代内应收口。

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
| 2026-04-21 | 执行 Phase 5B.2 — `db_session_scope` 在 async 上下文下的 API gap（用户选定方案 A）：⑴ `yweb/orm/db_session.py::db_session_scope` 内部用 `with allow_sync():` 包裹整个 scope 生命周期（`_set_request_id + get_session + yield + commit/rollback + on_request_end` 全覆盖）；⑵ `async_safety.py` 模块 docstring 补「`async def + with db_session_scope(): → 放行`」一行；⑶ `22_hybrid_query_sync_async_refactor.md` §7.3.7 追加 Phase 5B.2 后续说明；⑷ `test_l6d` 翻正向（`pytest.raises` → 正常进入/查询/清理）并新增 `test_l6e`（async auto_commit 真落库）+ `test_l6f`（async 异常路径 rollback + 清理）；⑸ 全量回归 **2698 passed / 0 failed / 0 errors**，vs Phase 5B.1 的 2696 正好 +2（L6e/L6f），L6d 翻正向不改数量 |
| 2026-04-21 | 执行 Phase 5B.3 — `tests/test_scheduler/unit/` 跨模块 metadata 污染修复：根因 = `TestCreateSchedulerModels` / `TestFactoryExtra` 调 `create_scheduler_models()` / `setup_scheduler(app=...)` 无前缀时把 `scheduler_job` 等表永久注册进 `BaseModel.metadata`，叠加 `_create_model_class` 的 `extend_existing=True` 导致 Index 累加，后续 test_orm 的 `create_all(新 engine)` 报 `index ... already exists`。修复 = 两个类各加 `@pytest.fixture(autouse=True) _isolate_metadata`（metadata 快照 + teardown 移除新增表）。从 6 failed / 515 errors → `test_scheduler/ + test_orm/unit/` 组合 **1035 passed**；全量回归 **2698 passed / 0 failed / 0 errors**，与 5B.2 基线零差异。**Phase 5B 全部完成** |
| 2026-04-21 | 执行 Phase 6 — 文档范式升级：把 async 读路径首选从「`async_db_call(lambda: ...)`」升级为「`await Model.query.xxx()`」，`async_db_call` 降级为写路径 / 多语句事务 / 混合 async I/O 兜底。改动 8 个入口：`.cursor/rules/yweb-orm.mdc`、`.cursor/skills/yweb-orm/SKILL.md`、`docs/03_orm_guide.md`（新增 §10.1.1 HybridQuery 首选小节）、`docs/orm_docs/12_db_session.md`（推荐方式 / 场景选择表 / Q8 重写）、`docs/orm_docs/15_fastapi_integration.md`（路由对比表 + 读/写场景示例）、`docs/orm_docs/04_query_and_filter.md`（页尾 async 写法）、`docs/orm_docs/05_pagination.md`（paginate 的 await 用法）、`docs/orm_docs/README.md`（banner + 功能矩阵 + 模块树注释）。所有改动用统一 4 句话模板（HybridQuery 读 / async_db_call 写 / def 路由最简 / `YWEB_HYBRID_QUERY=off` 回滚）。6.9 README_DEV.md 与 6.10 ASYNC_SYNC_ORM_GUIDE.md 评估后不做。全量回归 **2698 passed / 0 failed / 0 errors**，与 Phase 5B.3 基线完全一致（纯 md，零回归） |
| 2026-04-21 | 执行 Phase 7（文档部分）— 发布与回滚预案闭环：⑴ 把 `assets/upstream_rundb_migration.md` 从「仅 `run_db` 改名迁移」扩展为完整的「yweb-core 2026-04 升级指南」（文件名保留以不破坏旧 commit 引用），顶部加「本次升级一览」表（可作为 CHANGELOG 雏形）；⑵ 新增「可选升级：async 读路径改用 HybridQuery 范式」大章（扫描命令 / 决策树 / 4 组改法示例 / 不改的情形 / 回归验证）；⑶ 新增「紧急回滚预案」三级（环境变量 → 双开关 → git revert 倒序）+「什么时候该回滚」5 类现象决策表；⑷ 新增「兼容矩阵」7 类老写法行为对照表；⑸ 23 号清单 Phase 7.3 / 7.4 勾选，7.1（版本号 bump）与 7.2（CHANGELOG 首建）标「延后到实际发版节点」并写理由；⑹ 新建 Phase 7B 把 Phase 5 延期的补测（CancelledError / 连接池压测 / lazy trap / `lazy='dynamic'` / `DetachedInstanceError`）独立跟踪，发版前非必须完成。全量回归 **2698 passed / 0 failed / 0 errors**（纯 md，零回归） |
| 2026-04-22 | 执行 Phase 7B.3/7B.4/7B.5 — 边缘 trap 固化测试：新增 `tests/test_orm/unit/test_hybrid_query_edge_cases.py` 7 条测试（3 lazy lifecycle + 1 async joinedload e2e + 3 `lazy='dynamic'` 固化），合并做是因为三者共享 Author/Post + Team/Member 关系模型。**意外收获**：7B.4 的 async 测试暴露生产 trap「Phase 7B 发现项 1」——`primary_key_generators.py:290` 在 async 上下文直接 `.query.first()` 会返回 `_HybridTerminal` 被误判为冲突，死循环重试（性质同 Phase 5B scheduler bug）。本轮测试绕开（seed 留 sync）、生产 bug 留独立 commit 修。组合回归 `test_orm/ + test_scheduler/` **1072 passed**（vs 基线 1065 正好 +7）。7B.1（CancelledError 覆盖）/ 7B.2（连接池压测）延后至后续独立 commit |
| 2026-04-22 | 修复 Phase 7B 发现项 1 — 主键生成器在 async 上下文的死循环：`yweb/orm/primary_key_generators.py::PrimaryKeyGenerator.generate_with_retry` 的冲突检测查询外层加 `with allow_sync():`（从 `.async_safety` 延迟导入），解决「async def 里裸 `save()` → `.query.first()` 返回 `_HybridTerminal` 被判冲突 → `RuntimeError: 生成主键失败`」的误导性错误路径。新增 `TestPrimaryKeyInAsyncContext` 类 2 条回归测试追加到 `test_hybrid_query_edge_cases.py`（单次 save 落库闭环 + 3 连 save id 唯一）。组合回归 `test_orm/ + test_scheduler/` **1074 passed**（vs 上一轮 1072 正好 +2），零回归。**修复不代表推荐**此种写法 —— 它仍阻塞事件循环；修复的价值是框架不再抛一个指向错误方向的 RuntimeError |
| 2026-04-22 | 执行 Phase 7B.1 — CancelledError 路径中间件 finally 覆盖：新增 `TestLifecycleCancelledError::test_cancelled_error_still_triggers_on_request_end` 到 `tests/test_orm/unit/test_hybrid_query_lifecycle.py`。不走 TestClient（同步客户端的 CancelledError 模拟依赖框架版本），改为直接构造 ASGI 调用：手写 scope / receive / send + fake app，app 内用 `allow_sync()` 开主协程 scope 的 session，再 `raise asyncio.CancelledError`；断言 middleware finally 跑完后 `_registry_has() is False`。L1（正常）/ L2（普通异常）/ 7B.1（CancelledError）三条路径至此全覆盖。单文件回归 11/11 绿（vs 基线 10 正好 +1），未触及生产代码 |
