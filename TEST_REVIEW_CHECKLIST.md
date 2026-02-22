# 测试文件审查清单（分阶段）

> 目标：按文件逐个审查测试质量，重点识别虚假测试（Happy Path / Shallow / Implementation-Driven / Tautological / Puppet 等）。

## 使用说明

1. 每审查完一个文件，新增一行记录。
2. 若测试失败，先在“结论摘要”写明问题分类（测试问题/实现问题/规格问题）。
3. 修改源码前，先在“下一步”写出备选方案，等待确认后执行。

## 进度总览

- 当前阶段：`test_utils` + `test_validators` 模块（已完成）
- 已完成：`75`
- 计划总数：`75`
- 当前完成到：`第 75 个文件`


## 下一批候选（待排期）

- `yweb-core/tests/test_orm/` 与 `yweb-core/tests/test_storage/` 下测试文件（按文件名顺序）

## 文件审查记录（按模块）

### 模块：`test_auth`

| 序号 | 文件 | 状态 | 结论摘要 | 下一步 |
|---|---|---|---|---|
| 1 | `yweb-core/tests/test_auth/test_api_key.py` | 已完成 | 已重构为规格驱动测试，补齐异常/边界路径，避免同源自证；当前文件测试通过。 | 后续可扩展并发/极端输入场景 |
| 2 | `yweb-core/tests/test_auth/test_audit.py` | 已完成（已重构） | 已改为行为级测试：覆盖记录行为、状态语义、查询条件、分页排序、清理策略；避免 `hasattr` 式浅层断言。测试已通过（11/11）。 | 后续可引入真实数据库集成测试，验证 ORM 查询在真实环境的一致性 |
| 3 | `yweb-core/tests/test_auth/test_base.py` | 已完成（增强） | 基础行为覆盖较好，本次补充失败语义和边界分支：默认错误码、无默认提供者、未知 provider、全 provider 校验失败、默认提供者回退。测试已通过（25/25）。 | 后续可补充 token_extractor 的自动认证路径测试 |
| 4 | `yweb-core/tests/test_auth/test_dependencies.py` | 已完成（增强） | 补充了认证失败语义断言（401 detail）、可选认证无效 token 分支、RoleChecker 的 401/403/成功分支，降低浅层测试风险。测试已通过（21/21）。 | 后续可增加 `get_token_data` 与 HTTPBearer 路径的端到端验证 |
| 5 | `yweb-core/tests/test_auth/test_jwt.py` | 已完成（增强） | 补充了构造参数校验、refresh 相关失败/成功分支、兼容 API 行为、无效 token 剩余时长分支，减少仅 happy path 的风险。测试已通过（31/31）。 | 后续可补充 `raise_on_expired=True` 的异常码语义验证 |
| 6 | `yweb-core/tests/test_auth/test_mfa.py` | 已完成（增强） | 补充 TOTP 未配置/长度错误分支、短信发送频率限制、MFAManager 的 unknown provider / verify_any / primary provider 等关键行为分支。测试已通过（32/32）。 | 后续可补充跨 provider 的真实集成场景（如 TOTP + Recovery 回退链路） |
| 7 | `yweb-core/tests/test_auth/test_mixins.py` | 已完成（增强） | 强化了 commit 行为、副作用更新调用、失败计数临界锁定等场景，降低仅属性断言的浅层风险。测试已通过（32/32）。 | 后续可补充 `needs_password_rehash/rehash_password_if_needed` 的行为链路验证 |
| 8 | `yweb-core/tests/test_auth/test_oauth2.py` | 已完成（增强） | 补充 OAuth2 客户端默认 scope/通配 URI、manager 的 not found/invalid grant/内省、provider 的 unsupported grant/无效凭证格式/无效 token 分支。测试已通过（25/25）。 | 后续可补充 device code 授权与轮询全流程测试 |
| 9 | `yweb-core/tests/test_auth/test_password.py` | 已完成（增强） | 补充了未知哈希格式、MD5 盐值不匹配、长度边界联合配置等分支，增强对密码升级与验证失败语义的覆盖。测试已通过（29/29）。 | 后续可补充并发/高负载下哈希与验证稳定性基准测试 |
| 10 | `yweb-core/tests/test_auth/test_session.py` | 已完成（增强） | 补充了过期 Session 清理、MFA 标记失败分支、Provider 凭证错误分支、无效 Session 验证、登出清理 Cookie 语义。测试已通过（24/24）。 | 后续可补充 `require_mfa=True` 依赖链路与会话自动续期阈值测试 |
| 11 | `yweb-core/tests/test_auth/test_token_store.py` | 已完成（增强） | 补充了删除不存在记录、无 JWTManager 撤销、无效 token 非黑名单路径、全局实例重配置覆盖等边界分支。测试已通过（23/23）。 | 后续可补充 RedisTokenStore 的集成测试（序列化、TTL、并发一致性） |
| 12 | `yweb-core/tests/test_auth/test_token_refresh.py` | 已完成（增强） | 补充了滑动续期触发分支（refresh_token_renewed=True）、缺失 user_id 刷新失败等关键边界，提升 refresh 语义覆盖。测试已通过（21/21）。 | 后续可补充 `raise_on_expired=True` 在 refresh 场景下的异常路径验证 |
| 13 | `yweb-core/tests/test_auth/test_ldap_extra.py` | 已完成（增强） | 补充了 LDAP 异常分支、组名解析的非 CN 路径、角色映射去重分支，增强 LDAP provider 边界覆盖。测试已通过（14/14）。 | 后续可增加真实 ldap3 集成测试（连接、TLS、属性映射一致性） |
| 14 | `yweb-core/tests/test_auth/test_models_extra.py` | 已完成（增强） | 补充了 RoleMixin 在 roles 缺失/None 时的容错行为，避免空值场景下回归。测试已通过（4/4）。 | 后续可增加基于真实 ORM 模型的 search_with_roles 关联加载测试 |
| 15 | `yweb-core/tests/test_auth/test_service_setup_extra.py` | 已完成（增强） | 补充了 BaseAuthService 的异常防护分支、user_getter 活跃状态可配置分支、AuthSetup.create_auth_service 成功路径。测试已通过（9/9）。 | 后续可补充 setup_auth(app=...) 的端到端路由挂载联调测试 |
| 16 | `yweb-core/tests/test_auth/test_rate_limiter_validators_extra.py` | 已完成（增强） | 补充了未封锁 IP 剩余秒数分支、空用户名校验异常分支，增强 rate limiter 与 validator 的边界覆盖。测试已通过（10/10）。 | 后续可补充并发场景下 LoginRateLimiter 的线程安全验证 |
| 17 | `yweb-core/tests/test_auth/test_dependencies_audit_api_key_extra.py` | 已完成（增强） | 补充了 API Key scope 装饰器在缺少 api_key_data 时透传分支、Header/Query/Cookie 优先级分支，增强依赖与 API Key 边界覆盖。测试已通过（10/10）。 | 后续可补充真实 FastAPI app 下的依赖注入联调测试 |
| 18 | `yweb-core/tests/test_auth/test_mfa_extra_more.py` | 已完成（增强） | 补充了 MFAManager.is_enabled 分支与 OTP 错误码 remaining_attempts 分支，强化 MFA 失败路径可观察性。测试已通过（6/6）。 | 后续可补充 TOTP 时间窗口漂移与多时区边界测试 |
| 19 | `yweb-core/tests/test_auth/test_auth_api_routes_extra.py` | 已完成（增强） | 补充了 `/auth/refresh` 无效 token 失败分支、`/oauth2/token` refresh invalid_grant=401 分支、OIDC 未配置 oauth2_manager 的 500 分支。测试已通过（19/19）。 | 后续可补充 OAuth2/OIDC 真实签名 token 的跨端点联调验证 |
| 20 | `yweb-core/tests/test_auth/test_auth_api_routes_extra_edgecases.py` | 已完成（增强） | 补充了自定义 `login_response_builder` 分支、OAuth2 `unsupported_response_type` 重定向分支，完善路由配置与协议错误处理覆盖。测试已通过（10/10）。 | 后续可补充 response_type/state 组合在不同客户端配置下的一致性验证 |
| 21 | `yweb-core/tests/test_auth/test_oauth2_provider_oidc_extra.py` | 已完成（增强） | 补充了 device_code 成功与通用错误映射分支、OIDC 默认 JWKS（无公钥）分支，增强 provider 与 OIDC 管理器边界覆盖。测试已通过（10/10）。 | 后续可补充 RS256 签名下公私钥轮换与 kid 匹配测试 |
| 22 | `yweb-core/tests/test_auth/test_oauth2_api_routes_extra_more.py` | 已完成（增强） | 补充了 client_credentials 无效客户端 401 分支及授权服务器元数据端点断言，强化 OAuth2 路由协议语义覆盖。测试已通过（12/12）。 | 后续可补充 HTTP Basic 与表单凭证冲突时的优先级一致性测试 |
| 23 | `yweb-core/tests/test_auth/test_auth_user_oidc_api_routes_extra_more.py` | 已完成（增强） | 补充了登录成功重置限流器分支、OIDC POST `/userinfo` 分支、用户创建重复值分支，完善 auth/user/oidc 路由边界覆盖。测试已通过（15/15）。 | 后续可补充 login 与 user 管理接口的跨路由会话一致性测试 |

