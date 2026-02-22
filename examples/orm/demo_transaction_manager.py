"""事务管理器示例

本脚本演示了 yweb.orm 的事务管理功能，包括基础事务、嵌套事务、钩子系统和传播行为。

================================================================================
                          事务管理功能概述
================================================================================

主要功能：
- 基础事务管理（提交、回滚、状态转换）
- 嵌套事务（Savepoint）支持
- 事务钩子系统（before_commit, after_commit, after_rollback, on_error）
- 事务传播行为（REQUIRED, REQUIRES_NEW, NESTED, MANDATORY, NEVER）
- 提交抑制机制（事务上下文中自动忽略 commit=True，但会 flush + refresh）
- 自动刷新机制（autoflush=True，查询前自动 flush pending 对象）
- 装饰器支持（@transactional）
- 重试机制（@transaction_with_retry）

核心 API：
┌─────────────────────────────────────────────────────────────────────────────┐
│ transaction_manager.transaction()     - 创建事务上下文                       │
│ @transaction_manager.transactional()  - 事务装饰器                          │
│ @transaction_with_retry()             - 带重试的事务装饰器                   │
│ get_current_transaction()             - 获取当前事务                        │
│ tx.savepoint()                        - 创建保存点（嵌套事务）               │
│ @tx.before_commit                     - 注册提交前钩子                      │
│ @tx.after_commit                      - 注册提交后钩子                      │
│ @tx.after_rollback                    - 注册回滚后钩子                      │
│ @tx.on_error                          - 注册错误处理钩子                    │
└─────────────────────────────────────────────────────────────────────────────┘

使用步骤：
1. 导入 transaction_manager
2. 使用 with transaction_manager.transaction() 创建事务
3. 在事务中执行数据库操作
4. 可选：注册钩子、创建保存点、设置传播行为

获取主键 ID（所有主键策略）：
┌─────────────────────────────────────────────────────────────────────────────┐
│ model.save() 后直接访问 model.id 即可！                                      │
│ 框架会在访问 id 时自动检测并 flush，无需手动处理。                            │
│ 注：所有主键（自增、UUID、雪花算法等）都在 flush 时生成。                     │
└─────────────────────────────────────────────────────────────────────────────┘

运行方式：
    python demo_transaction_manager.py
"""

import os
import sys
from sqlalchemy import String, Integer
from sqlalchemy.orm import Mapped, mapped_column


# ==================== 1. 导入依赖 ====================

from yweb.orm import (
    CoreModel,
    BaseModel,
    init_database,
    transaction_manager as tm,
    get_current_transaction,
    transaction_with_retry,
    TransactionPropagation,
    TransactionState,
)


# ==================== 2. 定义测试模型 ====================

class UserModel(BaseModel):
    """用户模型 - 用于演示事务管理"""
    __tablename__ = "demo_tx_users"
    __table_args__ = {'extend_existing': True}

    email: Mapped[str] = mapped_column(String(100), nullable=True)
    balance: Mapped[int] = mapped_column(Integer, default=0)


class OrderModel(BaseModel):
    """订单模型 - 用于演示事务管理"""
    __tablename__ = "demo_tx_orders"
    __table_args__ = {'extend_existing': True}

    user_id: Mapped[int] = mapped_column(Integer, nullable=True)
    amount: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")


class LogModel(BaseModel):
    """日志模型 - 用于演示事务管理"""
    __tablename__ = "demo_tx_logs"
    __table_args__ = {'extend_existing': True}

    action: Mapped[str] = mapped_column(String(100), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, nullable=True)
    details: Mapped[str] = mapped_column(String(500), nullable=True)


# ==================== 辅助函数 ====================

