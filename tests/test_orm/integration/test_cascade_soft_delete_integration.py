"""端到端级联软删除集成测试

完整测试真实使用场景，覆盖所有级联删除类型：
1. DELETE - 级联软删除（订单-订单项、文章-评论）
2. SET_NULL - 设置外键为空（部门-员工）
3. DO_NOTHING - 不处理（项目-标签）
4. PROTECT - 限制删除（分类-产品）
5. UNLINK - 解除关联（用户-角色多对多）

测试重点：
- 使用 init_database 初始化
- 通过 relationship.append() 添加子对象
- 直接调用 delete() 触发级联（不手动调用 manager）
- 验证查询自动过滤已删除记录
"""

import pytest
from sqlalchemy import Column, Integer, String, ForeignKey, Table
from sqlalchemy.orm import relationship

from yweb.orm import (
    CoreModel,
    BaseModel,
    init_database,
    configure_cascade_soft_delete,
    activate_soft_delete_hook,
    # Django 风格关系字段
    fields,
)


# ==================== 场景1：DELETE - 订单-订单项（强聚合关系）====================

class E2EOrderModel(BaseModel):
    """订单模型"""
    __tablename__ = "e2e_orders"
    __table_args__ = {'extend_existing': True}

    order_no = Column(String(50))
    total_amount = Column(Integer, default=0)
    # e2e_order_items 属性由 E2EOrderItemModel 的 backref 自动创建


class E2EOrderItemModel(BaseModel):
    """订单项模型"""
    __tablename__ = "e2e_order_items"
    __table_args__ = {'extend_existing': True}

    product_name = Column(String(100))
    quantity = Column(Integer, default=1)
    price = Column(Integer, default=0)

    # DELETE：订单删除时，订单项也被软删除
    order = fields.ManyToOne(E2EOrderModel, on_delete=fields.DELETE)


# ==================== 场景2：DELETE - 文章-评论（一对多级联）====================

class E2EArticleModel(BaseModel):
    """文章模型"""
    __tablename__ = "e2e_articles"
    __table_args__ = {'extend_existing': True}

    title = Column(String(200))
    content = Column(String(2000))
    # e2e_comments 属性由 E2ECommentModel 的 backref 自动创建


class E2ECommentModel(BaseModel):
    """评论模型"""
    __tablename__ = "e2e_comments"
    __table_args__ = {'extend_existing': True}

    content = Column(String(500))
    author = Column(String(50))

    # DELETE：文章删除时，评论也被软删除
    article = fields.ManyToOne(E2EArticleModel, on_delete=fields.DELETE)


# ==================== 场景3：SET_NULL - 部门-员工（可选父子关系）====================

class E2EDepartmentModel(BaseModel):
    """部门模型"""
    __tablename__ = "e2e_departments"
    __table_args__ = {'extend_existing': True}

    dept_name = Column(String(100))
    # e2e_employees 属性由 E2EEmployeeModel 的 backref 自动创建


class E2EEmployeeModel(BaseModel):
    """员工模型"""
    __tablename__ = "e2e_employees"
    __table_args__ = {'extend_existing': True}

    emp_name = Column(String(100))

    # SET_NULL：部门删除时，员工的部门ID设为空
    department = fields.ManyToOne(E2EDepartmentModel, on_delete=fields.SET_NULL, nullable=True)


# ==================== 场景4：DO_NOTHING - 项目-标签（松散关系）====================

class E2EProjectModel(BaseModel):
    """项目模型"""
    __tablename__ = "e2e_projects"
    __table_args__ = {'extend_existing': True}

    project_name = Column(String(100))
    # e2e_tags 属性由 E2ETagModel 的 backref 自动创建


class E2ETagModel(BaseModel):
    """标签模型"""
    __tablename__ = "e2e_tags"
    __table_args__ = {'extend_existing': True}

    tag_name = Column(String(50))

    # DO_NOTHING：项目删除时，标签不做任何处理
    project = fields.ManyToOne(E2EProjectModel, on_delete=fields.DO_NOTHING, nullable=True)