### 模块：`test_cache`

| 序号 | 文件 | 状态 | 结论摘要 | 下一步 |
|---|---|---|---|---|
| 24 | `yweb-core/tests/test_cache/test_decorators.py` | 已完成（增强） | 修复“同义反复/快乐测试”风险：为 dict/list 场景补充 `call_count` 断言，验证缓存命中而非仅结果相等；测试通过（15/15）。 | 后续可补充时间冻结方案替代 `sleep`，降低时序波动 |
| 25 | `yweb-core/tests/test_cache/test_decorators_extra.py` | 已完成（增强） | 补充 Redis 缓存命中行为断言（`call_count`），避免只看返回值的浅层测试；测试通过（4/4）。 | 后续可补充 Redis 序列化失败/反序列化异常路径 |
| 26 | `yweb-core/tests/test_cache/test_cache_api.py` | 已完成（增强） | 补强 `/clear` 相关测试：从“仅断言响应字段”升级为“校验清空后是否重新计算”，避免 API Happy Path 假阳性；测试通过（26/26）。 | 后续可补充异常分支的错误码语义断言（message/detail） |
| 27 | `yweb-core/tests/test_cache/test_invalidation.py` | 已完成（增强） | 补充自定义 `key_extractor` 与多函数注册的真实失效行为断言，避免仅验证注册数量的实现驱动测试；测试通过（14/14）。 | 后续可补充未知事件名与空 registrations 的鲁棒性测试 |
| 28 | `yweb-core/tests/test_cache/test_setup_listeners_bug.py` | 已完成（复审） | 已按“虚假测试”标准复核：核心用例通过真实 SQLAlchemy 事件触发与缓存失效行为校验，不是纯快乐测试；复跑通过（9/9）。 | 后续可在不依赖私有属性前提下再补一层黑盒 API 行为回归 |
| 29 | `yweb-core/tests/test_cache/test_clear_listened_models_bug.py` | 已完成（复审） | 已按“虚假测试”标准复核：覆盖 clear 后重注册、多轮 clear、新事件增量与 no-op 安全性，行为链路充分；复跑通过（9/9）。 | 后续可补充高频 clear/re-register 压力场景 |