def print_section(title):
    """打印章节标题"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def print_success(message):
    """打印成功消息"""
    print(f"[OK] {message}")


def print_error(message):
    """打印错误消息"""
    print(f"[ERROR] {message}")


def print_info(message):
    """打印信息"""
    print(f"[INFO] {message}")


def print_warning(message):
    """打印警告消息"""
    print(f"[WARN] {message}")


# ==================== 测试场景 ====================

def test_scenario_1_basic_transaction():
    """场景1：基础事务 - 正常提交"""
    print_section("场景1：基础事务 - 正常提交")

    print_info("创建事务并添加用户...")
    with tm.transaction() as tx:
        print_info(f"事务状态: {tx.state.name}")
        print_info(f"是否在事务中: {tm.is_in_transaction()}")

        user = UserModel(
            name="张三",
            code="USER_001",
            email="zhangsan@example.com",
            balance=1000
        )
        user.save()
        user_id = user.id  # 访问 id 时自动 flush

        print_success(f"用户已添加: ID={user_id}, 姓名={user.name}, 余额={user.balance}")

    # 事务结束后验证
    print_info(f"事务结束后状态: {tx.state.name}")
    print_info(f"是否在事务中: {tm.is_in_transaction()}")

    # 验证数据已提交
    found = UserModel.get(user_id)
    if found:
        print_success(f"数据已成功提交到数据库: {found.name}")
    else:
        print_error("数据未找到，提交失败！")

    return user_id


def test_scenario_2_transaction_rollback():
    """场景2：事务回滚 - 异常时自动回滚"""
    print_section("场景2：事务回滚 - 异常时自动回滚")

    user_id = None
    try:
        with tm.transaction() as tx:
            user = UserModel(
                name="李四",
                code="USER_002",
                email="lisi@example.com",
                balance=2000
            )
            user.save()
            user_id = user.id  # 访问 id 时自动 flush

            print_info(f"用户已添加: ID={user_id}, 姓名={user.name}")

            # 模拟业务异常
            print_warning("模拟业务异常，触发回滚...")
            raise ValueError("余额不足，无法完成操作")

    except ValueError as e:
        print_info(f"捕获异常: {e}")
        print_info(f"事务状态: {tx.state.name}")

    # 验证数据已回滚
    if user_id:
        found = UserModel.get(user_id)
        if found is None:
            print_success("数据已成功回滚，用户未创建")
        else:
            print_error("回滚失败，数据仍然存在！")


def test_scenario_3_manual_rollback():
    """场景3：手动回滚"""
    print_section("场景3：手动回滚")

    with tm.transaction(auto_commit=False) as tx:
        user = UserModel(
            name="王五",
            code="USER_003",
            email="wangwu@example.com",
            balance=3000
        )
        user.save()
        user_id = user.id  # 访问 id 时自动 flush

        print_info(f"用户已添加: ID={user_id}, 姓名={user.name}")

        # 手动回滚
        print_info("执行手动回滚...")
        tx.rollback()
        print_info(f"事务状态: {tx.state.name}")

    # 验证数据已回滚
    found = UserModel.get(user_id)
    if found is None:
        print_success("手动回滚成功，用户未创建")
    else:
        print_error("手动回滚失败！")


def test_scenario_4_nested_transaction():
    """场景4：嵌套事务（Savepoint）"""
    print_section("场景4：嵌套事务（Savepoint）")

    print_info("创建外层事务...")
    with tm.transaction() as tx:
        # 创建用户
        user = UserModel(
            name="赵六",
            code="USER_004",
            email="zhaoliu@example.com",
            balance=5000
        )
        user.save()
        user_id = user.id  # 访问 id 时自动 flush
        print_success(f"外层事务：用户已创建 ID={user_id}")

        # 创建保存点
        print_info("创建保存点，尝试创建订单...")
        try:
            with tx.savepoint("order_creation") as sp:
                order = OrderModel(
                    name="订单001",
                    code="ORDER_001",
                    user_id=user_id,
                    amount=1000,
                    status="pending"
                )
                order.save()
                print_info(f"保存点内：订单已创建 ID={order.id}")  # 访问 id 时自动 flush

                # 模拟订单创建失败
                print_warning("模拟订单创建失败...")
                raise ValueError("库存不足")

        except ValueError as e:
            print_info(f"保存点回滚: {e}")

        # 外层事务继续
        print_info("外层事务继续执行...")

    # 验证结果
    found_user = UserModel.get(user_id)
    found_orders = OrderModel.query.filter_by(user_id=user_id).all()

    if found_user and len(found_orders) == 0:
        print_success("嵌套事务正确：用户已创建，订单已回滚")
    else:
        print_error("嵌套事务失败！")


def test_scenario_5_transaction_hooks():
    """场景5：事务钩子"""
    print_section("场景5：事务钩子")

    hook_logs = []

    with tm.transaction() as tx:
        # 注册 before_commit 钩子
        @tx.before_commit
        def validate_before_commit(ctx):
            hook_logs.append("before_commit: 验证数据完整性")
            print_info("钩子执行: before_commit - 验证数据完整性")

        # 注册 after_commit 钩子
        @tx.after_commit
        def send_notification(ctx):
            hook_logs.append("after_commit: 发送通知邮件")
            print_info("钩子执行: after_commit - 发送通知邮件")

        # 创建用户
        user = UserModel(
            name="钱七",
            code="USER_005",
            email="qianqi@example.com",
            balance=8000
        )
        user.save()
        print_success(f"用户已创建: ID={user.id}")  # 访问 id 时自动 flush

    # 验证钩子执行
    if len(hook_logs) == 2:
        print_success(f"所有钩子已执行: {hook_logs}")
    else:
        print_error(f"钩子执行不完整: {hook_logs}")


def test_scenario_6_rollback_hook():
    """场景6：回滚钩子"""
    print_section("场景6：回滚钩子")

    rollback_executed = []

    try:
        with tm.transaction() as tx:
            # 注册 after_rollback 钩子
            @tx.after_rollback
            def cleanup_on_rollback(ctx):
                rollback_executed.append(True)
                print_info("钩子执行: after_rollback - 清理临时资源")

            # 注册 on_error 钩子
            @tx.on_error
            def log_error(ctx, error):
                print_info(f"钩子执行: on_error - 记录错误: {error}")

            user = UserModel(
                name="孙八",
                code="USER_006",
                email="sunba@example.com",
                balance=6000
            )
            user.add()

            # 触发异常
            raise ValueError("模拟业务错误")

    except ValueError:
        pass

    if rollback_executed:
        print_success("回滚钩子已正确执行")
    else:
        print_error("回滚钩子未执行！")


def test_scenario_7_propagation_required():
    """场景7：传播行为 - REQUIRED"""
    print_section("场景7：传播行为 - REQUIRED（加入现有事务）")

    with tm.transaction() as outer_tx:
        print_info(f"外层事务: ID={id(outer_tx)}, 嵌套层级={outer_tx.nesting_level}")

        user = UserModel(
            name="周九",
            code="USER_007",
            email="zhoujiu@example.com",
            balance=7000
        )
        user.add()

        # 内层事务使用 REQUIRED 传播行为（默认）
        with tm.transaction(propagation=TransactionPropagation.REQUIRED) as inner_tx:
            print_info(f"内层事务: ID={id(inner_tx)}, 嵌套层级={inner_tx.nesting_level}")

            if inner_tx is outer_tx:
                print_success("REQUIRED: 内层事务加入了外层事务（同一个事务对象）")
            else:
                print_error("REQUIRED: 应该是同一个事务对象！")

            order = OrderModel(
                name="订单002",
                code="ORDER_002",
                user_id=1,
                amount=500,
                status="completed"
            )
            order.add()

    print_success("外层事务提交，所有操作都已提交")


def test_scenario_8_propagation_nested():
    """场景8：传播行为 - NESTED"""
    print_section("场景8：传播行为 - NESTED（创建保存点）")

    with tm.transaction() as outer_tx:
        user = UserModel(
            name="吴十",
            code="USER_008",
            email="wushi@example.com",
            balance=9000
        )
        user.save()
        user_id = user.id  # 访问 id 时自动 flush
        print_success(f"外层事务：用户已创建 ID={user_id}")

        try:
            # 使用 NESTED 传播行为创建嵌套事务
            with tm.transaction(propagation=TransactionPropagation.NESTED) as nested_tx:
                print_info("NESTED: 创建了保存点")

                log = LogModel(
                    name="日志001",
                    code="LOG_001",
                    action="create_order",
                    user_id=user_id,
                    details="尝试创建订单"
                )
                log.save()
                print_info(f"嵌套事务：日志已创建 ID={log.id}")  # 访问 id 时自动 flush

                # 触发异常，回滚嵌套事务
                raise ValueError("订单创建失败")

        except ValueError as e:
            print_info(f"嵌套事务回滚: {e}")

        # 外层事务继续

    # 验证结果
    found_user = UserModel.get(user_id)
    found_logs = LogModel.query.filter_by(user_id=user_id).all()

    if found_user and len(found_logs) == 0:
        print_success("NESTED 传播行为正确：用户已创建，日志已回滚")
    else:
        print_error("NESTED 传播行为失败！")


def test_scenario_9_transactional_decorator():
    """场景9：@transactional 装饰器"""
    print_section("场景9：@transactional 装饰器")

    @tm.transactional()
    def create_user_with_order(username: str, email: str, order_amount: int):
        """使用装饰器管理事务"""
        print_info(f"装饰器内：是否在事务中 = {tm.is_in_transaction()}")

        # 创建用户
        user = UserModel(
            name=username,
            code=f"USER_{username}",
            email=email,
            balance=10000
        )
        user.save()
        print_success(f"用户已创建: ID={user.id}")  # 访问 id 时自动 flush

        # 创建订单
        order = OrderModel(
            name=f"{username}的订单",
            code=f"ORDER_{username}",
            user_id=user.id,
            amount=order_amount,
            status="completed"
        )
        order.save()
        print_success(f"订单已创建: ID={order.id}")  # 访问 id 时自动 flush

        return user.id, order.id

    # 调用装饰器函数
    user_id, order_id = create_user_with_order("郑十一", "zhengshiyi@example.com", 1500)

    # 验证数据已提交
    found_user = UserModel.get(user_id)
    found_order = OrderModel.get(order_id)

    if found_user and found_order:
        print_success("@transactional 装饰器工作正常，数据已提交")
    else:
        print_error("@transactional 装饰器失败！")


def test_scenario_10_commit_suppression():
    """场景10：提交抑制机制"""
    print_section("场景10：提交抑制机制")

    print_info("在事务上下文中，commit=True 会被自动抑制...")

    try:
        with tm.transaction() as tx:
            print_info(f"suppress_commit = {tx.suppress_commit}")

            user = UserModel(
                name="冯十二",
                code="USER_012",
                email="fengshier@example.com",
                balance=12000
            )
            user.save()
            user_id = user.id  # 访问 id 时自动 flush

            # 尝试使用 commit=True（会被抑制）
            user.name = "冯十二（已更新）"
            user.save(commit=True)  # 这里的 commit=True 会被抑制
            print_info("调用了 save(commit=True)，但提交被抑制")

            # 触发异常，整个事务回滚
            raise ValueError("测试提交抑制")

    except ValueError:
        pass

    # 验证数据已回滚
    found = UserModel.get(user_id)
    if found is None:
        print_success("提交抑制机制正常：commit=True 被抑制，整个事务回滚")
    else:
        print_error("提交抑制机制失败！")


def test_scenario_11_retry_decorator():
    """场景11：重试装饰器"""
    print_section("场景11：重试装饰器")

    attempt_count = [0]

    @transaction_with_retry(max_retries=3, retry_delay=0.1, retry_on=(ValueError,))
    def flaky_operation():
        """模拟不稳定的操作"""
        attempt_count[0] += 1
        print_info(f"尝试第 {attempt_count[0]} 次...")

        if attempt_count[0] < 3:
            raise ValueError("模拟临时错误")

        # 第3次成功
        user = UserModel(
            name="陈十三",
            code="USER_013",
            email="chenshisan@example.com",
            balance=13000
        )
        user.save()
        print_success(f"第 {attempt_count[0]} 次成功，用户已创建: ID={user.id}")  # 访问 id 时自动 flush
        return user.id

    # 执行重试操作
    user_id = flaky_operation()

    if attempt_count[0] == 3:
        print_success(f"重试装饰器工作正常：重试了 {attempt_count[0]} 次后成功")
    else:
        print_error("重试装饰器失败！")


def test_scenario_12_context_data():
    """场景12：事务上下文数据共享"""
    print_section("场景12：事务上下文数据共享")

    result = []

    with tm.transaction() as tx:
        # 在事务上下文中存储数据
        tx.data["operation"] = "create_user"
        tx.data["timestamp"] = "2024-01-01 12:00:00"

        @tx.before_commit
        def log_operation(ctx):
            operation = ctx.data.get("operation")
            timestamp = ctx.data.get("timestamp")
            print_info(f"before_commit: 操作={operation}, 时间={timestamp}")
            result.append(operation)

        @tx.after_commit
        def send_notification(ctx):
            operation = ctx.data.get("operation")
            print_info(f"after_commit: 发送通知 - 操作={operation}")
            result.append("notification_sent")

        user = UserModel(
            name="楚十四",
            code="USER_014",
            email="chushisi@example.com",
            balance=14000
        )
        user.add()

    if len(result) == 2 and result[0] == "create_user":
        print_success("上下文数据在钩子间正确共享")
    else:
        print_error("上下文数据共享失败！")


# ==================== 主函数 ====================

def main():
    """主函数"""
    print("\n" + "="*70)
    print("  事务管理器功能演示")
    print("="*70)

    # 初始化数据库
    print_info("初始化数据库...")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, "demo_transaction_manager.db")

    # 删除旧数据库
    if os.path.exists(db_path):
        os.remove(db_path)
        print_info("已删除旧数据库")

    engine, session_scope = init_database(f"sqlite:///{db_path}", echo=False)
    CoreModel.query = session_scope.query_property()

    # 配置事务管理器
    tm.get_session = lambda: session_scope()

    # 创建数据表
    print_info("创建数据表...")
    BaseModel.metadata.drop_all(engine)
    BaseModel.metadata.create_all(engine)
    print_success("数据库初始化完成")

    # 运行所有测试场景
    try:
        test_scenario_1_basic_transaction()
        test_scenario_2_transaction_rollback()
        test_scenario_3_manual_rollback()
        test_scenario_4_nested_transaction()
        test_scenario_5_transaction_hooks()
        test_scenario_6_rollback_hook()
        test_scenario_7_propagation_required()
        test_scenario_8_propagation_nested()
        test_scenario_9_transactional_decorator()
        test_scenario_10_commit_suppression()
        test_scenario_11_retry_decorator()
        test_scenario_12_context_data()

        print_section("所有测试场景执行完成")
        print_success("事务管理器功能演示成功！")

    except Exception as e:
        print_error(f"测试过程中发生错误: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

    finally:
        session_scope.remove()
        print()
        print_info(f"数据库文件保存在: {db_path}")
        print_info("可以使用 SQLite 工具查看数据库内容")


if __name__ == "__main__":
    main()