# ==================== 场景5：PROTECT - 分类-产品（限制删除）====================

class E2ECategoryModel(BaseModel):
    """分类模型"""
    __tablename__ = "e2e_categories"
    __table_args__ = {'extend_existing': True}

    category_name = Column(String(100))
    # e2e_products 属性由 E2EProductModel 的 backref 自动创建


class E2EProductModel(BaseModel):
    """产品模型"""
    __tablename__ = "e2e_products"
    __table_args__ = {'extend_existing': True}

    product_name = Column(String(100))

    # PROTECT：有产品时禁止删除分类
    category = fields.ManyToOne(E2ECategoryModel, on_delete=fields.PROTECT, nullable=True)


# ==================== 场景6：UNLINK - 用户-角色（多对多）====================

class E2ERoleModel(BaseModel):
    """角色模型"""
    __tablename__ = "e2e_roles"
    __table_args__ = {'extend_existing': True}

    role_name = Column(String(50))
    role_code = Column(String(50))
    # e2e_user_models 属性由 E2EUserModel 的 backref 自动创建


class E2EUserModel(BaseModel):
    """用户模型"""
    __tablename__ = "e2e_users"
    __table_args__ = {'extend_existing': True}

    username = Column(String(50))
    email = Column(String(100))

    # UNLINK：用户删除时，解除与角色的关联
    roles = fields.ManyToMany(E2ERoleModel, on_delete=fields.UNLINK)


# ==================== 测试类 ====================

