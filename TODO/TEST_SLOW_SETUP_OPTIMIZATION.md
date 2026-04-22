# ORM 测试慢：`Base.metadata.create_all()` 重复执行问题

> 状态：待优化  
> 影响范围：`tests/test_orm/` 下所有测试文件（35 个文件，669 个测试方法）

## 问题现象

ORM 单元测试运行极慢，即使测试逻辑本身非常简单（如 `test_tree_mixin.py` 仅测试树形结构的基本 CRUD），单个文件也需要数秒。整个 `test_orm/` 跑完耗时远超预期。

## 根因分析

### 1. `memory_engine` fixture 是 function 作用域

```python
# tests/conftest.py
@pytest.fixture(scope="function")    # ← 每个测试方法都新建引擎
def memory_engine():
    engine = create_engine("sqlite:///:memory:", ...)
    yield engine
    engine.dispose()
```

### 2. 每个测试类的 `setup_db` 依赖 function 级引擎

几乎所有 ORM 测试类都使用相同的模式：

```python
class TestXxx:
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        Base.metadata.create_all(bind=memory_engine)   # ← 每个方法都建全量表
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
```

### 3. `Base.metadata` 是全局共享的

pytest 在收集阶段会导入所有测试文件，每个文件中定义的模型类都注册到同一个 `Base.metadata`。
因此，**即使 `test_tree_mixin.py` 只用了 2 张表，`create_all()` 也会创建 metadata 中的全部表。**

### 实测数据

| 指标 | 数值 |
|------|------|
| 仅 tree 测试时 metadata 中的表 | 2 张 |
| 导入部分测试后 metadata 的表 | 33 张 |
| pytest 收集全部测试后 metadata 的表 | 82~117 张 |
| `create_all()` 33 张表单次耗时 | ~20ms |
| test_orm 下测试方法总数 | 669 个 |
| **仅 `create_all` 的纯开销估算** | **~14 秒（33 表），全量表时更高** |

### 结论

> 测试逻辑本身只要几毫秒，但 **每个方法的 setup 占了 90%+ 的运行时间**。
> 核心瓶颈：`Base.metadata.create_all()` 被调用了 669 次，每次创建几十到上百张无关的表。

## 优化方案

### 方案 A：提升 fixture 作用域为 class（推荐）

将 `memory_engine` 和 `setup_db` 的 scope 提升到 class 级别，同类内的测试方法共享同一个引擎和表结构，仅数据通过 rollback 隔离：

```python
# tests/conftest.py
@pytest.fixture(scope="class")
def class_engine():
    engine = create_engine("sqlite:///:memory:", ...)
    yield engine
    engine.dispose()

@pytest.fixture(scope="class")
def class_db(class_engine):
    Base.metadata.create_all(bind=class_engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=class_engine)
    session_scope = scoped_session(SessionLocal)
    CoreModel.query = session_scope.query_property()
    yield session_scope
    session_scope.remove()
```

测试类内用 autouse fixture 做数据清理：

```python
class TestBasicTreeOperations:
    @pytest.fixture(autouse=True)
    def setup(self, class_db):
        self.session_scope = class_db
        yield
        # 回滚本次测试的数据变更，保持隔离
        self.session_scope().rollback()
        self.session_scope.remove()
```

**预期效果**：`create_all()` 从 669 次降到约 50 次（每个测试类 1 次），10x+ 提速。

### 方案 B：提升到 module 级别（更激进）

scope 直接用 `module`，同一个文件内所有测试类共享引擎。`create_all()` 降到 35 次（每个文件 1 次）。

但需要更小心地处理类间的数据隔离和 `CoreModel.query` 的恢复。

### 方案 C：指定 tables 参数（精细化）

`create_all()` 支持 `tables` 参数，只创建当前测试需要的表：

```python
Base.metadata.create_all(
    bind=memory_engine,
    tables=[TreeMenu.__table__, TreeCategory.__table__]
)
```

优点是最彻底，但需要每个测试类显式声明依赖的表，维护成本高。

### 方案 D：混合策略（推荐实施）

1. **conftest.py 提供 class 级 fixture**（方案 A）作为默认选项
2. **保留 function 级 `memory_engine`** 给确实需要完全隔离的场景（如测试引擎初始化本身）
3. **逐步迁移**：新测试使用 class 级 fixture，旧测试分批迁移

### 迁移步骤

1. 在 `tests/conftest.py` 新增 class 级 fixtures（`class_engine` + `class_db`）
2. 选一个简单文件（如 `test_tree_mixin.py`）试点改造，对比耗时
3. 确认无回归后，批量迁移其余文件
4. 旧的 function 级 `memory_engine` 保留但标注为特殊场景用

## 注意事项

- class 级 scope 下，测试方法间共享同一数据库，必须确保每个方法结束后 rollback，否则脏数据会影响后续方法
- `CoreModel.query` 赋值是全局副作用，class fixture teardown 时需恢复原值
- `init_versioning()` 在 `pytest_configure` 中全局执行一次，这部分不受影响
- 如果某些测试确实需要干净的引擎（如测试 `create_all` 本身的行为），仍可使用 function 级 fixture
