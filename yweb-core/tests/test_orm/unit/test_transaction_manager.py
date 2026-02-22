"""事务管理器测试

测试 TransactionManager 的核心功能：
1. 基础事务测试（提交、回滚、状态转换）
2. 嵌套事务测试（Savepoint）
3. 钩子测试（before_commit, after_commit 等）
4. 传播行为测试（REQUIRED, REQUIRES_NEW, NESTED 等）
5. 提交抑制测试
"""

import pytest
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import sessionmaker, scoped_session

from yweb.orm import CoreModel, BaseModel
from yweb.orm.transaction import (
    TransactionState,
    TransactionPropagation,
    TransactionHookType,
    TransactionHook,
    TransactionContext,
    SavepointContext,
    TransactionManager,
    get_current_transaction,
    transaction_with_retry,
    TransactionNotActiveError,
    TransactionAlreadyCommittedError,
    PropagationError,
    HookExecutionError,
)

from tests.helpers import reset_transaction_manager


# ==================== 测试模型定义 ====================

class TxTestUser(BaseModel):
    """事务管理器测试用户模型"""
    __tablename__ = "test_tx_mgr_users"
    __table_args__ = {"extend_existing": True}
    
    email = Column(String(100), nullable=True)
    balance = Column(Integer, default=0)


class TxTestLog(BaseModel):
    """事务管理器测试日志模型"""
    __tablename__ = "test_tx_mgr_logs"
    __table_args__ = {"extend_existing": True}
    
    action = Column(String(100), nullable=False)
    user_id = Column(Integer, nullable=True)


# ==================== 基础事务测试 ====================

class TestBasicTransaction:
    """基础事务测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """自动初始化数据库会话"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        
        # 创建新的事务管理器实例（避免测试间干扰）
        self.tm = TransactionManager.__new__(TransactionManager)
        reset_transaction_manager(self.tm)
        self.tm.__init__()
        self.tm.get_session = lambda: self.session_scope()
        
        yield
        self.session_scope.remove()
    
    def test_transaction_normal_commit(self):
        """测试正常提交"""
        with self.tm.transaction() as tx:
            user = TxTestUser(name="CommitTest", email="commit@test.com")
            user.add()
            self.session_scope().flush()
            user_id = user.id
        
        # 验证提交成功
        found = TxTestUser.get(user_id)
        assert found is not None
        assert found.name == "CommitTest"
    
    def test_transaction_rollback_on_exception(self):
        """测试异常时自动回滚"""
        user_id = None
        
        try:
            with self.tm.transaction() as tx:
                user = TxTestUser(name="RollbackTest", email="rollback@test.com")
                user.add()
                self.session_scope().flush()
                user_id = user.id
                
                # 抛出异常触发回滚
                raise ValueError("测试异常")
        except ValueError:
            pass
        
        # 验证回滚成功
        if user_id:
            found = TxTestUser.get(user_id)
            assert found is None, "事务应该已回滚"
    
    def test_transaction_manual_rollback(self):
        """测试手动回滚"""
        with self.tm.transaction(auto_commit=False) as tx:
            user = TxTestUser(name="ManualRollback", email="manual@test.com")
            user.add()
            self.session_scope().flush()
            user_id = user.id
            
            # 手动回滚
            tx.rollback()
        
        # 验证回滚成功
        found = TxTestUser.get(user_id)
        assert found is None
    
    def test_transaction_state_transitions(self):
        """测试事务状态转换"""
        with self.tm.transaction() as tx:
            # 进入上下文后应为 ACTIVE
            assert tx.state == TransactionState.ACTIVE
            assert tx.is_active == True
        
        # 正常退出后应为 COMMITTED
        assert tx.state == TransactionState.COMMITTED
    
    def test_transaction_state_on_rollback(self):
        """测试回滚后的状态"""
        try:
            with self.tm.transaction() as tx:
                raise ValueError("测试")
        except ValueError:
            pass
        
        assert tx.state == TransactionState.ROLLED_BACK
    
    def test_get_current_transaction(self):
        """测试获取当前事务"""
        # 事务外应为 None
        assert get_current_transaction() is None
        
        with self.tm.transaction() as tx:
            # 事务内应能获取到当前事务
            current = get_current_transaction()
            assert current is not None
            assert current is tx
        
        # 事务结束后应为 None
        assert get_current_transaction() is None
    
    def test_is_in_transaction(self):
        """测试是否在事务中"""
        assert self.tm.is_in_transaction() == False
        
        with self.tm.transaction() as tx:
            assert self.tm.is_in_transaction() == True
        
        assert self.tm.is_in_transaction() == False


