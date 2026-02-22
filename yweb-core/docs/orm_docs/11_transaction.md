# 11. 事务管理

## 概述

YWeb ORM 提供了灵活的事务管理机制，支持：

- **自动提交**：通过 `commit=True` 参数
- **手动控制**：通过 session 的 commit/rollback
- **Service 层模式**：跨多个模型的业务事务

## 基本概念

### commit 参数

所有修改方法都支持 `commit` 参数：

```python
# commit=False（默认）：只添加到会话，不提交
user.add()
user.update()
user.delete()
user.save()

# commit=True：添加到会话并立即提交
user.add(True)
user.update(True)
user.delete(True)
user.save(True)
```

### 事务边界

```python
# 事务开始：第一次数据库操作
user = User(username="tom")
user.add()  # 事务开始

# 事务中：可以有多个操作
profile = UserProfile(user_id=user.id)
profile.add()

# 事务结束：commit 或 rollback
session.commit()  # 提交事务
# 或
session.rollback()  # 回滚事务
```

## 单模型事务

### 自动提交模式

```python
# 每个操作独立提交
user = User(username="tom")
user.add(True)  # 立即提交

user.email = "tom@example.com"
user.update(True)  # 立即提交
```

### 手动提交模式

```python
from yweb.orm import db_manager

session = db_manager.get_session()

# 多个操作
user = User(username="tom")
user.add()

user.email = "tom@example.com"
user.update()

# 统一提交
session.commit()
```

### 回滚操作

```python
user = User(username="tom")
user.add()

# 发现问题，回滚
session.rollback()

# 用户不会被保存
users = User.get_all()  # 不包含 tom
```

## 多模型事务

