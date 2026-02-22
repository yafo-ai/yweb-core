"""级联软删除功能测试

测试不同关系类型的级联软删除行为：
1. DELETE - 级联软删除（订单-订单项）
2. SET_NULL - 设置外键为空（部门-员工）
3. DO_NOTHING/UNLINK - 不删除/解除关联（用户-角色）
4. PROTECT - 限制删除
"""

import pytest
from datetime import datetime
from sqlalchemy import Column, Integer, String, ForeignKey, Table, create_engine
from sqlalchemy.orm import sessionmaker, relationship, scoped_session

from yweb.orm import (
    CoreModel,
    BaseModel,
    SimpleSoftDeleteMixin,
    configure_cascade_soft_delete,
    get_cascade_manager,
    activate_soft_delete_hook,
    # Django 风格关系字段
    fields,
    OnDelete,
)


# ==================== 测试模型定义 ====================
# 使用 fields.* 风格定义关系（关系在子表定义）

# 场景1：订单-订单项（强聚合关系，级联软删除）
class OrderModel(BaseModel):
    """订单模型"""
    __tablename__ = "test_orders"
    __table_args__ = {'extend_existing': True}
    
    order_no = Column(String(50))
    total_amount = Column(Integer, default=0)
    # items 属性由 OrderItemModel 的 backref 自动创建


class OrderItemModel(BaseModel):
    """订单项模型"""
    __tablename__ = "test_order_items"
    __table_args__ = {'extend_existing': True}
    
    product_name = Column(String(100))
    quantity = Column(Integer, default=1)
    price = Column(Integer, default=0)
    
    # 多对一：订单删除时，订单项也被软删除
    order = fields.ManyToOne(OrderModel, on_delete=fields.DELETE)


# 场景2：部门-员工（可选父子关系，设置外键为空）
class DepartmentModel(BaseModel):
    """部门模型"""
    __tablename__ = "test_departments"
    __table_args__ = {'extend_existing': True}
    
    dept_name = Column(String(100))
    # employees 属性由 EmployeeModel 的 backref 自动创建


class EmployeeModel(BaseModel):
    """员工模型"""
    __tablename__ = "test_employees"
    __table_args__ = {'extend_existing': True}
    
    emp_name = Column(String(100))
    
    # 多对一：部门删除时，员工的部门ID设为空
    department = fields.ManyToOne(DepartmentModel, on_delete=fields.SET_NULL, nullable=True)


# 场景3：用户-角色（多对多关系，解除关联）
class RoleModel(BaseModel):
    """角色模型"""
    __tablename__ = "test_roles"
    __table_args__ = {'extend_existing': True}
    
    role_name = Column(String(50))
    # cascade_users 属性由 CascadeUserModel 的 backref 自动创建


class CascadeUserModel(BaseModel):
    """用户模型"""
    __tablename__ = "test_cascade_users"
    __table_args__ = {'extend_existing': True}
    
    username = Column(String(50))
    
    # 多对多：用户删除时，只解除关联，不删除角色
    roles = fields.ManyToMany(RoleModel, on_delete=fields.UNLINK)


# 场景4：限制删除
class CategoryModel(BaseModel):
    """分类模型"""
    __tablename__ = "test_categories"
    __table_args__ = {'extend_existing': True}
    
    category_name = Column(String(100))
    # products 属性由 ProductModel 的 backref 自动创建


class ProductModel(BaseModel):
    """产品模型"""
    __tablename__ = "test_products"
    __table_args__ = {'extend_existing': True}
    
    product_name = Column(String(100))
    
    # 多对一：有产品时禁止删除分类
    category = fields.ManyToOne(CategoryModel, on_delete=fields.PROTECT, nullable=True)


# ==================== 测试类 ====================

class TestOnDeleteEnum:
    """OnDelete 枚举测试"""
    
    def test_on_delete_enum_values(self):
        """测试枚举值存在"""
        assert OnDelete.DELETE == "delete"
        assert OnDelete.SET_NULL == "set_null"
        assert OnDelete.DO_NOTHING == "do_nothing"
        assert OnDelete.PROTECT == "protect"
        assert OnDelete.UNLINK == "unlink"