### 模块：`test_exceptions`

| 序号 | 文件 | 状态 | 结论摘要 | 下一步 |
|---|---|---|---|---|
| 30 | `yweb-core/tests/test_exceptions/test_exceptions.py` | 已完成（增强+实现修复） | 补充了可变对象隔离断言，识别到 `BusinessException.to_dict()` 暴露内部引用（实现问题 B）；按方案 A 修复为深拷贝后通过（26/26）。 | 后续可补充嵌套 `extra` 对象的深层不可变性回归测试 |
| 31 | `yweb-core/tests/test_exceptions/test_handlers.py` | 已完成（增强） | 补强系统异常响应语义测试（非 raise 模式）与多异常类型的错误码精确映射，减少仅状态码断言的浅层风险；测试通过（20/20）。 | 后续可补充 DEBUG 开关在同一进程下切换时的并发一致性测试 |
| 32 | `yweb-core/tests/test_exceptions/test_handlers_extra.py` | 已完成（复审） | 已覆盖 debug/non-debug、HTTP 4xx/5xx、validation fallback 等关键分支，断言具有行为独立性；复跑通过（5/5）。 | 后续可补充 request_id 缺失时日志字段兜底断言 |
| 33 | `yweb-core/tests/test_exceptions/test_integration.py` | 已完成（增强） | 为创建失败/删除操作补充状态不变量断言（DB 记录数与删除结果），避免只看响应体的 Happy Path；测试通过（14/14）。 | 后续可补充并发创建同名用户时冲突语义测试 |
| 34 | `yweb-core/tests/test_exceptions/test_exception_conversion.py` | 已完成（复审） | 异常转换链路测试覆盖数据库/HTTP 异常与异常链保留，具备可观察行为断言，不属于同义反复；复跑通过（9/9）。 | 后续可补充请求上下文（trace_id）透传到异常 extra 的验证 |