> **推荐**：使用 `@transactional` 装饰器代替手动事务管理，参见 [Service 层最佳实践](#service-层最佳实践)。

### 基本模式（了解即可）

```python
from yweb.orm import db_manager

session = db_manager.get_session()

try:
    # 创建用户
    user = User(username="tom")
    user.add()
    session.flush()  # 获取 user.id（手动方式）

    # 创建用户档案
    profile = UserProfile(user_id=user.id, bio="Hello")
    profile.add()

    # 统一提交
    session.commit()
except Exception as e:
    session.rollback()
    raise
```

### flush vs commit

```python
# flush：将变更写入数据库，但不提交事务
# 用于获取主键 ID（所有类型）或触发约束检查
user = User(username="tom")
user.add()
session.flush()  # 或直接访问 user.id 会自动 flush
print(user.id)  # 可以获取 ID

# commit：提交事务，使变更永久生效
session.commit()
```

> **注意**：框架配置了 `autoflush=True`，在执行查询前会自动 flush。如果使用 `@transactional` + `save(commit=True)`，会自动 flush + refresh，更简洁。

## Service 层模式

### 基本结构（不推荐）

以下是传统的手动事务管理方式，**不推荐使用**，仅供了解：

```python
class UserService:
    def __init__(self, session):
        self.session = session

    def create_user_with_profile(self, user_data: dict, profile_data: dict):
        """创建用户和档案（传统方式，不推荐）"""
        try:
            user = User(**user_data)
            user.add()
            self.session.flush()  # 手动 flush

            profile = UserProfile(user_id=user.id, **profile_data)
            profile.add()

            self.session.commit()
            return user
        except Exception as e:
            self.session.rollback()
            raise
```

### 订单服务示例

```python
class InsufficientStockError(Exception):
    """库存不足异常"""
    pass

class OrderService:
    def __init__(self, session):
        self.session = session

    def create_order(self, customer_name: str, items: list[dict]):
        """创建订单（跨多模型事务）

        业务流程:
        1. 创建订单
        2. 创建订单项
        3. 扣减库存
        4. 计算总金额
        5. 一次性提交
        """
        try:
            # 1. 创建订单
            order = Order(customer_name=customer_name, status="pending")
            order.add()
            self.session.flush()

            total_amount = 0

            # 2. 处理订单项
            for item_data in items:
                product = Product.get(item_data["product_id"])
                if not product:
                    raise ValueError(f"产品不存在: {item_data['product_id']}")

                # 3. 检查并扣减库存
                quantity = item_data["quantity"]
                if product.stock < quantity:
                    raise InsufficientStockError(
                        f"产品 {product.name} 库存不足"
                    )

                product.stock -= quantity
                product.update()

                # 4. 创建订单项
                order_item = OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    quantity=quantity,
                    price=product.price
                )
                order_item.add()

                total_amount += product.price * quantity

            # 5. 更新订单总金额
            order.total_amount = total_amount
            order.status = "completed"
            order.update()

            # 6. 提交
            self.session.commit()
            return order

        except Exception as e:
            self.session.rollback()
            raise

    def cancel_order(self, order_id: int):
        """取消订单（恢复库存）"""
        try:
            order = Order.get(order_id)
            if not order:
                raise ValueError("订单不存在")

            if order.status == "cancelled":
                raise ValueError("订单已取消")

            # 恢复库存
            for item in order.items:
                product = Product.get(item.product_id)
                product.stock += item.quantity
                product.update()

            # 标记取消
            order.status = "cancelled"
            order.update()

            self.session.commit()
            return order

        except Exception as e:
            self.session.rollback()
            raise
```

### 在 FastAPI 中使用

```python
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from yweb.orm import get_db

app = FastAPI()

@app.post("/orders")
def create_order(data: dict, db: Session = Depends(get_db)):
    service = OrderService(db)
    try:
        order = service.create_order(
            customer_name=data["customer_name"],
            items=data["items"]
        )
        return OK(order)
    except InsufficientStockError as e:
        return BadRequest(str(e))
    except Exception as e:
        return ServerError(str(e))
```

## 嵌套事务

SQLAlchemy 支持 savepoint（保存点）实现嵌套事务：

```python
from sqlalchemy import savepoint

session = db_manager.get_session()

try:
    # 外层事务
    user = User(username="tom")
    user.add()

    # 创建保存点
    sp = session.begin_nested()

    try:
        # 内层操作
        profile = UserProfile(user_id=user.id)
        profile.add()
        # 可能失败的操作
        risky_operation()
        sp.commit()
    except Exception:
        sp.rollback()  # 只回滚到保存点
        # 外层事务继续

    session.commit()
except Exception:
    session.rollback()
```

## 事务隔离级别

```python
from sqlalchemy import create_engine

# 设置隔离级别
engine = create_engine(
    "postgresql://user:pass@localhost/db",
    isolation_level="REPEATABLE READ"
)

# 可选的隔离级别：
# - READ UNCOMMITTED
# - READ COMMITTED（默认）
# - REPEATABLE READ
# - SERIALIZABLE
```

## 最佳实践

### 1. 相关操作放在同一事务（单次提交模式）

> ⚠️ **重要**：特别是涉及关系操作（如多对多）时，**必须使用单次提交模式**。

```python
# ✅ 推荐：统一提交
user = User(username="tom")
user.add()

profile = UserProfile(user_id=user.id)
profile.add()

session.commit()

# ❌ 不推荐：分开提交
user = User(username="tom")
user.add(True)  # 提交

profile = UserProfile(user_id=user.id)
profile.add(True)  # 再次提交
```

**关系操作的单次提交模式**：

```python
# ✅ 正确：单次提交
role = Role(name="admin")
user = User(username="tom")
user.roles.append(role)  # 都是新对象，直接关联
session.add_all([role, user])
session.commit()

# ❌ 错误：先提交再关联
role = Role(name="admin")
role.save(commit=True)  # 先提交
user = User(username="tom")
user.roles.append(role)  # ⚠️ 可能失败！对象状态已过期
user.save(commit=True)
```

**原因**：SQLAlchemy 默认 `expire_on_commit=True`，commit 后对象状态过期，
再执行关系操作时可能被跳过。如果必须先提交，需要使用 `refresh()` 刷新对象。

### 2. 使用 try-except-rollback

```python
try:
    # 业务操作
    session.commit()
except Exception:
    session.rollback()
    raise
```

### 3. Service 层封装事务

```python
class UserService:
    def create_user(self, data):
        try:
            # 业务逻辑
            session.commit()
        except Exception:
            session.rollback()
            raise
```

### 4. 服务层事务管理（推荐 @transactional）

> ⚠️ **重要**：服务层推荐使用 `@transactional` 装饰器自动管理事务。

```python
from yweb.orm import transaction_manager as tm

class EmployeeService:
    @tm.transactional()
    def remove_from_dept(self, employee_id: int, dept_id: int):
        """使用 @transactional，自动管理事务"""
        employee = self.employee_model.get(employee_id)
        
        # 批量删除操作
        self.emp_dept_rel_model.query.filter(...).delete()
        
        if employee.primary_dept_id == dept_id:
            employee.primary_dept_id = None
        
        employee.save()  # 不需要 commit=True，事务管理器自动提交
```

**优势**：
- 自动提交/回滚
- 支持嵌套事务（Savepoint）
- 提交抑制（嵌套时内层 commit 被抑制）

**简单场景**：不使用 `@transactional` 时，通过 `model.save(commit=True)` 提交。

**内部方法**：辅助方法不应自行提交，由调用方或事务管理器统一处理。

### 4. 避免长事务

```python
# 不推荐：长事务
session.begin()
# ... 大量操作 ...
# ... 耗时操作 ...
session.commit()

# 推荐：拆分事务
# 事务1
session.commit()

# 事务2
session.commit()
```

### 5. 使用 flush 获取 ID

```python
user = User(username="tom")
user.add()
session.flush()  # 获取 ID，但不提交

# 使用 user.id 创建关联记录
profile = UserProfile(user_id=user.id)
profile.add()

session.commit()  # 统一提交
```

## 常见问题

### Q1: 什么时候用 commit=True？

- 单个独立操作
- 不需要与其他操作组成事务
- 快速测试

### Q2: 什么时候手动控制事务？

- 多个相关操作需要原子性
- Service 层业务逻辑
- 需要回滚能力

### Q3: flush 和 commit 的区别？

- `flush`：将变更写入数据库，但事务未结束
- `commit`：提交事务，变更永久生效

### Q4: 如何处理事务超时？

```python
from sqlalchemy import create_engine

engine = create_engine(
    "postgresql://...",
    pool_timeout=30,  # 连接超时
    pool_recycle=1800  # 连接回收
)
```

## 下一步

- [12_数据库会话](12_db_session.md) - 了解会话管理
- [15_FastAPI集成](15_fastapi_integration.md) - 学习 FastAPI 集成
- [16_事务管理器](16_transaction_manager.md) - 高级事务管理功能

---

## 高级事务管理（TransactionManager）

YWeb ORM 提供了高级事务管理器（TransactionManager），支持：

- **事务传播行为**：REQUIRED、REQUIRES_NEW、NESTED 等
- **事务钩子**：before_commit、after_commit、before_rollback、after_rollback
- **嵌套事务**：通过 Savepoints 实现
- **提交抑制**：在事务上下文中自动抑制 `commit=True` 的提交
- **装饰器模式**：通过 `@transactional` 装饰器简化事务管理

### 快速开始

```python
from yweb.orm import transaction_manager as tm

# 方式1：使用上下文管理器
with tm.transaction() as tx:
    user = User(username="tom")
    user.save()  # 不需要 commit=True
    
    profile = UserProfile(user_id=user.id)
    profile.save()
    # 退出上下文时自动提交

# 方式2：使用装饰器
@tm.transactional()
def create_user_with_profile(user_data, profile_data):
    user = User(**user_data)
    user.save()
    
    profile = UserProfile(user_id=user.id, **profile_data)
    profile.save()
    # 函数返回时自动提交
```

### 事务传播行为

```python
from yweb.orm.transaction import TransactionPropagation

# REQUIRED（默认）：如果存在事务则加入，否则创建新事务
@tm.transactional(propagation=TransactionPropagation.REQUIRED)
def method1():
    pass

# REQUIRES_NEW：总是创建新事务，挂起当前事务
@tm.transactional(propagation=TransactionPropagation.REQUIRES_NEW)
def method2():
    pass

# NESTED：创建嵌套事务（Savepoint）
@tm.transactional(propagation=TransactionPropagation.NESTED)
def method3():
    pass
```

### 事务钩子

```python
from yweb.orm.transaction import TransactionHook, TransactionHookType

class AuditHook(TransactionHook):
    """审计钩子：记录事务提交"""
    
    @property
    def hook_type(self):
        return TransactionHookType.AFTER_COMMIT
    
    def execute(self, context):
        print(f"事务已提交: {context.transaction_id}")

# 注册钩子
tm.register_hook(AuditHook())

# 使用钩子
with tm.transaction() as tx:
    user = User(username="tom")
    user.save()
    # 提交后会触发 AuditHook
```

### 提交抑制机制

在事务上下文中，`commit=True` 会被自动抑制，由事务管理器统一控制提交：

```python
with tm.transaction() as tx:
    user = User(username="tom")
    user.save(commit=True)  # commit=True 被抑制，不会立即提交
    
    profile = UserProfile(user_id=user.id)
    profile.save(commit=True)  # 同样被抑制
    
    # 退出上下文时统一提交
```

> **注意**：虽然 `commit=True` 被抑制，但会自动执行 `flush()` + `refresh()`，确保可以访问自动生成的字段（如 id）。

### Service 层最佳实践

```python
from yweb.orm import transaction_manager as tm

class UserService:
    @tm.transactional()
    def create_user_with_profile(self, user_data: dict, profile_data: dict):
        """创建用户和档案（事务）"""
        # 创建用户
        user = User(**user_data)
        user.save()
        
        # 访问 user.id 时自动 flush，可直接使用
        profile = UserProfile(user_id=user.id, **profile_data)
        profile.save()
        
        return user
        # 函数返回时自动提交，异常时自动回滚
    
    @tm.transactional(propagation=TransactionPropagation.REQUIRES_NEW)
    def send_notification(self, user_id: int):
        """发送通知（独立事务）"""
        # 即使外层事务回滚，通知也会发送
        notification = Notification(user_id=user_id)
        notification.save()
```

### 嵌套事务示例

```python
@tm.transactional()
def outer_transaction():
    user = User(username="tom")
    user.save()
    
    try:
        # 嵌套事务
        inner_transaction()
    except Exception:
        # 内层事务回滚，但外层事务继续
        pass
    
    # 外层事务提交

@tm.transactional(propagation=TransactionPropagation.NESTED)
def inner_transaction():
    profile = UserProfile(user_id=1)
    profile.save()
    raise Exception("内层失败")  # 只回滚内层
```

### 更多信息

详细的 TransactionManager 设计和使用说明，请参考：
- [16_事务管理器](16_transaction_manager.md) - 完整的设计文档和 API 参考