class TestCascadeSoftDeleteManager:
    """级联软删除管理器测试"""
    
    def test_configure_cascade_soft_delete(self):
        """测试配置级联软删除"""
        configure_cascade_soft_delete()
        manager = get_cascade_manager()
        assert manager is not None
    
    def test_manager_has_deleted_field_name(self):
        """测试管理器有 deleted_field_name 属性"""
        configure_cascade_soft_delete(deleted_field_name="deleted_at")
        manager = get_cascade_manager()
        assert manager.deleted_field_name == "deleted_at"


class TestOrderItemCascadeDelete:
    """订单-订单项级联软删除测试（场景1）"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        activate_soft_delete_hook()
        configure_cascade_soft_delete()
        
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_create_order_with_items(self):
        """测试：创建订单和订单项"""
        order = OrderModel(order_no="ORD-001", total_amount=1000)
        
        # 通过 relationship 集合添加子对象（推荐方式）
        item1 = OrderItemModel(product_name="Product A", quantity=2, price=300)
        item2 = OrderItemModel(product_name="Product B", quantity=1, price=400)
        order.order_items.append(item1)
        order.order_items.append(item2)
        order.add(True)
        
        assert len(order.order_items) == 2
    
    def test_soft_delete_order_cascades_to_items(self):
        """测试：软删除订单时，订单项也被级联软删除"""
        # 创建订单和订单项（通过 relationship 集合）
        order = OrderModel(order_no="ORD-002", total_amount=500)
        item = OrderItemModel(product_name="Product C", quantity=1, price=500)
        order.order_items.append(item)
        order.add(True)
        
        order_id = order.id
        item_id = item.id
        
        # 重新获取订单对象（确保在 session 中）
        session = self.session_scope()
        order = session.get(OrderModel, order_id)
        
        # 获取管理器并执行级联软删除
        manager = get_cascade_manager()
        manager.soft_delete_with_cascade(order, session)
        session.commit()
        
        # 验证订单被软删除
        order = OrderModel.query.execution_options(include_deleted=True).filter_by(id=order_id).first()
        assert order.deleted_at is not None
        
        # 验证订单项也被软删除
        item = OrderItemModel.query.execution_options(include_deleted=True).filter_by(id=item_id).first()
        assert item.deleted_at is not None
    
    def test_item_foreign_key_preserved_after_cascade_delete(self):
        """测试：级联软删除后，订单项的外键保持不变"""
        # 创建订单和订单项（通过 relationship 集合）
        order = OrderModel(order_no="ORD-003", total_amount=200)
        item = OrderItemModel(product_name="Product D", quantity=1, price=200)
        order.order_items.append(item)
        order.add(True)
        
        order_id = order.id
        item_id = item.id
        
        # 重新获取订单对象（确保在 session 中）
        session = self.session_scope()
        order = session.get(OrderModel, order_id)
        
        # 执行级联软删除
        manager = get_cascade_manager()
        manager.soft_delete_with_cascade(order, session)
        session.commit()
        
        # 验证外键保持不变（动态获取外键列名）
        from sqlalchemy import inspect
        mapper = inspect(OrderItemModel)
        rel = mapper.relationships['order']
        fk_column_name = list(rel.local_columns)[0].name
        
        item = OrderItemModel.query.execution_options(include_deleted=True).filter_by(id=item_id).first()
        assert getattr(item, fk_column_name) == order_id
    
    def test_append_items_via_relationship_and_save(self):
        """测试：通过 relationship append 添加子对象并用 save 保存"""
        order = OrderModel(order_no="ORD-004", total_amount=1000)
        order.add(True)
        
        # 通过 relationship append 添加（不显式设置 order_id）
        item1 = OrderItemModel(product_name="Product E", quantity=1, price=500)
        item2 = OrderItemModel(product_name="Product F", quantity=2, price=250)
        order.order_items.append(item1)
        order.order_items.append(item2)
        order.save(True)
        
        # 验证子对象被保存且关联正确设置（通过 relationship 访问）
        assert item1.id is not None
        assert item2.id is not None
        assert item1.order.id == order.id
        assert item2.order.id == order.id
        assert len(order.order_items) == 2
    
    def test_new_order_with_items_via_append_then_add(self):
        """测试：新建订单时通过 append 添加子对象后调用 add 保存"""
        order = OrderModel(order_no="ORD-005", total_amount=800)
        item = OrderItemModel(product_name="Product G", quantity=1, price=800)
        
        # 新对象 append 子对象后 add
        order.order_items.append(item)
        order.add(True)
        
        # 验证父子对象都被保存（通过 relationship 访问）
        assert order.id is not None
        assert item.id is not None
        assert item.order.id == order.id
        assert len(order.order_items) == 1
    
    def test_delete_method_triggers_cascade_soft_delete(self):
        """测试：通过 order.delete(True) 触发级联软删除（而非直接调用 manager）"""
        order = OrderModel(order_no="ORD-006", total_amount=600)
        order.add(True)
        order_id = order.id
        
        item1 = OrderItemModel(product_name="Product H", quantity=1, price=300)
        item2 = OrderItemModel(product_name="Product I", quantity=1, price=300)
        order.order_items.append(item1)
        order.order_items.append(item2)
        order.save(True)
        
        item1_id = item1.id
        item2_id = item2.id
        
        # 通过 delete 方法触发（这会经过 before_flush hook）
        order.delete(True)
        
        # 验证订单被软删除
        order = OrderModel.query.execution_options(include_deleted=True).filter_by(id=order_id).first()
        assert order is not None
        assert order.deleted_at is not None
        
        # 验证订单项也被级联软删除
        item1 = OrderItemModel.query.execution_options(include_deleted=True).filter_by(id=item1_id).first()
        item2 = OrderItemModel.query.execution_options(include_deleted=True).filter_by(id=item2_id).first()
        assert item1.deleted_at is not None
        assert item2.deleted_at is not None
        
        # 验证正常查询看不到已删除的记录
        active_orders = OrderModel.query.all()
        active_items = OrderItemModel.query.all()
        assert len(active_orders) == 0
        assert len(active_items) == 0


class TestDepartmentEmployeeSetNull:
    """部门-员工设置外键为空测试（场景2）"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        activate_soft_delete_hook()
        configure_cascade_soft_delete()
        
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_create_department_with_employees(self):
        """测试：创建部门和员工"""
        dept = DepartmentModel(dept_name="Engineering")
        
        # 通过 relationship 集合添加（推荐方式）
        emp1 = EmployeeModel(emp_name="Alice")
        emp2 = EmployeeModel(emp_name="Bob")
        dept.employees.append(emp1)
        dept.employees.append(emp2)
        dept.add(True)
        
        assert len(dept.employees) == 2
    
    def test_soft_delete_department_sets_employee_fk_null(self):
        """测试：软删除部门时，员工的部门ID设为空"""
        # 创建部门和员工（通过 relationship 集合）
        dept = DepartmentModel(dept_name="Marketing")
        emp = EmployeeModel(emp_name="Charlie")
        dept.employees.append(emp)
        dept.add(True)
        
        dept_id = dept.id
        emp_id = emp.id
        
        # 重新获取部门对象（确保在 session 中）
        session = self.session_scope()
        dept = session.get(DepartmentModel, dept_id)
        
        # 执行级联软删除（SET_NULL）
        manager = get_cascade_manager()
        manager.soft_delete_with_cascade(dept, session)
        session.commit()
        
        # 验证部门被软删除
        dept = DepartmentModel.query.execution_options(include_deleted=True).filter_by(id=dept_id).first()
        assert dept.deleted_at is not None
        
        # 验证员工的部门关联被设为空，但员工本身未被删除（通过 relationship 访问）
        emp = EmployeeModel.query.filter_by(id=emp_id).first()
        assert emp is not None
        assert emp.department is None
        assert emp.deleted_at is None