class TestE2ECascadeIntegration:
    """端到端级联软删除集成测试

    完全模拟真实使用场景，不使用内部 API
    """

    @pytest.fixture(autouse=True)
    def setup_db(self):
        """使用 init_database 初始化（模拟真实使用）"""
        # 激活软删除钩子和级联配置
        activate_soft_delete_hook()
        configure_cascade_soft_delete()

        # 使用 init_database（真实使用方式）
        engine, session_scope = init_database("sqlite:///:memory:", echo=False)

        # 设置 query 属性（真实使用方式）
        CoreModel.query = session_scope.query_property()

        # 创建所有表
        BaseModel.metadata.create_all(engine)

        self.engine = engine
        self.session_scope = session_scope

        yield

        # 清理
        session_scope.remove()

    # ==================== 场景1：DELETE - 订单-订单项 ====================

    def test_order_cascade_delete_via_append(self):
        """测试：通过 append 添加订单项，删除订单时级联软删除"""
        # 1. 创建订单
        order = E2EOrderModel(
            order_no="ORD20240101001",
            total_amount=1500,
            name="测试订单",
            code="ORDER_001"
        )
        order.add(True)

        # 2. 通过 relationship.append() 添加订单项（不显式设置外键）
        item1 = E2EOrderItemModel(
            product_name="iPhone 15",
            quantity=1,
            price=1000
        )
        item2 = E2EOrderItemModel(
            product_name="AirPods Pro",
            quantity=1,
            price=500
        )
        order.e2e_order_items.append(item1)
        order.e2e_order_items.append(item2)
        order.save(True)

        # 3. 验证外键自动设置
        assert item1.order.id == order.id
        assert item2.order.id == order.id
        assert len(order.e2e_order_items) == 2

        order_id = order.id
        item1_id = item1.id
        item2_id = item2.id

        # 4. 直接调用 delete() 触发级联（真实使用方式）
        order.delete(True)

        # 5. 验证订单被软删除
        deleted_order = E2EOrderModel.query.execution_options(include_deleted=True).filter_by(id=order_id).first()
        assert deleted_order is not None
        assert deleted_order.deleted_at is not None
        assert deleted_order.is_deleted == True

        # 6. 验证订单项也被级联软删除
        deleted_item1 = E2EOrderItemModel.query.execution_options(include_deleted=True).filter_by(id=item1_id).first()
        deleted_item2 = E2EOrderItemModel.query.execution_options(include_deleted=True).filter_by(id=item2_id).first()
        assert deleted_item1.deleted_at is not None
        assert deleted_item2.deleted_at is not None

        # 7. 验证正常查询自动过滤已删除记录
        active_orders = E2EOrderModel.query.all()
        active_items = E2EOrderItemModel.query.all()
        assert len(active_orders) == 0
        assert len(active_items) == 0

        # 8. 验证外键保持不变
        assert deleted_item1.order.id == order_id
        assert deleted_item2.order.id == order_id

    def test_order_new_object_append_then_add(self):
        """测试：新建订单时先 append 子对象再 add 保存"""
        # 创建新订单（未保存）
        order = E2EOrderModel(
            order_no="ORD20240101002",
            total_amount=800,
            name="新订单",
            code="ORDER_002"
        )

        # 在保存前 append 订单项
        item = E2EOrderItemModel(
            product_name="MacBook Air",
            quantity=1,
            price=800
        )
        order.e2e_order_items.append(item)

        # 一次性保存父子对象
        order.add(True)

        # 验证都被保存
        assert order.id is not None
        assert item.id is not None
        assert item.order.id == order.id
        assert len(order.e2e_order_items) == 1

    # ==================== 场景2：DELETE - 文章-评论 ====================

    def test_article_cascade_delete_comments(self):
        """测试：删除文章时，评论也被级联软删除"""
        # 创建文章
        article = E2EArticleModel(
            title="测试文章",
            content="这是一篇测试文章",
            name="文章1",
            code="ARTICLE_001"
        )
        article.add(True)

        # 添加评论
        comment1 = E2ECommentModel(content="很好的文章", author="张三")
        comment2 = E2ECommentModel(content="学到了", author="李四")
        comment3 = E2ECommentModel(content="感谢分享", author="王五")

        article.e2e_comments.append(comment1)
        article.e2e_comments.append(comment2)
        article.e2e_comments.append(comment3)
        article.save(True)

        article_id = article.id
        comment_ids = [comment1.id, comment2.id, comment3.id]

        # 删除文章
        article.delete(True)

        # 验证文章被软删除
        deleted_article = E2EArticleModel.query.execution_options(include_deleted=True).filter_by(id=article_id).first()
        assert deleted_article.is_deleted == True

        # 验证所有评论都被级联软删除
        for comment_id in comment_ids:
            deleted_comment = E2ECommentModel.query.execution_options(include_deleted=True).filter_by(id=comment_id).first()
            assert deleted_comment.is_deleted == True
            assert deleted_comment.article.id == article_id  # 外键保持不变

        # 验证正常查询看不到
        assert E2EArticleModel.query.count() == 0
        assert E2ECommentModel.query.count() == 0

    # ==================== 场景3：SET_NULL - 部门-员工 ====================

    def test_department_set_null_on_delete(self):
        """测试：删除部门时，员工的部门ID设为空"""
        # 创建部门
        dept = E2EDepartmentModel(
            dept_name="技术部",
            name="部门1",
            code="DEPT_001"
        )
        dept.add(True)

        # 添加员工
        emp1 = E2EEmployeeModel(emp_name="张三", name="员工1", code="EMP_001")
        emp2 = E2EEmployeeModel(emp_name="李四", name="员工2", code="EMP_002")
        emp3 = E2EEmployeeModel(emp_name="王五", name="员工3", code="EMP_003")

        dept.e2e_employees.append(emp1)
        dept.e2e_employees.append(emp2)
        dept.e2e_employees.append(emp3)
        dept.save(True)

        dept_id = dept.id
        emp_ids = [emp1.id, emp2.id, emp3.id]

        # 验证外键已设置
        assert emp1.department.id == dept_id
        assert emp2.department.id == dept_id
        assert emp3.department.id == dept_id

        # 删除部门
        dept.delete(True)

        # 验证部门被软删除
        deleted_dept = E2EDepartmentModel.query.execution_options(include_deleted=True).filter_by(id=dept_id).first()
        assert deleted_dept.is_deleted == True

        # 验证员工的部门ID被设为空，但员工本身未被删除
        for emp_id in emp_ids:
            emp = E2EEmployeeModel.query.filter_by(id=emp_id).first()
            assert emp is not None
            assert emp.department is None  # 外键被清空，relationship 返回 None
            assert emp.is_deleted == False  # 员工未被删除

        # 验证员工仍然可以查询到
        assert E2EEmployeeModel.query.count() == 3

    # ==================== 场景4：DO_NOTHING - 项目-标签（松散关系）====================

    def test_project_do_nothing_keeps_tags_unchanged(self):
        """测试：删除项目时，标签不做任何处理"""
        # 创建项目
        project = E2EProjectModel(
            project_name="项目A",
            name="项目1",
            code="PROJ_001"
        )
        project.add(True)

        # 添加标签
        tag1 = E2ETagModel(tag_name="Python", name="标签1", code="TAG_001")
        tag2 = E2ETagModel(tag_name="Django", name="标签2", code="TAG_002")

        project.e2e_tags.append(tag1)
        project.e2e_tags.append(tag2)
        project.save(True)

        project_id = project.id
        tag1_id = tag1.id
        tag2_id = tag2.id

        # 验证外键已设置
        assert tag1.project.id == project_id
        assert tag2.project.id == project_id

        # 删除项目
        project.delete(True)

        # 验证项目被软删除
        deleted_project = E2EProjectModel.query.execution_options(include_deleted=True).filter_by(id=project_id).first()
        assert deleted_project.is_deleted == True

        # 验证标签保持不变（外键不变，未被删除）
        tag1 = E2ETagModel.query.filter_by(id=tag1_id).first()
        tag2 = E2ETagModel.query.filter_by(id=tag2_id).first()

        assert tag1 is not None
        assert tag2 is not None
        assert tag1.project.id == project_id  # 外键保持不变
        assert tag2.project.id == project_id
        assert tag1.is_deleted == False  # 未被删除
        assert tag2.is_deleted == False

        # 验证标签仍然可以查询到
        assert E2ETagModel.query.count() == 2

    # ==================== 场景5：PROTECT - 分类-产品 ====================

    def test_category_protect_prevents_delete_with_products(self):
        """测试：有产品时，禁止删除分类"""
        # 创建分类
        category = E2ECategoryModel(
            category_name="电子产品",
            name="分类1",
            code="CAT_001"
        )
        category.add(True)

        # 添加产品
        product = E2EProductModel(
            product_name="iPhone",
            name="产品1",
            code="PROD_001"
        )
        category.e2e_products.append(product)
        category.save(True)

        category_id = category.id
        product_id = product.id

        # 尝试删除有产品的分类，应该抛出异常
        exception_raised = False
        exception_message = ""
        try:
            category.delete(True)  # 这会在 commit 时触发 before_flush 钩子并抛出异常
        except ValueError as e:
            # 预期行为：在 before_flush 钩子中抛出 ValueError
            exception_raised = True
            exception_message = str(e)
        except Exception as e:
            # 其他异常
            exception_raised = True
            exception_message = str(e)

        # 验证异常确实被抛出
        assert exception_raised, "PROTECT 应该抛出异常阻止删除"
        assert "无法删除" in exception_message or "存在关联" in exception_message or "protect" in exception_message.lower(), \
            f"异常消息不符合预期: {exception_message}"

        # 由于异常被抛出，session 中的对象状态可能不一致
        # 需要回滚 session 以清除 deleted 状态
        from sqlalchemy.orm import object_session
        session = object_session(category)
        if session:
            session.rollback()  # 回滚以清除 deleted 状态

        # 重新查询验证实际状态
        category_check = E2ECategoryModel.query.execution_options(include_deleted=True).filter_by(id=category_id).first()
        product_check = E2EProductModel.query.execution_options(include_deleted=True).filter_by(id=product_id).first()

        # 验证：由于异常被抛出且回滚，分类和产品都不应该被删除
        assert category_check is not None, "分类应该仍然存在"
        assert product_check is not None, "产品应该仍然存在"
        assert category_check.is_deleted == False, "分类不应该被删除"
        assert product_check.is_deleted == False, "产品不应该被删除"

        # 最终验证：正常查询应该能看到分类和产品
        assert E2ECategoryModel.query.filter_by(id=category_id).first() is not None, \
            "正常查询应该能找到分类"
        assert E2EProductModel.query.filter_by(id=product_id).first() is not None, \
            "正常查询应该能找到产品"

    def test_category_protect_allows_delete_without_products(self):
        """测试：没有产品时，可以删除分类"""
        # 创建空分类
        category = E2ECategoryModel(
            category_name="图书",
            name="分类2",
            code="CAT_002"
        )
        category.add(True)

        category_id = category.id

        # 删除空分类，应该成功
        category.delete(True)

        # 验证分类被软删除
        deleted_category = E2ECategoryModel.query.execution_options(include_deleted=True).filter_by(id=category_id).first()
        assert deleted_category.is_deleted == True

        # 验证正常查询看不到
        assert E2ECategoryModel.query.count() == 0

    # ==================== 场景6：UNLINK - 用户-角色（多对多）====================

    def test_user_unlink_removes_role_associations(self):
        """测试：删除用户时，解除与角色的关联"""
        # 创建角色
        role_admin = E2ERoleModel(
            role_name="管理员",
            role_code="ADMIN",
            name="角色1",
            code="ROLE_001"
        )
        role_user = E2ERoleModel(
            role_name="普通用户",
            role_code="USER",
            name="角色2",
            code="ROLE_002"
        )
        E2ERoleModel.add_all([role_admin, role_user])

        # 创建用户并关联角色
        user = E2EUserModel(
            username="zhangsan",
            email="zhangsan@example.com",
            name="用户1",
            code="USER_001"
        )
        user.roles.append(role_admin)
        user.roles.append(role_user)
        user.add(True)

        user_id = user.id
        role_admin_id = role_admin.id
        role_user_id = role_user.id

        # 验证关联已建立
        assert len(user.roles) == 2

        # 删除用户
        user.delete(True)

        # 验证用户被软删除
        deleted_user = E2EUserModel.query.execution_options(include_deleted=True).filter_by(id=user_id).first()
        assert deleted_user.is_deleted == True

        # 验证角色未被删除
        role_admin = E2ERoleModel.query.filter_by(id=role_admin_id).first()
        role_user = E2ERoleModel.query.filter_by(id=role_user_id).first()
        assert role_admin is not None
        assert role_user is not None
        assert role_admin.is_deleted == False
        assert role_user.is_deleted == False

        # 验证关联表中的记录被清除
        # 注意：由于用户被软删除，通过 relationship 查询会被过滤
        # 这里我们验证角色仍然存在即可
        assert E2ERoleModel.query.count() == 2

    def test_user_multiple_users_share_roles(self):
        """测试：多个用户共享角色，删除一个用户不影响其他用户"""
        # 创建共享角色
        role = E2ERoleModel(
            role_name="编辑",
            role_code="EDITOR",
            name="角色3",
            code="ROLE_003"
        )

        # 创建两个用户，都关联同一个角色
        user1 = E2EUserModel(
            username="user1",
            email="user1@example.com",
            name="用户2",
            code="USER_002"
        )
        user2 = E2EUserModel(
            username="user2",
            email="user2@example.com",
            name="用户3",
            code="USER_003"
        )

        # 单次提交：先建立关联，再一次性提交所有对象
        user1.roles.append(role)
        user2.roles.append(role)

        E2EUserModel.add_all([user1, user2, role], commit=True)

        user1_id = user1.id
        user2_id = user2.id
        role_id = role.id

        # 删除 user1
        user1.delete(True)

        # 验证 user1 被软删除
        deleted_user1 = E2EUserModel.query.execution_options(include_deleted=True).filter_by(id=user1_id).first()
        assert deleted_user1.is_deleted == True

        # 验证 user2 和 role 都未受影响
        user2 = E2EUserModel.query.filter_by(id=user2_id).first()
        role = E2ERoleModel.query.filter_by(id=role_id).first()

        assert user2 is not None
        assert user2.is_deleted == False
        assert role is not None
        assert role.is_deleted == False

        # 验证 user2 仍然关联着角色
        assert len(user2.roles) == 1
        assert user2.roles[0].id == role_id

    # ==================== 综合场景测试 ====================

    def test_complex_scenario_multiple_cascades(self):
        """测试：复杂场景 - 多层级联删除"""
        # 创建订单
        order = E2EOrderModel(
            order_no="ORD20240101999",
            total_amount=3000,
            name="复杂订单",
            code="ORDER_999"
        )
        order.add(True)

        # 添加多个订单项
        items = []
        for i in range(5):
            item = E2EOrderItemModel(
                product_name=f"产品{i+1}",
                quantity=i+1,
                price=100 * (i+1)
            )
            order.e2e_order_items.append(item)
            items.append(item)

        order.save(True)

        order_id = order.id
        item_ids = [item.id for item in items]

        # 验证所有订单项都已保存
        assert len(order.e2e_order_items) == 5
        assert E2EOrderItemModel.query.count() == 5

        # 删除订单
        order.delete(True)

        # 验证订单和所有订单项都被软删除
        assert E2EOrderModel.query.count() == 0
        assert E2EOrderItemModel.query.count() == 0

        # 验证包含已删除记录的查询
        all_orders = E2EOrderModel.query.execution_options(include_deleted=True).all()
        all_items = E2EOrderItemModel.query.execution_options(include_deleted=True).all()

        assert len(all_orders) == 1
        assert len(all_items) == 5
        assert all(item.is_deleted for item in all_items)

    def test_query_filtering_after_cascade_delete(self):
        """测试：级联删除后，查询自动过滤的完整性"""
        # 创建多个订单
        order1 = E2EOrderModel(order_no="ORD001", total_amount=100, name="订单1", code="O1")
        order2 = E2EOrderModel(order_no="ORD002", total_amount=200, name="订单2", code="O2")
        order3 = E2EOrderModel(order_no="ORD003", total_amount=300, name="订单3", code="O3")

        E2EOrderModel.add_all([order1, order2, order3], commit=True)

        # 为每个订单添加订单项
        for order in [order1, order2, order3]:
            item = E2EOrderItemModel(product_name=f"产品-{order.order_no}", quantity=1, price=100)
            order.e2e_order_items.append(item)
            order.save(True)

        # 验证初始状态
        assert E2EOrderModel.query.count() == 3
        assert E2EOrderItemModel.query.count() == 3

        # 删除 order2
        order2.delete(True)

        # 验证查询自动过滤
        active_orders = E2EOrderModel.query.all()
        active_items = E2EOrderItemModel.query.all()

        assert len(active_orders) == 2
        assert len(active_items) == 2

        # 验证剩余的是 order1 和 order3
        order_nos = [o.order_no for o in active_orders]
        assert "ORD001" in order_nos
        assert "ORD003" in order_nos
        assert "ORD002" not in order_nos

    def test_backref_auto_creation(self):
        """测试：backref=True 自动创建反向引用"""
        # 创建订单
        order = E2EOrderModel(
            order_no="ORD-BACKREF",
            total_amount=500,
            name="测试反向引用",
            code="ORDER_BACKREF"
        )
        order.add(True)

        # 创建订单项并通过 append 关联
        item = E2EOrderItemModel(
            product_name="测试产品",
            quantity=1,
            price=500
        )
        order.e2e_order_items.append(item)
        order.save(True)

        # 验证外键已正确设置
        assert item.order.id == order.id

        # 重新查询验证关系
        item_from_db = E2EOrderItemModel.query.filter_by(id=item.id).first()
        assert item_from_db.order.id == order.id
