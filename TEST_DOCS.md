# yweb-core 测试指南

## 测试目录结构

```
tests/模块名
├── unit/               # 单元测试
├── integration/        # 集成测试
└── e2e/               # 端到端测试
```

## 测试命名规范

### 文件命名规范

测试文件必须遵循以下命名规则：

1. **统一前缀**：所有测试文件必须以 `test_` 开头
2. **功能模块命名**：使用下划线分隔的功能模块名称
3. **子功能命名**：使用下划线分隔的子功能或特定测试类型

#### 命名模式

```
test_[功能模块]_[子功能]_[特定测试类型].py
```

#### 具体规范示例

| 功能类型 | 命名模式 | 示例 |
|----------|----------|------|
| 基础功能 | `test_[模块].py` | `test_base_model.py` |
| 版本相关 | `test_[模块]_version.py` | `test_base_model_version.py` |
| 策略相关 | `test_[模块]_strategy.py` | `test_pk_strategy.py` |
| 冲突处理 | `test_[模块]_collision.py` | `test_short_uuid_collision.py` |
| 历史记录 | `test_[模块]_history.py` | `test_short_uuid_history.py` |
| 集成测试 | `test_[功能]_integration.py` | `test_cascade_soft_delete_integration.py` |

#### 命名优化原则

1. **清晰性**：使用完整的单词，避免过度缩写
   - ✅ `test_base_model_version.py`
   - ❌ `test_base_model_ver.py`

2. **一致性**：相同功能类型的测试使用统一的命名模式
   - ✅ 所有主键策略相关：`test_pk_strategy_*.py`
   - ✅ 所有UUID相关：`test_short_uuid_*.py`

3. **简洁性**：去除冗余词汇，保持命名简洁
   - ✅ `test_short_uuid_collision.py`
   - ❌ `test_short_uuid_collision_retry.py`

### 测试类型分类

#### 单元测试 (unit/)
- **定义**：测试单个函数、类或模块的功能
- **特点**：不依赖外部系统，执行速度快
- **示例**：`test_base_model.py`, `test_soft_delete.py`

#### 集成测试 (integration/)
- **定义**：测试多个组件之间的交互
- **特点**：可能涉及数据库、外部服务等
- **示例**：`test_cascade_soft_delete_integration.py`

#### 端到端测试 (e2e/)
- **定义**：测试完整的用户流程
- **特点**：模拟真实用户操作场景
- **示例**：预留目录，暂无具体测试

## 测试应该避免的问题

- Happy Path Testing（快乐路径测试） - 只测试正常流程，不测试边界和异常情况
- Shallow Testing（浅层测试） - 测试不够深入，只覆盖表面
- Fragile Test（脆弱测试） - 测试过于依赖实现细节，当实现改变时测试也会失败
- Implementation-Driven Testing（实现驱动测试） - 测试是基于实现写的，而不是基于需求/规格
- Self-Validating Test（自我验证测试） - 一个不太准确的术语，但有时用来描述这种问题
- Tautological Test（同义反复测试） - 测试逻辑和被测代码逻辑相同，等于在验证 "A == A"
- Puppet Test（傀儡测试） - 测试只是跟着代码走，没有独立验证

## 防止虚假测试（重点）

### 设计原则（先规格，后实现）

1. **规格驱动**：优先根据需求/契约写测试，不根据源码实现细节反推测试。
2. **独立真值**：断言应来自外部可验证事实（协议、状态码、错误码、持久化结果、业务规则），避免“被测对象自己生成输入再验证自己”。
3. **覆盖反例**：每个核心能力至少有一个失败路径（非法输入、边界值、权限不足、过期/禁用、依赖不存在等）。
4. **行为优先**：优先断言行为结果与对外语义，减少对内部结构、私有字段、调用顺序的脆弱依赖。

### 反虚假测试检查清单（PR 前必查）