### 模块：`test_config`

| 序号 | 文件 | 状态 | 结论摘要 | 下一步 |
|---|---|---|---|---|
| 35 | `yweb-core/tests/test_config/test_settings.py` | 已完成（增强） | 在默认值断言外补充了计算字段解析、非法配置错误分支、可变默认值隔离等行为断言，降低浅层测试风险；测试通过（18/18）。 | 后续可补充环境变量覆盖嵌套配置的端到端测试 |
| 36 | `yweb-core/tests/test_config/test_loader.py` | 已完成（增强） | 补充缓存与 reload 语义、深层 merge 保持、路径穿透默认值场景；并修复测试隔离问题（清理全局缓存）避免同名文件污染；测试通过（23/23）。 | 后续可补充并发加载同一配置文件的线程安全测试 |

### 模块：`test_log`

| 序号 | 文件 | 状态 | 结论摘要 | 下一步 |
|---|---|---|---|---|
| 37 | `yweb-core/tests/test_log/test_logger.py` | 已完成（复审） | 以命名契约、层级关系、传播行为为主，已有独立可观察断言，未发现明显快乐测试问题。 | 后续可补充并发 get_logger 的一致性测试 |
| 38 | `yweb-core/tests/test_log/test_logger_extra.py` | 已完成（复审） | 覆盖配置提取、root/sql logger 装配与分支行为，断言针对行为结果，质量可接受。 | 后续可补充 logger 复用下 handler 去重断言 |
| 39 | `yweb-core/tests/test_log/test_handlers.py` | 已完成（增强） | 修复“仅 assert not None”浅层用例，补充处理器关键属性与文件名模板替换断言；已验证通过（24/24）。 | 后续可补充异常流（I/O 失败）下的容错分支测试 |
| 40 | `yweb-core/tests/test_log/test_buffered_handler.py` | 已完成（复审） | 覆盖容量刷新、错误级别立即落盘、并发写入、关闭刷盘等关键行为，非快乐路径占比较高。 | 后续可补充极端高并发下顺序一致性测试 |
| 41 | `yweb-core/tests/test_log/test_log_cleanup.py` | 已完成（复审） | 已覆盖按天数/总大小/组合策略清理和工具方法，具备状态结果断言，质量可接受。 | 后续可补充跨时区日期边界清理测试 |
| 42 | `yweb-core/tests/test_log/test_filter_hooks.py` | 已完成（增强） | 补充输入不应被原地改写、副作用验证及重复注册单次注销语义，减少同义反复与浅层断言风险；已验证通过（34/34）。 | 后续可补充 hook 异常传播策略测试 |
| 43 | `yweb-core/tests/test_log/test_handlers_extra_more.py` | 已完成（复审） | 覆盖 flush 异常分支、close join 分支等补充路径，回归价值明确。 | 后续可补充弱引用对象回收后的清理验证 |