# ==================== 嵌套事务（Savepoint）测试 ====================

class TestNestedTransaction:
    """嵌套事务（Savepoint）测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """自动初始化数据库会话"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        
        self.tm = TransactionManager.__new__(TransactionManager)
        reset_transaction_manager(self.tm)
        self.tm.__init__()
        self.tm.get_session = lambda: self.session_scope()
        
        yield
        self.session_scope.remove()
    
    def test_savepoint_commit(self):
        """测试保存点正常提交"""
        with self.tm.transaction() as tx:
            user = TxTestUser(name="Outer", email="outer@test.com")
            user.add()
            
            with tx.savepoint("sp1") as sp:
                log = TxTestLog(action="create_user", user_id=1)
                log.add()
            
            # savepoint 释放后，日志应该在事务中
            self.session_scope().flush()
        
        # 验证都提交了
        users = TxTestUser.get_all()
        logs = TxTestLog.get_all()
        assert len(users) == 1
        assert len(logs) == 1
    
    def test_savepoint_rollback_not_affect_outer(self):
        """测试保存点回滚不影响外层"""
        with self.tm.transaction() as tx:
            user = TxTestUser(name="WillKeep", email="keep@test.com")
            user.add()
            self.session_scope().flush()
            
            try:
                with tx.savepoint("sp1") as sp:
                    log = TxTestLog(action="will_rollback", user_id=1)
                    log.add()
                    self.session_scope().flush()
                    
                    # 抛出异常，savepoint 回滚
                    raise ValueError("Savepoint rollback")
            except ValueError:
                pass
            
            # 外层用户应该还在
            self.session_scope().flush()
        
        # 验证：用户存在，日志不存在
        users = TxTestUser.get_all()
        logs = TxTestLog.get_all()
        assert len(users) == 1
        assert users[0].name == "WillKeep"
        assert len(logs) == 0, "保存点内的日志应该被回滚"
    
    def test_multiple_savepoints(self):
        """测试多层嵌套保存点"""
        with self.tm.transaction() as tx:
            user1 = TxTestUser(name="User1", email="u1@test.com")
            user1.add()
            
            with tx.savepoint("sp1") as sp1:
                user2 = TxTestUser(name="User2", email="u2@test.com")
                user2.add()
                
                with tx.savepoint("sp2") as sp2:
                    user3 = TxTestUser(name="User3", email="u3@test.com")
                    user3.add()
            
            self.session_scope().flush()
        
        # 验证所有用户都提交了
        users = TxTestUser.get_all()
        assert len(users) == 3
    
    def test_named_savepoint(self):
        """测试命名保存点"""
        with self.tm.transaction() as tx:
            with tx.savepoint("my_savepoint") as sp:
                assert sp.name == "my_savepoint"
    
    def test_auto_named_savepoint(self):
        """测试自动命名保存点"""
        with self.tm.transaction() as tx:
            with tx.savepoint() as sp1:
                assert sp1.name.startswith("sp_")
            
            with tx.savepoint() as sp2:
                assert sp2.name.startswith("sp_")
                assert sp2.name != sp1.name


# ==================== 钩子测试 ====================