- [ ] 是否存在仅覆盖 Happy Path 的测试？
- [ ] 是否存在“同源自证”（例如 `generate -> validate` 一起验证同一算法）？
- [ ] 是否验证了错误分支（状态码、错误码、错误消息）？
- [ ] 是否包含边界场景（空值、非法格式、最小/最大、过期、禁用）？
- [ ] 是否在不依赖实现细节的情况下仍能证明需求成立？
- [ ] 测试失败时，是否能清晰定位是“需求缺失 / 测试问题 / 代码缺陷”中的哪一类？

### 推荐最小场景集（以认证类模块为例）

1. 成功认证（合法凭证）
2. 缺失凭证（401/等价错误语义）
3. 非法凭证（401/等价错误语义）
4. 权限不足（403/等价错误语义）
5. 凭证失效（过期/禁用/撤销）
6. 用户或主体不存在
7. 多来源提取优先级（Header > Query > Cookie 等契约）

## 测试失败处理流程（先诊断，不急着改源码）

> 规则：**测试不通过时，先不修改源码**。先产出问题分析与备选修复方案，由用户/评审者决策后再改。

### 标准流程

1. **复现与收敛**
   - 固定失败命令、失败用例、失败环境（Python/依赖/配置）
   - 最小化复现范围（单文件、单用例、最小输入）
2. **分类判断**
   - A 类：测试用例错误（断言不符合规格、夹具污染、测试脆弱）
   - B 类：实现缺陷（行为与规格不符）
   - C 类：规格缺口（需求未明确或存在冲突）
3. **输出决策材料（必须）**
   - 具体问题：现象、影响范围、复现步骤
   - 证据：失败日志、关键断言、对照规格
   - 备选方案：至少 2 个（改测试 / 改实现 / 同步规格），并写明风险与收益
4. **等待确认**
   - 由用户明确选择方案后再执行改动
5. **执行与回归**
   - 仅实施已确认方案；完成后跑相关测试并汇总结果

### 建议输出模板

```markdown
## 测试失败诊断

- 失败用例：
- 复现命令：
- 实际结果：
- 期望结果（规格依据）：
- 影响范围：

## 可能修复方案

1. 方案 A（改测试）
   - 适用条件：
   - 风险：
2. 方案 B（改源码）
   - 适用条件：
   - 风险：
3. 方案 C（补规格/统一契约）
   - 适用条件：
   - 风险：

## 待你确认
- 请选择 A / B / C（或组合）
```

## 配套规则与技能（Cursor）

- Rule：`.cursor/rules/test-quality-and-failure-workflow.mdc`
  - 约束测试真实性，禁止虚假测试套路
  - 明确“测试失败先诊断、后改码”的决策流程
- Skill：`.cursor/skills/yweb-test-quality/SKILL.md`
  - 提供可执行的测试审查步骤、失败分类方法和输出模板

## 环境准备

### 安装依赖

```bash
# 安装开发和测试依赖
pip install -r requirements-dev.txt
```

### 依赖说明

| 依赖包 | 用途 |
|--------|------|
| `pytest` | 测试框架 |
| `pytest-cov` | 测试覆盖率报告 |
| `pytest-asyncio` | 异步测试支持 |
| `pytest-mock` | Mock 工具 |
| `httpx` | HTTP 测试客户端 |

## 运行测试

### 基础命令

```bash
# 运行所有测试
pytest

# 运行带详细输出
pytest -v

# 运行带简短错误追踪
pytest --tb=short
```

### 按模块运行

```bash
# 运行认证模块测试
pytest tests/test_auth/

# 运行 ORM 模块测试（全部）
pytest tests/test_orm/

# 运行 ORM 单元测试
pytest tests/test_orm/unit/

# 运行 ORM 集成测试
pytest tests/test_orm/integration/

# 运行配置模块测试
pytest tests/test_config/

# 运行中间件测试
pytest tests/test_middleware/
```

### 运行特定测试

```bash
# 运行单个测试文件
pytest tests/test_response/test_base_response.py

# 运行特定测试类
pytest tests/test_response/test_base_response.py::TestOKResponse

# 运行特定测试方法
pytest tests/test_response/test_base_response.py::TestOKResponse::test_ok_with_data
```