### 模块：`test_middleware`

| 序号 | 文件 | 状态 | 结论摘要 | 下一步 |
|---|---|---|---|---|
| 44 | `yweb-core/tests/test_middleware/test_request_logging.py` | 已完成（增强） | 将多条“仅有标题无断言”的用例补强为行为断言：方法/路径/状态码、异常日志、skip 路径标记、大请求体预览化、敏感字段过滤；已验证通过（12/12）。 | 后续可补充多 content-type 下日志预览一致性测试 |
| 45 | `yweb-core/tests/test_middleware/test_request_logging_extra.py` | 已完成（复审） | 已覆盖配置解析、用户信息超时/异常回退、过滤器失败容错、异常路径 request_id 回退等关键分支，质量可接受。 | 后续可补充 log_filters 链式短路策略测试 |
| 46 | `yweb-core/tests/test_middleware/test_request_body_handling.py` | 已完成（复审） | 端到端覆盖 POST/PUT/PATCH/并发/大体积/Unicode/校验错误等场景，核心契约明确，不属于快乐路径。 | 后续可补充 multipart/form-data 场景 |
| 47 | `yweb-core/tests/test_middleware/test_request_id.py` | 已完成（增强） | 修复 `try/except pass` 虚假测试：改为在应用启动/首请求阶段显式断言不支持参数时抛错，避免“无论实现如何都通过”；已验证通过（8/8）。 | 后续可补充异常请求链路下 request_id 清理验证 |
| 48 | `yweb-core/tests/test_middleware/test_current_user.py` | 已完成（复审） | 覆盖 token 提取、路径匹配、异常容错、并发隔离及 Simple 中间件行为，断言以外部可观察行为为主。 | 后续可补充异步端点下 ContextVar 隔离压测 |
| 49 | `yweb-core/tests/test_middleware/test_current_user_integration.py` | 已完成（复审） | 多用户审计链路端到端验证充分，包含未认证拒绝与用户切换场景，非浅层测试。 | 后续可补充事务回滚下历史记录一致性验证 |
| 50 | `yweb-core/tests/test_middleware/test_ip_access.py` | 已完成（复审） | 覆盖中间件/依赖/装饰器三层能力，包含白黑名单、路径匹配、优先级与 from_settings；行为断言完整。 | 后续可补充 trusted_proxies 真实代理链场景 |
| 51 | `yweb-core/tests/test_middleware/test_performance.py` | 已完成（复审） | 现有测试覆盖基础性能头与中间件协作，虽部分阈值断言偏保守但不构成虚假测试。 | 后续可补充稳定的 mock 时钟以降低 sleep 抖动 |

### 模块：`test_response`

| 序号 | 文件 | 状态 | 结论摘要 | 下一步 |
|---|---|---|---|---|
| 52 | `yweb-core/tests/test_response/test_base_response.py` | 已完成（增强） | 在原有默认值断言基础上补充了顶层/嵌套 `None` 序列化语义、DTO 递归序列化、别名函数与类方法一致性及统一响应契约（`msg_details`）断言，降低浅层测试风险；已验证通过（46/46）。 | 后续可补充 `Resp` 快捷类与 OpenAPI response_model 的一致性测试 |

### 模块：`test_scheduler`