class TestTransactionHooks:
    """事务钩子测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """自动初始化数据库会话"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        
        self.tm = TransactionManager.__new__(TransactionManager)
        reset_transaction_manager(self.tm)
        self.tm.__init__()
        self.tm.get_session = lambda: self.session_scope()
        
        yield
        self.session_scope.remove()
    
    def test_before_commit_hook(self):
        """测试 before_commit 钩子"""
        hook_called = []
        
        with self.tm.transaction() as tx:
            @tx.before_commit
            def on_before_commit(ctx):
                hook_called.append("before_commit")
            
            user = TxTestUser(name="HookTest", email="hook@test.com")
            user.add()
        
        assert "before_commit" in hook_called
    
    def test_after_commit_hook(self):
        """测试 after_commit 钩子"""
        hook_called = []
        
        with self.tm.transaction() as tx:
            @tx.after_commit
            def on_after_commit(ctx):
                hook_called.append("after_commit")
            
            user = TxTestUser(name="HookTest", email="hook@test.com")
            user.add()
        
        assert "after_commit" in hook_called
    
    def test_after_rollback_hook(self):
        """测试 after_rollback 钩子"""
        hook_called = []
        
        try:
            with self.tm.transaction() as tx:
                @tx.after_rollback
                def on_after_rollback(ctx):
                    hook_called.append("after_rollback")
                
                raise ValueError("触发回滚")
        except ValueError:
            pass
        
        assert "after_rollback" in hook_called
    
    def test_hook_execution_order(self):
        """测试钩子执行顺序"""
        execution_order = []
        
        with self.tm.transaction() as tx:
            @tx.before_commit
            def hook1(ctx):
                execution_order.append(1)
            
            @tx.before_commit
            def hook2(ctx):
                execution_order.append(2)
            
            @tx.after_commit
            def hook3(ctx):
                execution_order.append(3)
        
        # before_commit 应该在 after_commit 之前
        assert execution_order.index(1) < execution_order.index(3)
        assert execution_order.index(2) < execution_order.index(3)
    
    def test_before_commit_hook_error_prevents_commit(self):
        """测试 before_commit 钩子异常阻止提交"""
        with pytest.raises(HookExecutionError):
            with self.tm.transaction() as tx:
                @tx.before_commit
                def bad_hook(ctx):
                    raise ValueError("Hook error")
                
                user = TxTestUser(name="WillNotCommit", email="nocommit@test.com")
                user.add()
        
        # 验证用户未创建
        users = TxTestUser.get_all()
        assert len(users) == 0
    
    def test_after_commit_hook_error_not_affect_commit(self):
        """测试 after_commit 钩子异常不影响已提交的事务"""
        with self.tm.transaction() as tx:
            @tx.after_commit
            def bad_hook(ctx):
                raise ValueError("After commit error")
            
            user = TxTestUser(name="WillCommit", email="commit@test.com")
            user.add()
        
        # 验证用户已创建（事务已提交）
        users = TxTestUser.get_all()
        assert len(users) == 1
    
    def test_global_hook_decorator(self):
        """测试全局钩子（装饰器方式）"""
        hook_called = []
        
        @self.tm.global_hooks.before_commit
        def global_before_commit(ctx):
            hook_called.append("global_before_commit")
        
        with self.tm.transaction() as tx:
            user = TxTestUser(name="GlobalHookTest", email="global@test.com")
            user.add()
        
        assert "global_before_commit" in hook_called
        
        # 清理全局钩子
        self.tm.clear_global_hooks()
    
    def test_on_error_hook(self):
        """测试错误处理钩子"""
        error_caught = []
        
        try:
            with self.tm.transaction() as tx:
                @tx.on_error
                def handle_error(ctx, error):
                    error_caught.append(str(error))
                
                raise ValueError("Test error")
        except ValueError:
            pass
        
        assert len(error_caught) == 1
        assert "Test error" in error_caught[0]


# ==================== 传播行为测试 ====================

