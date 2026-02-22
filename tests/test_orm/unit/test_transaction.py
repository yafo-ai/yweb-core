"""事务处理测试（底层 ORM 行为）

测试 CoreModel/BaseModel 的基础事务行为（不使用 TransactionManager）：
- update() vs update(True) 的区别
- 手动事务提交与回滚
- 乐观锁（版本控制）的并发处理
- 跨模型业务事务（Service 层场景）

注意：TransactionManager 的高级功能测试请参见 test_transaction_manager.py
"""

import pytest
from datetime import datetime
from sqlalchemy import Column, Integer, String, ForeignKey, create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, relationship
from sqlalchemy.orm.exc import StaleDataError

from yweb.orm import CoreModel, BaseModel


# ==================== 测试模型定义 ====================

class TransactionUser(BaseModel):
    """事务测试用户模型"""
    __tablename__ = "test_transaction_users"
    __table_args__ = {"extend_existing": True}
    
    email = Column(String(100), nullable=True)


# 多模型事务测试用模型
class TransactionOrder(BaseModel):
    """订单模型（事务测试用）"""
    __tablename__ = "test_tx_orders"
    __table_args__ = {"extend_existing": True}
    
    customer_name = Column(String(100), nullable=False)
    total_amount = Column(Integer, default=0)
    status = Column(String(20), default="pending")  # pending, completed, cancelled
    
    items = relationship("TransactionOrderItem", back_populates="order")