| 序号 | 文件 | 状态 | 结论摘要 | 下一步 |
|---|---|---|---|---|
| 53 | `yweb-core/tests/test_scheduler/integration/test_api.py` | 已完成（增强） | 修复 `/jobs/run` 的不确定断言（`200/500` 均通过 + 条件跳过），改为通过 mock `run_job` 验证稳定响应语义（状态、消息、`run_id`、`job_code`）与调用参数，避免快乐路径假阳性；已验证通过（19/19）。 | 继续排查其余 API 用例中对内部状态的过度耦合断言 |
| 54 | `yweb-core/tests/test_scheduler/integration/test_integration.py` | 已完成（增强） | 将生命周期测试从“仅验证注册”升级为“验证 startup/shutdown 实际执行”，通过 `TestClient` 驱动应用生命周期并断言 `start/shutdown` 调用行为，减少浅层测试风险；已验证通过（17/17）。 | 继续复审重试场景，补充重试事件与次数的确定性断言 |
| 55 | `yweb-core/tests/test_scheduler/integration/test_integration.py` | 已完成（二次增强） | 将 `test_job_with_retry` 从 `attempt_count >= 1` 的弱断言升级为重试契约断言（执行 2 次、重试事件字段、错误事件语义），避免“发生过就算通过”的浅层测试；复跑通过（17/17）。 | 下一步进入 `unit/test_scheduler.py`，优先清理仅注册数量断言的实现驱动用例 |
| 56 | `yweb-core/tests/test_scheduler/unit/test_triggers.py` | 已完成（增强） | 将多处 `trigger is not None` 升级为触发语义断言：基于固定时间校验 `get_next_fire_time()` 的时分秒与工作日行为，避免“对象创建即通过”的浅层测试；已验证通过（21/21）。 | 继续处理 `unit/test_scheduler.py` 的监听器注册类弱断言（仅计数） |
| 57 | `yweb-core/tests/test_scheduler/unit/test_scheduler.py` | 已完成（增强） | 将事件监听器测试从“仅检查注册数量”改为“真实事件分发行为断言”，验证同步/异步监听器被触发且多监听器调用顺序可观察，降低实现驱动与傀儡测试风险；已验证通过（37/37）。 | 继续排查 `integration/test_history.py` 中 `is not None` / `>=1` 的浅层断言 |
| 58 | `yweb-core/tests/test_scheduler/integration/test_history.py` | 已完成（增强） | 修复两类弱断言：1）`cleanup_old_history` 从 `count >= 1` 升级为 `count == 1` 且验证新记录状态；2）`test_job_execution_records_history` 去掉条件分支 `if history`，改为强制断言落库成功并校验 `job_code/status`，避免 Puppet/Happy Path 假通过；已验证通过（19/19）。 | 下一步进入 `integration/test_api.py` / `unit/test_builder.py`，清理剩余 `is not None` 占位断言 |
| 59 | `yweb-core/tests/test_scheduler/unit/test_async_executor.py` | 已完成（复审） | 复核并发上限、异常清理、无 `job_id` 计数行为等关键分支，断言具备可观察行为；回归通过。 | 后续可补充同步函数 `kwargs` 支持的规格澄清用例 |
| 60 | `yweb-core/tests/test_scheduler/unit/test_builder.py` | 已完成（增强） | 将 `trigger is not None` 升级为 `get_triggers()` 行为断言，减少对象存在性浅层断言；回归通过。 | 后续可补充多触发器优先级与冲突配置用例 |
| 61 | `yweb-core/tests/test_scheduler/unit/test_context.py` | 已完成（复审） | 上下文字段、序列化/反序列化与状态语义断言完整，未见明显实现驱动风险；回归通过。 | 后续可补充跨时区与毫秒精度边界 |
| 62 | `yweb-core/tests/test_scheduler/unit/test_distributed.py` | 已完成（复审） | 分布式锁获取/释放与异常容错路径具备行为断言，不属于 Happy Path 伪覆盖；回归通过。 | 后续可补充高并发抢锁稳定性测试 |
| 63 | `yweb-core/tests/test_scheduler/unit/test_events.py` | 已完成（复审） | 事件模型构造与字段语义断言清晰，覆盖成功/失败/重试等核心事件；回归通过。 | 后续可补充事件兼容性回归（字段新增默认值） |
| 64 | `yweb-core/tests/test_scheduler/unit/test_http_job.py` | 已完成（复审） | HTTP Job 正常/异常/重试分支覆盖较均衡，断言以外部结果为主；回归通过。 | 后续可补充网络超时抖动与响应体异常格式场景 |
| 65 | `yweb-core/tests/test_scheduler/unit/test_job_class.py` | 已完成（复审） | 类任务声明式配置与回调链路覆盖完整，异常路径可观察；回归通过。 | 后续可补充 `on_error` 异常再抛的语义测试 |
| 66 | `yweb-core/tests/test_scheduler/unit/test_models.py` | 已完成（复审） | Job/History/Stats 模型核心字段与状态迁移断言完整，测试质量可接受；回归通过。 | 后续可补充 ORM 真实会话下索引/约束一致性测试 |
| 67 | `yweb-core/tests/test_scheduler/unit/test_retry.py` | 已完成（复审） | 重试策略（固定/指数/条件）关键路径覆盖良好，断言不依赖内部实现细节；回归通过。 | 后续可补充极端退避参数边界测试 |
| 68 | `yweb-core/tests/test_scheduler/unit/test_settings.py` | 已完成（复审） | 配置默认值、环境变量覆盖与功能开关断言完整，未见虚假测试模式；回归通过。 | 后续可补充非法配置值错误语义断言 |
| 69 | `yweb-core/tests/test_scheduler/unit/test_scheduler_edge_paths.py` | 已完成（增强） | 修复生命周期测试伪前提（startup 后再断言 shutdown 未调用）导致的稳定失败；改为验证启用场景 `shutdown(wait=True)` 被调用，并补强 `run_id` 与 `get_job` 类型断言；回归通过。 | `test_scheduler/unit` 审查收尾完成，进入下一模块排期 |