class TestTransactionPropagation:
    """事务传播行为测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """自动初始化数据库会话"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        
        self.tm = TransactionManager.__new__(TransactionManager)
        reset_transaction_manager(self.tm)
        self.tm.__init__()
        self.tm.get_session = lambda: self.session_scope()
        
        yield
        self.session_scope.remove()
    
    def test_propagation_required_join_existing(self):
        """测试 REQUIRED：加入现有事务"""
        with self.tm.transaction() as outer_tx:
            outer_level = outer_tx.nesting_level
            
            with self.tm.transaction(propagation=TransactionPropagation.REQUIRED) as inner_tx:
                # 应该是同一个事务
                assert inner_tx is outer_tx
                # 嵌套层级应该增加
                assert inner_tx.nesting_level == outer_level + 1
    
    def test_propagation_required_new_when_no_existing(self):
        """测试 REQUIRED：无现有事务时创建新事务"""
        with self.tm.transaction(propagation=TransactionPropagation.REQUIRED) as tx:
            assert tx.is_active
            assert tx.nesting_level == 1
    
    def test_propagation_mandatory_requires_existing(self):
        """测试 MANDATORY：必须在事务中"""
        with pytest.raises(PropagationError) as exc_info:
            with self.tm.transaction(propagation=TransactionPropagation.MANDATORY) as tx:
                pass
        
        assert "MANDATORY" in str(exc_info.value)
    
    def test_propagation_mandatory_with_existing(self):
        """测试 MANDATORY：有现有事务时正常执行"""
        with self.tm.transaction() as outer_tx:
            with self.tm.transaction(propagation=TransactionPropagation.MANDATORY) as inner_tx:
                assert inner_tx is outer_tx
    
    def test_propagation_never_rejects_existing(self):
        """测试 NEVER：不能在事务中执行"""
        with self.tm.transaction() as outer_tx:
            with pytest.raises(PropagationError) as exc_info:
                with self.tm.transaction(propagation=TransactionPropagation.NEVER) as inner_tx:
                    pass
            
            assert "NEVER" in str(exc_info.value)
    
    def test_propagation_never_without_existing(self):
        """测试 NEVER：无事务时正常执行"""
        # 应该不抛出异常
        with self.tm.transaction(propagation=TransactionPropagation.NEVER) as tx:
            pass
    
    def test_propagation_nested_creates_savepoint(self):
        """测试 NESTED：创建嵌套事务（savepoint）"""
        with self.tm.transaction() as outer_tx:
            user = TxTestUser(name="Outer", email="outer@test.com")
            user.add()
            
            try:
                with self.tm.transaction(propagation=TransactionPropagation.NESTED) as inner_tx:
                    log = TxTestLog(action="will_rollback", user_id=1)
                    log.add()
                    self.session_scope().flush()
                    raise ValueError("Nested rollback")
            except ValueError:
                pass
            
            self.session_scope().flush()
        
        # 外层提交，内层回滚
        users = TxTestUser.get_all()
        logs = TxTestLog.get_all()
        assert len(users) == 1
        assert len(logs) == 0
    
    def test_propagation_nested_requires_existing(self):
        """测试 NESTED：需要外层事务"""
        with pytest.raises(PropagationError) as exc_info:
            with self.tm.transaction(propagation=TransactionPropagation.NESTED) as tx:
                pass
        
        assert "NESTED" in str(exc_info.value)


# ==================== 提交抑制测试 ====================

class TestCommitSuppression:
    """提交抑制测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """自动初始化数据库会话"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        
        self.tm = TransactionManager.__new__(TransactionManager)
        reset_transaction_manager(self.tm)
        self.tm.__init__()
        self.tm.get_session = lambda: self.session_scope()
        
        yield
        self.session_scope.remove()
    
    def test_commit_true_suppressed_in_transaction(self):
        """测试 commit=True 在事务中被抑制"""
        try:
            with self.tm.transaction() as tx:
                user = TxTestUser(name="Suppressed", email="suppressed@test.com")
                user.add()
                self.session_scope().flush()
                user_id = user.id
                
                # 即使传 commit=True，也不会立即提交
                user.name = "Updated"
                user.save(commit=True)  # 应该被抑制
                
                # 抛出异常触发回滚
                raise ValueError("Rollback test")
        except ValueError:
            pass
        
        # 如果 commit=True 没有被抑制，user 应该已经保存
        # 但由于被抑制，整个事务回滚，user 不应该存在
        found = TxTestUser.get(user_id)
        assert found is None, "commit=True 应该被事务上下文抑制"
    
    def test_allow_commit_context_allows_commit(self):
        """测试 allow_commit() 临时允许提交"""
        with self.tm.transaction() as tx:
            user = TxTestUser(name="AllowCommit", email="allow@test.com")
            user.add()
            self.session_scope().flush()
            user_id = user.id
            
            # 检查 suppress_commit 状态
            assert tx.suppress_commit == True
            
            with tx.allow_commit():
                # 在 allow_commit 上下文中，suppress_commit 应为 False
                assert tx.suppress_commit == False
            
            # 退出后恢复
            assert tx.suppress_commit == True
    
    def test_suppress_commit_disabled(self):
        """测试禁用提交抑制"""
        with self.tm.transaction(suppress_commit=False) as tx:
            assert tx.suppress_commit == False
    
    def test_should_suppress_commit_method(self):
        """测试 should_suppress_commit 方法"""
        # 事务外不应抑制
        assert self.tm.should_suppress_commit() == False
        
        with self.tm.transaction() as tx:
            # 事务内应该抑制
            assert self.tm.should_suppress_commit() == True
            assert tx.should_suppress_commit() == True