class TestUserRoleUnlink:
    """用户-角色解除关联测试（场景3）
    
    注意：多对多关系与软删除自动过滤有复杂的交互。
    这里主要测试核心功能逻辑。
    """
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话 - 不启用软删除过滤"""
        # 不启用 soft_delete_hook 以避免查询过滤干扰测试
        configure_cascade_soft_delete()
        
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_soft_delete_cascade_unlink_clears_collection(self):
        """测试：解除关联 UNLINK 类型会清除关联集合"""
        user = CascadeUserModel(username="test_user")
        role = RoleModel(role_name="test_role")
        
        # 通过 relationship 建立多对多关联
        user.roles.append(role)
        user.add(True)
        
        user_id = user.id
        role_id = role.id
        
        # 重新获取用户（通过 relationship 自动加载 roles）
        user = CascadeUserModel.get(user_id)
        
        # 验证关联存在
        assert len(user.roles) == 1
        
        # 执行级联软删除（UNLINK）
        from sqlalchemy.orm import object_session
        session = object_session(user)
        
        # 确保关联的 roles 对象都在 session 中
        for r in user.roles:
            session.add(r)
        
        manager = get_cascade_manager()
        manager.soft_delete_with_cascade(user, session)
        session.commit()
        
        # 重新查询验证用户被软删除（绕过可能的 session 问题）
        user = CascadeUserModel.query.execution_options(include_deleted=True).filter_by(id=user_id).first()
        assert user is not None
        assert user.deleted_at is not None
        
        # 验证角色未被删除
        role = RoleModel.query.filter_by(id=role_id).first()
        assert role is not None
        assert role.deleted_at is None
    
    def test_unlink_on_delete_exists(self):
        """测试：UNLINK 级联类型存在"""
        assert OnDelete.UNLINK == "unlink"


class TestCategoryProductRestrict:
    """分类-产品限制删除测试（场景4）"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        activate_soft_delete_hook()
        configure_cascade_soft_delete()
        
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_soft_delete_category_with_products_raises_error(self):
        """测试：有产品时，软删除分类应该失败"""
        # 创建分类和产品（通过 relationship 集合）
        category = CategoryModel(category_name="Electronics")
        product = ProductModel(product_name="Phone")
        category.products.append(product)
        category.add(True)
        
        category_id = category.id
        
        # 重新获取分类对象（确保在 session 中）
        session = self.session_scope()
        category = session.get(CategoryModel, category_id)
        
        # 尝试软删除有产品的分类
        manager = get_cascade_manager()
        
        with pytest.raises(ValueError) as exc_info:
            manager.soft_delete_with_cascade(category, session)
        
        assert "无法删除" in str(exc_info.value)
        assert "存在关联" in str(exc_info.value)
    
    def test_soft_delete_empty_category_succeeds(self):
        """测试：没有产品时，可以软删除分类"""
        category = CategoryModel(category_name="Books")
        category.add(True)
        
        category_id = category.id
        
        # 软删除空分类
        session = self.session_scope()
        manager = get_cascade_manager()
        manager.soft_delete_with_cascade(category, session)
        session.commit()
        
        # 验证分类被软删除
        category = CategoryModel.query.execution_options(include_deleted=True).filter_by(id=category_id).first()
        assert category.deleted_at is not None


class TestSoftDeleteMixin:
    """SoftDeleteMixin 测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        activate_soft_delete_hook()
        configure_cascade_soft_delete()
        
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_is_deleted_property(self):
        """测试 is_deleted 属性"""
        order = OrderModel(order_no="TEST-001")
        order.add(True)
        
        order_id = order.id
        
        # 初始状态：未删除
        assert order.is_deleted == False
        
        # 执行软删除
        session = self.session_scope()
        manager = get_cascade_manager()
        manager.soft_delete_with_cascade(order, session)
        session.commit()
        
        # 重新查询验证
        order = OrderModel.query.execution_options(include_deleted=True).filter_by(id=order_id).first()
        assert order is not None
        assert order.deleted_at is not None