### 模块：`test_utils`

| 序号 | 文件 | 状态 | 结论摘要 | 下一步 |
|---|---|---|---|---|
| 70 | `yweb-core/tests/test_utils/test_encryption.py` | 已完成（增强） | 修复与实现不一致的假设（误按 bcrypt 语义）、清理 `try/except pass` 伪通过断言；补充默认盐值稳定哈希、自定义盐值影响、`verify_password(..., salt=...)` 一致性验证；回归通过。 | 后续可补充 `hash_password_md5` 与 `verify_encrypted_password` 的跨版本兼容场景 |
| 71 | `yweb-core/tests/test_utils/test_file_size.py` | 已完成（增强） | 清理“允许抛错或通过都算对”的弱断言，改为基于源码语义的确定性断言（负值解析、PB 格式化、decimal-base 分支）；回归通过。 | 后续可补充 `binary=False` 下 MB/GB 的更多精度边界 |
| 72 | `yweb-core/tests/test_utils/test_file_size_extra_more.py` | 已完成（复审） | 已覆盖别名单位、异常分支、负值格式化与超大值分支，断言具备行为确定性；回归通过。 | 后续可补充极端浮点输入（如 `nan/inf`）策略测试 |
| 73 | `yweb-core/tests/test_utils/test_ip.py` | 已完成（增强） | 补充“无效 IP + `*` 通配符”分支及“空 XFF 回退 X-Real-IP”分支，完善代理头优先级边界语义；回归通过。 | 后续可补充 `decode(errors=\"replace\")` 非 UTF-8 头值分支 |
| 74 | `yweb-core/tests/test_utils/test_test_collector_extra_more.py` | 已完成（复审） | 覆盖 run/check/summary/reset 与状态枚举分支，已具备较好行为断言深度；回归通过。 | 后续可补充 verbose=False 时输出抑制的精细断言 |

### 模块：`test_validators`

| 序号 | 文件 | 状态 | 结论摘要 | 下一步 |
|---|---|---|---|---|
| 75 | `yweb-core/tests/test_validators/test_constraints_extra_more.py` | 已完成（增强） | 依据源码补充 US/JP/HK/TW 手机号地区分支、身份证小写 `x` 归一化、约束构造器元数据断言、optional 空白输入边界；回归通过。 | 后续可补充 `Range(ge/le)` 与 `Range(gt/lt)` 组合冲突场景 |