# ==================== 装饰器测试 ====================

class TestTransactionalDecorator:
    """@transactional 装饰器测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """自动初始化数据库会话"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        
        self.tm = TransactionManager.__new__(TransactionManager)
        reset_transaction_manager(self.tm)
        self.tm.__init__()
        self.tm.get_session = lambda: self.session_scope()
        
        yield
        self.session_scope.remove()
    
    def test_transactional_decorator_commits(self):
        """测试装饰器正常提交"""
        @self.tm.transactional()
        def create_user(name: str):
            user = TxTestUser(name=name, email=f"{name}@test.com")
            user.add()
            return user
        
        user = create_user("Decorated")
        
        # 验证已提交
        found = TxTestUser.get(user.id)
        assert found is not None
        assert found.name == "Decorated"
    
    def test_transactional_decorator_rollback_on_exception(self):
        """测试装饰器异常时回滚"""
        @self.tm.transactional()
        def create_user_with_error(name: str):
            user = TxTestUser(name=name, email=f"{name}@test.com")
            user.add()
            self.session_scope().flush()
            raise ValueError("Simulated error")
        
        with pytest.raises(ValueError):
            create_user_with_error("WillRollback")
        
        # 验证已回滚
        users = TxTestUser.query.filter_by(name="WillRollback").all()
        assert len(users) == 0
    
    def test_transactional_with_propagation(self):
        """测试装饰器的传播行为"""
        @self.tm.transactional(propagation=TransactionPropagation.MANDATORY)
        def inner_function():
            return get_current_transaction()
        
        # 没有外层事务时应该失败
        with pytest.raises(PropagationError):
            inner_function()
        
        # 有外层事务时应该成功
        with self.tm.transaction() as outer_tx:
            inner_tx = inner_function()
            assert inner_tx is outer_tx


# ==================== 重试装饰器测试 ====================

class TestTransactionRetry:
    """事务重试装饰器测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """自动初始化数据库会话"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        
        self.tm = TransactionManager.__new__(TransactionManager)
        reset_transaction_manager(self.tm)
        self.tm.__init__()
        self.tm.get_session = lambda: self.session_scope()
        
        yield
        self.session_scope.remove()
    
    def test_retry_succeeds_after_failures(self):
        """测试重试后成功"""
        attempt_count = [0]
        
        @transaction_with_retry(max_retries=3, retry_delay=0.01, retry_on=(ValueError,))
        def flaky_function():
            attempt_count[0] += 1
            if attempt_count[0] < 3:
                raise ValueError("Simulated failure")
            return "success"
        
        result = flaky_function()
        
        assert result == "success"
        assert attempt_count[0] == 3
    
    def test_retry_exhausted(self):
        """测试重试次数耗尽"""
        attempt_count = [0]
        
        @transaction_with_retry(max_retries=2, retry_delay=0.01, retry_on=(ValueError,))
        def always_fail():
            attempt_count[0] += 1
            raise ValueError("Always fails")
        
        with pytest.raises(ValueError):
            always_fail()
        
        # 1 次初始 + 2 次重试 = 3 次
        assert attempt_count[0] == 3
    
    def test_retry_only_for_specified_exceptions(self):
        """测试只对指定异常重试"""
        attempt_count = [0]
        
        @transaction_with_retry(max_retries=3, retry_delay=0.01, retry_on=(ValueError,))
        def raise_type_error():
            attempt_count[0] += 1
            raise TypeError("Not retryable")
        
        with pytest.raises(TypeError):
            raise_type_error()
        
        # TypeError 不在重试列表中，应该只执行一次
        assert attempt_count[0] == 1