### 测试覆盖率

```bash
# 生成覆盖率报告（终端输出）
pytest --cov=yweb

# 生成 HTML 覆盖率报告
pytest --cov=yweb --cov-report=html

# 查看报告：打开 htmlcov/index.html
```

## 测试标记

项目支持以下测试标记（markers）：

| 标记 | 说明 |
|------|------|
| `@pytest.mark.slow` | 标记耗时较长的测试 |
| `@pytest.mark.integration` | 标记集成测试 |
| `@pytest.mark.unit` | 标记单元测试 |

### 按标记筛选

```bash
# 只运行单元测试
pytest -m unit

# 只运行集成测试
pytest -m integration

# 排除慢速测试
pytest -m "not slow"
```

## 常用选项

| 选项 | 说明 |
|------|------|
| `-v` | 详细输出 |
| `-s` | 显示 print 输出 |
| `-x` | 遇到第一个失败立即停止 |
| `--lf` | 只运行上次失败的测试 |
| `-k "keyword"` | 按关键字筛选测试 |

### 示例

```bash
# 运行包含 "jwt" 关键字的测试
pytest -k "jwt"

# 失败时立即停止，显示详细输出
pytest -v -x

# 只重新运行上次失败的测试
pytest --lf
```

## 目录结构

```
yweb-core/
├── tests/
│   ├── __init__.py
│   ├── conftest.py                    # 公共 fixtures 和测试配置
│   │
│   ├── test_auth/                     # 认证模块测试
│   │   ├── test_jwt.py                # JWT 令牌功能测试
│   │   └── test_dependencies.py       # 认证依赖注入测试
│   │
│   ├── test_config/                   # 配置模块测试
│   │   ├── test_settings.py           # 配置类测试
│   │   └── test_loader.py             # YAML 配置加载器测试
│   │
│   ├── test_log/                      # 日志模块测试
│   │   ├── test_filter_hooks.py       # 日志过滤钩子测试
│   │   └── test_handlers.py           # 日志处理器测试
│   │
│   ├── test_middleware/               # 中间件测试
│   │   ├── test_request_id.py         # Request ID 中间件测试
│   │   ├── test_request_logging.py    # 请求日志中间件测试
│   │   └── test_performance.py        # 性能监控中间件测试
│   │
│   ├── test_orm/                      # ORM 模块测试
│   │   ├── unit/                      # 单元测试
│   │   │   ├── test_base_model.py     # ORM 基类测试
│   │   │   ├── test_base_model_version.py # 版本功能测试
│   │   │   ├── test_soft_delete.py    # 软删除功能测试
│   │   │   ├── test_cascade_soft_delete.py # 级联软删除测试
│   │   │   ├── test_transaction.py    # 基础事务测试
│   │   │   ├── test_transaction_manager.py # 事务管理器测试
│   │   │   ├── test_pk_strategy.py    # 主键策略测试
│   │   │   ├── test_pk_strategy_priority.py # 主键策略优先级测试
│   │   │   ├── test_pk_strategy_history.py # 主键策略历史测试
│   │   │   ├── test_pk_collision_retry.py # 主键冲突重试测试
│   │   │   ├── test_short_uuid_collision.py # 短UUID冲突测试
│   │   │   ├── test_short_uuid_history.py # 短UUID历史测试
│   │   │   └── test_auto_history.py   # 自动历史记录测试
│   │   ├── integration/               # 集成测试
│   │   │   └── test_cascade_soft_delete_integration.py # 级联软删除集成测试
│   │   └── e2e/                       # 端到端测试（预留）
│   │
│   ├── test_response/                 # 响应模块测试
│   │   └── test_base_response.py      # 统一响应封装测试
│   │
│   └── test_utils/                    # 工具模块测试
│       ├── test_encryption.py         # 加密工具测试
│       └── test_file_size.py          # 文件大小工具测试
│
├── pytest.ini                         # pytest 配置文件
└── requirements-dev.txt               # 开发和测试依赖
```