class TransactionOrderItem(BaseModel):
    """订单项模型（事务测试用）"""
    __tablename__ = "test_tx_order_items"
    __table_args__ = {"extend_existing": True}
    
    order_id = Column(Integer, ForeignKey("test_tx_orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("test_tx_products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(Integer, nullable=False)
    
    order = relationship("TransactionOrder", back_populates="items")
    product = relationship("TransactionProduct")


class TransactionProduct(BaseModel):
    """产品模型（事务测试用）"""
    __tablename__ = "test_tx_products"
    __table_args__ = {"extend_existing": True}
    
    price = Column(Integer, nullable=False)
    stock = Column(Integer, default=0)  # 库存


# ==================== 测试类 ====================

class TestTransaction:
    """事务处理测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """自动初始化数据库会话"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_update_without_commit(self):
        """测试 update() 不自动提交事务"""
        # 创建用户
        user = TransactionUser(name="Original", email="original@test.com")
        user.add(True)
        user_id = user.id
        original_ver = user.ver
        
        # 使用 update() 不提交
        user.name = "Updated"
        user.update()  # 不传 True，不自动提交
        
        # 在同一 session 中，变更可见
        assert user.name == "Updated"
        
        # 回滚事务
        self.session_scope().rollback()
        
        # 重新查询，应该是原始值
        user = TransactionUser.get(user_id)
        assert user.name == "Original", "回滚后应恢复原始值"
        assert user.ver == original_ver, "回滚后版本号应不变"
    
    def test_update_with_commit(self):
        """测试 update(True) 自动提交事务"""
        # 创建用户
        user = TransactionUser(name="Original", email="original@test.com")
        user.add(True)
        user_id = user.id
        original_ver = user.ver
        
        # 使用 update(True) 自动提交
        user.name = "Updated"
        user.update(True)  # 传 True，自动提交
        
        # 清除 session 缓存
        self.session_scope().expire_all()
        
        # 重新查询，应该是更新后的值
        user = TransactionUser.get(user_id)
        assert user.name == "Updated", "提交后应保留更新值"
        assert user.ver == original_ver + 1, "版本号应自动加 1"
    
    def test_multiple_updates_single_transaction(self):
        """测试多个更新操作在同一事务中"""
        # 创建两个用户
        user1 = TransactionUser(name="User1", email="user1@test.com")
        user2 = TransactionUser(name="User2", email="user2@test.com")
        TransactionUser.add_all([user1, user2], commit=True)
        
        user1_id = user1.id
        user2_id = user2.id
        
        # 更新两个用户，不提交
        user1.name = "User1_Updated"
        user1.update()
        
        user2.name = "User2_Updated"
        user2.update()
        
        # 此时变更在 session 中，但未持久化
        # 手动提交整个事务
        self.session_scope().commit()
        
        # 清除缓存并验证
        self.session_scope().expire_all()
        
        user1 = TransactionUser.get(user1_id)
        user2 = TransactionUser.get(user2_id)
        
        assert user1.name == "User1_Updated"
        assert user2.name == "User2_Updated"
    
    def test_partial_rollback_scenario(self):
        """测试部分操作后回滚的场景"""
        # 创建用户
        user = TransactionUser(name="Original", email="original@test.com")
        user.add(True)
        user_id = user.id
        
        # 第一次更新并提交
        user.name = "FirstUpdate"
        user.update(True)
        
        # 第二次更新但不提交
        user.name = "SecondUpdate"
        user.update()
        
        # 回滚第二次更新
        self.session_scope().rollback()
        
        # 验证只有第一次更新保留
        self.session_scope().expire_all()
        user = TransactionUser.get(user_id)
        assert user.name == "FirstUpdate", "只有已提交的更新应保留"
    
    def test_version_control_increments(self):
        """测试版本号自动递增"""
        user = TransactionUser(name="VersionTest", email="version@test.com")
        user.add(True)
        
        assert user.ver == 1, "初始版本号应为 1"
        
        # 第一次更新
        user.name = "Update1"
        user.update(True)
        assert user.ver == 2, "第一次更新后版本号应为 2"
        
        # 第二次更新
        user.name = "Update2"
        user.update(True)
        assert user.ver == 3, "第二次更新后版本号应为 3"
        
        # 第三次更新
        user.email = "new_email@test.com"
        user.update(True)
        assert user.ver == 4, "第三次更新后版本号应为 4"


class TestOptimisticLocking:
    """乐观锁（版本控制）测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """自动初始化数据库会话"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        self.SessionLocal = SessionLocal
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_concurrent_update_conflict(self):
        """测试并发更新导致的版本冲突"""
        # 创建用户
        user = TransactionUser(name="ConcurrentTest", email="concurrent@test.com")
        user.add(True)
        user_id = user.id
        
        # 模拟另一个会话先更新了数据
        # 创建第二个独立会话
        session2 = self.SessionLocal()
        try:
            user_in_session2 = session2.query(TransactionUser).filter_by(id=user_id).first()
            user_in_session2.name = "UpdatedBySession2"
            session2.commit()
        finally:
            session2.close()
        
        # 当前会话中的 user 对象还是旧版本号
        # 尝试更新会触发 StaleDataError
        user.name = "UpdatedBySession1"
        
        with pytest.raises(StaleDataError):
            user.update(True)
    
    def test_refresh_after_conflict(self):
        """测试冲突后刷新数据"""
        # 创建用户
        user = TransactionUser(name="RefreshTest", email="refresh@test.com")
        user.add(True)
        user_id = user.id
        
        # 模拟另一个会话更新
        session2 = self.SessionLocal()
        try:
            user_in_session2 = session2.query(TransactionUser).filter_by(id=user_id).first()
            user_in_session2.name = "UpdatedByOther"
            session2.commit()
        finally:
            session2.close()
        
        # 刷新当前对象以获取最新数据
        self.session_scope().refresh(user)
        
        assert user.name == "UpdatedByOther", "刷新后应获取最新数据"
        assert user.ver == 2, "刷新后版本号应为 2"
        
        # 现在可以正常更新
        user.name = "FinalUpdate"
        user.update(True)
        assert user.ver == 3


class TestAddOperations:
    """add() 操作测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """自动初始化数据库会话"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_add_without_commit(self):
        """测试 add() 不自动提交"""
        user = TransactionUser(name="AddTest", email="add@test.com")
        user.add()  # 不传 True
        
        # 对象在 session 中，有临时 id
        assert user in self.session_scope()
        
        # 回滚
        self.session_scope().rollback()
        
        # 对象不再持久化
        users = TransactionUser.get_all()
        assert len(users) == 0, "回滚后应没有记录"
    
    def test_add_with_commit(self):
        """测试 add(True) 自动提交"""
        user = TransactionUser(name="AddCommitTest", email="addcommit@test.com")
        user.add(True)
        user_id = user.id
        
        # 清除缓存
        self.session_scope().expire_all()
        
        # 重新查询验证
        found = TransactionUser.get(user_id)
        assert found is not None
        assert found.name == "AddCommitTest"
    
    def test_add_all_without_commit(self):
        """测试 add_all() 不自动提交"""
        user1 = TransactionUser(name="Batch1", email="batch1@test.com")
        user2 = TransactionUser(name="Batch2", email="batch2@test.com")
        
        TransactionUser.add_all([user1, user2])  # 不传 commit=True
        
        # 回滚
        self.session_scope().rollback()
        
        # 应该没有记录
        users = TransactionUser.get_all()
        assert len(users) == 0
    
    def test_add_all_with_commit(self):
        """测试 add_all(commit=True) 自动提交"""
        user1 = TransactionUser(name="Batch1", email="batch1@test.com")
        user2 = TransactionUser(name="Batch2", email="batch2@test.com")
        
        TransactionUser.add_all([user1, user2], commit=True)
        
        # 验证
        users = TransactionUser.get_all()
        assert len(users) == 2


class TestDeleteOperations:
    """delete() 操作测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """自动初始化数据库会话"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_delete_without_commit(self):
        """测试 delete() 不自动提交"""
        user = TransactionUser(name="DeleteTest", email="delete@test.com")
        user.add(True)
        user_id = user.id
        
        # 删除但不提交
        user.delete()
        
        # 回滚
        self.session_scope().rollback()
        
        # 用户应该还存在
        found = TransactionUser.get(user_id)
        assert found is not None, "回滚后记录应存在"
    
    def test_delete_with_commit(self):
        """测试 delete(True) 自动提交"""
        user = TransactionUser(name="DeleteCommitTest", email="deletecommit@test.com")
        user.add(True)
        user_id = user.id
        
        # 删除并提交
        user.delete(True)
        
        # 用户应该不存在（get() 找不到时返回 None）
        found = TransactionUser.get(user_id)
        assert found is None, "删除后记录应不存在"


class TestSaveOperations:
    """save() 操作测试（自动判断 add 或 update）"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """自动初始化数据库会话"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_save_new_object_without_commit(self):
        """测试 save() 新对象不自动提交"""
        user = TransactionUser(name="SaveNew", email="savenew@test.com")
        user.save()  # 新对象，执行 add
        
        # 回滚
        self.session_scope().rollback()
        
        # 应该没有记录
        users = TransactionUser.get_all()
        assert len(users) == 0
    
    def test_save_new_object_with_commit(self):
        """测试 save(True) 新对象自动提交"""
        user = TransactionUser(name="SaveNewCommit", email="savenewcommit@test.com")
        user.save(True)  # 新对象，执行 add 并提交
        
        user_id = user.id
        
        # 清除缓存
        self.session_scope().expire_all()
        
        # 验证
        found = TransactionUser.get(user_id)
        assert found is not None
        assert found.name == "SaveNewCommit"
    
    def test_save_existing_object_without_commit(self):
        """测试 save() 现有对象不自动提交"""
        user = TransactionUser(name="SaveExisting", email="saveexisting@test.com")
        user.add(True)
        user_id = user.id
        
        # 修改并 save
        user.name = "SaveExistingUpdated"
        user.save()  # 现有对象，执行 update
        
        # 回滚
        self.session_scope().rollback()
        
        # 验证
        self.session_scope().expire_all()
        found = TransactionUser.get(user_id)
        assert found.name == "SaveExisting", "回滚后应恢复原值"
    
    def test_save_existing_object_with_commit(self):
        """测试 save(True) 现有对象自动提交"""
        user = TransactionUser(name="SaveExistingCommit", email="saveexistingcommit@test.com")
        user.add(True)
        user_id = user.id
        original_ver = user.ver
        
        # 修改并 save
        user.name = "SaveExistingCommitUpdated"
        user.save(True)  # 现有对象，执行 update 并提交
        
        # 验证
        self.session_scope().expire_all()
        found = TransactionUser.get(user_id)
        assert found.name == "SaveExistingCommitUpdated"
        assert found.ver == original_ver + 1


# ==================== 多模型业务事务测试 ====================

class InsufficientStockError(Exception):
    """库存不足异常"""
    pass


class OrderService:
    """订单服务 - 模拟业务层
    
    演示在 Service 层如何处理跨多个 Model 的事务
    """
    
    def __init__(self, session_scope):
        self.session_scope = session_scope
    
    def create_order(self, customer_name: str, items: list[dict]) -> TransactionOrder:
        """创建订单（跨多模型事务）
        
        业务流程:
        1. 创建订单
        2. 创建订单项
        3. 扣减库存
        4. 计算总金额
        5. 一次性提交
        
        Args:
            customer_name: 客户名称
            items: 订单项列表 [{"product_id": 1, "quantity": 2}, ...]
        
        Returns:
            创建的订单对象
        
        Raises:
            InsufficientStockError: 库存不足时抛出，整个事务回滚
        """
        try:
            # 1. 创建订单（不提交，但 flush 以获取 id）
            order = TransactionOrder(customer_name=customer_name, status="pending")
            order.add()  # 不传 True，不提交
            self.session_scope().flush()  # flush 以获取 order.id
            
            total_amount = 0
            
            # 2. 遍历订单项
            for item_data in items:
                product_id = item_data["product_id"]
                quantity = item_data["quantity"]
                
                # 获取产品
                product = TransactionProduct.get(product_id)
                if product is None:
                    raise ValueError(f"产品不存在: {product_id}")
                
                # 3. 检查并扣减库存
                if product.stock < quantity:
                    raise InsufficientStockError(
                        f"产品 {product.name} 库存不足: 需要 {quantity}, 仅有 {product.stock}"
                    )
                
                product.stock -= quantity
                product.update()  # 不提交
                
                # 4. 创建订单项
                order_item = TransactionOrderItem(
                    order_id=order.id,
                    product_id=product_id,
                    quantity=quantity,
                    price=product.price
                )
                order_item.add()  # 不提交
                
                total_amount += product.price * quantity
            
            # 5. 更新订单总金额
            order.total_amount = total_amount
            order.status = "completed"
            order.update()  # 不提交
            
            # 6. 所有操作成功，一次性提交
            self.session_scope().commit()
            
            return order
            
        except Exception as e:
            # 任何错误，回滚整个事务
            self.session_scope().rollback()
            raise
    
    def cancel_order(self, order_id: int) -> TransactionOrder:
        """取消订单（恢复库存）
        
        业务流程:
        1. 获取订单
        2. 恢复所有订单项的库存
        3. 标记订单为已取消
        4. 一次性提交
        """
        try:
            order = TransactionOrder.get(order_id)
            if order is None:
                raise ValueError(f"订单不存在: {order_id}")
            
            if order.status == "cancelled":
                raise ValueError("订单已取消")
            
            # 恢复库存
            for item in order.items:
                product = TransactionProduct.get(item.product_id)
                product.stock += item.quantity
                product.update()
            
            # 标记取消
            order.status = "cancelled"
            order.update()
            
            # 提交
            self.session_scope().commit()
            
            return order
            
        except Exception as e:
            self.session_scope().rollback()
            raise


class TestMultiModelTransaction:
    """多模型业务事务测试 - 模拟 Service 层场景"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        self.order_service = OrderService(self.session_scope)
        yield
        self.session_scope.remove()
    
    @pytest.fixture
    def sample_products(self):
        """创建测试产品"""
        product1 = TransactionProduct(name="iPhone", price=999, stock=10)
        product2 = TransactionProduct(name="MacBook", price=1999, stock=5)
        product3 = TransactionProduct(name="AirPods", price=199, stock=20)
        TransactionProduct.add_all([product1, product2, product3], commit=True)
        return [product1, product2, product3]
    
    def test_create_order_success(self, sample_products):
        """测试成功创建订单 - 多模型一次性提交"""
        # 准备订单项
        items = [
            {"product_id": sample_products[0].id, "quantity": 2},  # 2 个 iPhone
            {"product_id": sample_products[1].id, "quantity": 1},  # 1 个 MacBook
        ]
        
        # 创建订单
        order = self.order_service.create_order("张三", items)
        
        # 验证订单
        assert order.id is not None
        assert order.customer_name == "张三"
        assert order.status == "completed"
        assert order.total_amount == 999 * 2 + 1999 * 1  # 3997
        
        # 验证库存已扣减
        self.session_scope().expire_all()
        iphone = TransactionProduct.get(sample_products[0].id)
        macbook = TransactionProduct.get(sample_products[1].id)
        airpods = TransactionProduct.get(sample_products[2].id)
        
        assert iphone.stock == 8, "iPhone 库存应从 10 减到 8"
        assert macbook.stock == 4, "MacBook 库存应从 5 减到 4"
        assert airpods.stock == 20, "AirPods 库存应不变"
        
        # 验证订单项
        order_items = TransactionOrderItem.query.filter_by(order_id=order.id).all()
        assert len(order_items) == 2
    
    def test_create_order_rollback_on_insufficient_stock(self, sample_products):
        """测试库存不足时回滚 - 所有操作都应撤销"""
        # 记录原始库存
        original_stocks = {p.id: p.stock for p in sample_products}
        
        # 准备订单项（MacBook 只有 5 个，要买 10 个）
        items = [
            {"product_id": sample_products[0].id, "quantity": 2},  # 2 个 iPhone（会先处理）
            {"product_id": sample_products[1].id, "quantity": 10},  # 10 个 MacBook（库存不足）
        ]
        
        # 创建订单应该失败
        with pytest.raises(InsufficientStockError) as exc_info:
            self.order_service.create_order("李四", items)
        
        assert "库存不足" in str(exc_info.value)
        
        # 验证所有库存都回滚了（包括第一个成功处理的 iPhone）
        self.session_scope().expire_all()
        for product in sample_products:
            current_product = TransactionProduct.get(product.id)
            assert current_product.stock == original_stocks[product.id], \
                f"{current_product.name} 库存应回滚到 {original_stocks[product.id]}"
        
        # 验证没有创建订单
        orders = TransactionOrder.query.filter_by(customer_name="李四").all()
        assert len(orders) == 0, "失败的订单不应被创建"
        
        # 验证没有创建订单项
        all_order_items = TransactionOrderItem.get_all()
        assert len(all_order_items) == 0, "失败的订单项不应被创建"
    
    def test_cancel_order_restores_stock(self, sample_products):
        """测试取消订单恢复库存"""
        # 先创建一个订单
        items = [
            {"product_id": sample_products[0].id, "quantity": 3},
            {"product_id": sample_products[2].id, "quantity": 5},
        ]
        order = self.order_service.create_order("王五", items)
        order_id = order.id
        
        # 验证库存已扣减
        self.session_scope().expire_all()
        assert TransactionProduct.get(sample_products[0].id).stock == 7  # 10 - 3
        assert TransactionProduct.get(sample_products[2].id).stock == 15  # 20 - 5
        
        # 取消订单
        cancelled_order = self.order_service.cancel_order(order_id)
        
        # 验证订单状态
        assert cancelled_order.status == "cancelled"
        
        # 验证库存已恢复
        self.session_scope().expire_all()
        assert TransactionProduct.get(sample_products[0].id).stock == 10
        assert TransactionProduct.get(sample_products[2].id).stock == 20
    
    def test_partial_failure_full_rollback(self, sample_products):
        """测试部分成功时的完整回滚
        
        场景：第一个产品扣库存成功，第二个失败，应该全部回滚
        """
        # 模拟一个更复杂的场景：产品不存在
        items = [
            {"product_id": sample_products[0].id, "quantity": 1},  # 存在
            {"product_id": 9999, "quantity": 1},  # 不存在
        ]
        
        with pytest.raises(ValueError) as exc_info:
            self.order_service.create_order("赵六", items)
        
        assert "产品不存在" in str(exc_info.value)
        
        # 验证第一个产品的库存没有被扣减
        self.session_scope().expire_all()
        assert TransactionProduct.get(sample_products[0].id).stock == 10


class TestMultiModelManualTransaction:
    """手动控制多模型事务 - 不使用 Service 封装"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_multiple_models_single_commit(self):
        """测试多个模型操作，最后一次性提交"""
        # 创建产品
        product = TransactionProduct(name="TestProduct", price=100, stock=50)
        product.add()
        
        # 创建订单
        order = TransactionOrder(customer_name="TestCustomer", status="pending")
        order.add()
        
        # flush 以获取 id（不是 commit，事务还在进行中）
        self.session_scope().flush()
        
        # 创建订单项
        order_item = TransactionOrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=5,
            price=100
        )
        order_item.add()
        
        # 扣减库存
        product.stock -= 5
        product.update()
        
        # 更新订单
        order.total_amount = 500
        order.status = "completed"
        order.update()
        
        # 此时都在 session 中，但未持久化
        # 一次性提交
        self.session_scope().commit()
        
        # 验证
        self.session_scope().expire_all()
        
        saved_product = TransactionProduct.get(product.id)
        saved_order = TransactionOrder.get(order.id)
        saved_item = TransactionOrderItem.get(order_item.id)
        
        assert saved_product.stock == 45
        assert saved_order.status == "completed"
        assert saved_order.total_amount == 500
        assert saved_item.quantity == 5
    
    def test_multiple_models_rollback_all(self):
        """测试多个模型操作，回滚所有"""
        # 创建并提交初始数据
        product = TransactionProduct(name="RollbackTest", price=200, stock=30)
        product.add(True)
        product_id = product.id
        
        # 开始新的事务
        product.stock -= 10
        product.update()
        
        order = TransactionOrder(customer_name="WillRollback", status="pending")
        order.add()
        
        # 回滚
        self.session_scope().rollback()
        
        # 验证
        self.session_scope().expire_all()
        
        # 产品库存应该还是 30
        saved_product = TransactionProduct.get(product_id)
        assert saved_product.stock == 30
        
        # 订单不应存在
        orders = TransactionOrder.query.filter_by(customer_name="WillRollback").all()
        assert len(orders) == 0