# ==================== 自定义钩子类测试 ====================

class TestCustomHookClass:
    """自定义钩子类测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """自动初始化数据库会话"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        
        self.tm = TransactionManager.__new__(TransactionManager)
        reset_transaction_manager(self.tm)
        self.tm.__init__()
        self.tm.get_session = lambda: self.session_scope()
        
        yield
        self.session_scope.remove()
    
    def test_custom_hook_class(self):
        """测试自定义钩子类"""
        executed = []
        
        class AuditHook(TransactionHook):
            @property
            def hook_type(self):
                return TransactionHookType.AFTER_COMMIT
            
            @property
            def priority(self):
                return 10
            
            @property
            def name(self):
                return "AuditHook"
            
            def execute(self, context):
                executed.append("audit")
        
        # 注册全局钩子
        self.tm.register_global_hook(AuditHook())
        
        with self.tm.transaction() as tx:
            user = TxTestUser(name="HookClassTest", email="hookclass@test.com")
            user.add()
        
        assert "audit" in executed
        
        # 清理
        self.tm.clear_global_hooks()
    
    def test_hook_priority(self):
        """测试钩子优先级"""
        executed = []
        
        class HighPriorityHook(TransactionHook):
            @property
            def hook_type(self):
                return TransactionHookType.BEFORE_COMMIT
            
            @property
            def priority(self):
                return 1  # 高优先级
            
            def execute(self, context):
                executed.append("high")
        
        class LowPriorityHook(TransactionHook):
            @property
            def hook_type(self):
                return TransactionHookType.BEFORE_COMMIT
            
            @property
            def priority(self):
                return 100  # 低优先级
            
            def execute(self, context):
                executed.append("low")
        
        # 先注册低优先级，再注册高优先级
        self.tm.register_global_hook(LowPriorityHook())
        self.tm.register_global_hook(HighPriorityHook())
        
        with self.tm.transaction() as tx:
            pass
        
        # 高优先级应该先执行
        assert executed.index("high") < executed.index("low")
        
        # 清理
        self.tm.clear_global_hooks()


# ==================== 上下文数据测试 ====================

class TestTransactionContextData:
    """事务上下文数据测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """自动初始化数据库会话"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        
        self.tm = TransactionManager.__new__(TransactionManager)
        reset_transaction_manager(self.tm)
        self.tm.__init__()
        self.tm.get_session = lambda: self.session_scope()
        
        yield
        self.session_scope.remove()
    
    def test_context_data_shared_between_hooks(self):
        """测试上下文数据在钩子间共享"""
        result = []
        
        with self.tm.transaction() as tx:
            @tx.before_commit
            def set_data(ctx):
                ctx.data["user_id"] = 123
            
            @tx.after_commit
            def get_data(ctx):
                result.append(ctx.data.get("user_id"))
        
        assert result[0] == 123
    
    def test_context_data_isolation(self):
        """测试不同事务的上下文数据隔离"""
        results = []
        
        with self.tm.transaction() as tx1:
            tx1.data["tx_name"] = "tx1"
            
            @tx1.after_commit
            def capture1(ctx):
                results.append(ctx.data.get("tx_name"))
        
        with self.tm.transaction() as tx2:
            tx2.data["tx_name"] = "tx2"
            
            @tx2.after_commit
            def capture2(ctx):
                results.append(ctx.data.get("tx_name"))
        
        assert results == ["tx1", "tx2"]
