"""完整的级联软删除手动测试脚本

覆盖所有级联删除类型的测试场景：
1. DELETE - 级联软删除（订单-订单项、文章-评论）
2. SET_NULL - 设置外键为空（部门-员工）
3. DO_NOTHING - 不处理（项目-标签）
4. PROTECT - 限制删除（分类-产品）
5. UNLINK - 解除关联（用户-角色多对多）

运行方式：
    python demo_cascade_all_scenarios.py
"""

import os
from sqlalchemy import Column, Integer, String
from yweb.orm import (
    CoreModel,
    BaseModel,
    init_database,
    fields,
    configure_cascade_soft_delete,
    activate_soft_delete_hook,
)
from yweb.utils import TestCollector

# 全局 TestCollector
tc: TestCollector = None


# ==================== 场景1：DELETE - 订单-订单项（强聚合关系）====================

class OrderModel(BaseModel):
    """订单模型"""
    __tablename__ = "demo_orders"
    __table_args__ = {'extend_existing': True}

    order_no = Column(String(50))
    total_amount = Column(Integer, default=0)
    # order_items 属性由 OrderItemModel 的 backref 自动创建


class OrderItemModel(BaseModel):
    """订单项模型"""
    __tablename__ = "demo_order_items"
    __table_args__ = {'extend_existing': True}

    product_name = Column(String(100))
    quantity = Column(Integer, default=1)
    price = Column(Integer, default=0)

    # DELETE：订单删除时，订单项也被软删除
    order = fields.ManyToOne(OrderModel, on_delete=fields.DELETE)


# ==================== 场景2：DELETE - 文章-评论（一对多级联）====================

class ArticleModel(BaseModel):
    """文章模型"""
    __tablename__ = "demo_articles"
    __table_args__ = {'extend_existing': True}

    title = Column(String(200))
    content = Column(String(2000))
    # comments 属性由 CommentModel 的 backref 自动创建


class CommentModel(BaseModel):
    """评论模型"""
    __tablename__ = "demo_comments"
    __table_args__ = {'extend_existing': True}

    content = Column(String(500))
    author = Column(String(50))

    # DELETE：文章删除时，评论也被软删除
    article = fields.ManyToOne(ArticleModel, on_delete=fields.DELETE)


# ==================== 场景3：SET_NULL - 部门-员工（可选父子关系）====================

class DepartmentModel(BaseModel):
    """部门模型"""
    __tablename__ = "demo_departments"
    __table_args__ = {'extend_existing': True}

    dept_name = Column(String(100))
    # employees 属性由 EmployeeModel 的 backref 自动创建


class EmployeeModel(BaseModel):
    """员工模型"""
    __tablename__ = "demo_employees"
    __table_args__ = {'extend_existing': True}

    emp_name = Column(String(100))

    # SET_NULL：部门删除时，员工的部门ID设为空
    department = fields.ManyToOne(DepartmentModel, on_delete=fields.SET_NULL, nullable=True)


# ==================== 场景4：DO_NOTHING - 项目-标签（松散关系）====================

class ProjectModel(BaseModel):
    """项目模型"""
    __tablename__ = "demo_projects"
    __table_args__ = {'extend_existing': True}

    project_name = Column(String(100))
    # tags 属性由 TagModel 的 backref 自动创建


class TagModel(BaseModel):
    """标签模型"""
    __tablename__ = "demo_tags"
    __table_args__ = {'extend_existing': True}

    tag_name = Column(String(50))

    # DO_NOTHING：项目删除时，标签不做任何处理
    project = fields.ManyToOne(ProjectModel, on_delete=fields.DO_NOTHING, nullable=True)


# ==================== 场景5：PROTECT - 分类-产品（限制删除）====================

class CategoryModel(BaseModel):
    """分类模型"""
    __tablename__ = "demo_categories"
    __table_args__ = {'extend_existing': True}

    category_name = Column(String(100))
    # products 属性由 ProductModel 的 backref 自动创建


class ProductModel(BaseModel):
    """产品模型"""
    __tablename__ = "demo_products"
    __table_args__ = {'extend_existing': True}

    product_name = Column(String(100))

    # PROTECT：有产品时禁止删除分类
    category = fields.ManyToOne(CategoryModel, on_delete=fields.PROTECT, nullable=True)


# ==================== 场景6：UNLINK - 用户-角色（多对多）====================

class RoleModel(BaseModel):
    """角色模型"""
    __tablename__ = "demo_roles"
    __table_args__ = {'extend_existing': True}

    role_name = Column(String(50))
    role_code = Column(String(50))


class UserModel(BaseModel):
    """用户模型"""
    __tablename__ = "demo_users"
    __table_args__ = {'extend_existing': True}

    username = Column(String(50))
    email = Column(String(100))

    # UNLINK：用户删除时，解除与角色的关联
    roles = fields.ManyToMany(
        RoleModel,
        on_delete=fields.UNLINK,
    )


# ==================== 辅助函数 ====================

def print_section(title):
    """打印章节标题"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def print_success(message):
    """打印成功消息"""
    print(f"[OK] {message}")
    if tc:
        tc.check(True, message)


def print_error(message):
    """打印错误消息"""
    print(f"[ERROR] {message}")
    if tc:
        tc.check(False, message)


def print_info(message):
    """打印信息"""
    print(f"[INFO] {message}")


# ==================== 测试场景 ====================

def test_scenario_1_order_cascade_delete():
    """场景1：订单-订单项级联软删除"""
    print_section("场景1：DELETE - 订单-订单项级联软删除")

    # 创建订单
    order = OrderModel(
        order_no="ORD20240101001",
        total_amount=1500,
        name="测试订单",
        code="ORDER_001"
    )
    order.add(True)
    print_success(f"创建订单: ID={order.id}, 订单号={order.order_no}")

    # 通过 relationship.append() 添加订单项
    item1 = OrderItemModel(product_name="iPhone 15", quantity=1, price=1000)
    item2 = OrderItemModel(product_name="AirPods Pro", quantity=1, price=500)
    order.order_items.append(item1)
    order.order_items.append(item2)
    order.save(True)
    print_success(f"添加订单项: {item1.product_name} x{item1.quantity}, {item2.product_name} x{item2.quantity}")

    order_id = order.id
    item1_id = item1.id
    item2_id = item2.id

    # 验证外键自动设置
    print_info(f"订单项1外键: order_id={item1.demo_order_id}")
    print_info(f"订单项2外键: order_id={item2.demo_order_id}")

    # 删除订单
    print_info("删除订单...")
    order.delete(True)

    # 验证级联软删除
    deleted_order = OrderModel.query.execution_options(include_deleted=True).filter_by(id=order_id).first()
    deleted_item1 = OrderItemModel.query.execution_options(include_deleted=True).filter_by(id=item1_id).first()
    deleted_item2 = OrderItemModel.query.execution_options(include_deleted=True).filter_by(id=item2_id).first()

    if deleted_order.is_deleted and deleted_item1.is_deleted and deleted_item2.is_deleted:
        print_success("订单和订单项都被级联软删除")
    else:
        print_error("级联软删除失败")

    # 验证正常查询看不到
    active_orders = OrderModel.query.count()
    active_items = OrderItemModel.query.count()
    print_info(f"正常查询结果: 订单数={active_orders}, 订单项数={active_items}")


def test_scenario_2_article_cascade_delete():
    """场景2：文章-评论级联软删除"""
    print_section("场景2：DELETE - 文章-评论级联软删除")

    # 创建文章
    article = ArticleModel(
        title="测试文章",
        content="这是一篇测试文章",
        name="文章1",
        code="ARTICLE_001"
    )
    article.add(True)
    print_success(f"创建文章: ID={article.id}, 标题={article.title}")

    # 添加评论
    comment1 = CommentModel(content="很好的文章", author="张三")
    comment2 = CommentModel(content="学到了", author="李四")
    comment3 = CommentModel(content="感谢分享", author="王五")

    article.comments.append(comment1)
    article.comments.append(comment2)
    article.comments.append(comment3)
    article.save(True)
    print_success(f"添加评论: 共{len(article.comments)}条")

    article_id = article.id
    comment_ids = [comment1.id, comment2.id, comment3.id]

    # 删除文章
    print_info("删除文章...")
    article.delete(True)

    # 验证级联软删除
    deleted_article = ArticleModel.query.execution_options(include_deleted=True).filter_by(id=article_id).first()
    deleted_comments = [
        CommentModel.query.execution_options(include_deleted=True).filter_by(id=cid).first()
        for cid in comment_ids
    ]

    if deleted_article.is_deleted and all(c.is_deleted for c in deleted_comments):
        print_success("文章和所有评论都被级联软删除")
    else:
        print_error("级联软删除失败")

    # 验证正常查询看不到
    active_articles = ArticleModel.query.count()
    active_comments = CommentModel.query.count()
    print_info(f"正常查询结果: 文章数={active_articles}, 评论数={active_comments}")


def test_scenario_3_department_clear_fk():
    """场景3：部门-员工清空外键"""
    print_section("场景3：SET_NULL - 部门-员工清空外键")

    # 创建部门
    dept = DepartmentModel(
        dept_name="技术部",
        name="部门1",
        code="DEPT_001"
    )
    dept.add(True)
    print_success(f"创建部门: ID={dept.id}, 名称={dept.dept_name}")

    # 添加员工
    emp1 = EmployeeModel(emp_name="张三", name="员工1", code="EMP_001")
    emp2 = EmployeeModel(emp_name="李四", name="员工2", code="EMP_002")
    emp3 = EmployeeModel(emp_name="王五", name="员工3", code="EMP_003")

    dept.employees.append(emp1)
    dept.employees.append(emp2)
    dept.employees.append(emp3)
    dept.save(True)
    print_success(f"添加员工: 共{len(dept.employees)}人")

    dept_id = dept.id
    emp_ids = [emp1.id, emp2.id, emp3.id]

    # 验证外键已设置
    print_info(f"员工1外键: department_id={emp1.demo_department_id}")
    print_info(f"员工2外键: department_id={emp2.demo_department_id}")
    print_info(f"员工3外键: department_id={emp3.demo_department_id}")

    # 删除部门
    print_info("删除部门...")
    dept.delete(True)

    # 验证部门被软删除
    deleted_dept = DepartmentModel.query.execution_options(include_deleted=True).filter_by(id=dept_id).first()
    if deleted_dept.is_deleted:
        print_success("部门被软删除")
    else:
        print_error("部门删除失败")

    # 验证员工的部门ID被清空
    employees = [EmployeeModel.query.filter_by(id=eid).first() for eid in emp_ids]
    if all(emp.demo_department_id is None for emp in employees):
        print_success("所有员工的部门ID被清空")
    else:
        print_error("外键清空失败")

    # 验证员工未被删除
    if all(not emp.is_deleted for emp in employees):
        print_success("员工未被删除")
    else:
        print_error("员工被错误删除")

    print_info(f"正常查询结果: 员工数={EmployeeModel.query.count()}")


def test_scenario_4_project_ignore():
    """场景4：项目-标签不处理"""
    print_section("场景4：DO_NOTHING - 项目-标签不处理")

    # 创建项目
    project = ProjectModel(
        project_name="项目A",
        name="项目1",
        code="PROJ_001"
    )
    project.add(True)
    print_success(f"创建项目: ID={project.id}, 名称={project.project_name}")

    # 添加标签
    tag1 = TagModel(tag_name="Python", name="标签1", code="TAG_001")
    tag2 = TagModel(tag_name="Django", name="标签2", code="TAG_002")

    project.tags.append(tag1)
    project.tags.append(tag2)
    project.save(True)
    print_success(f"添加标签: {tag1.tag_name}, {tag2.tag_name}")

    project_id = project.id
    tag1_id = tag1.id
    tag2_id = tag2.id

    # 验证外键已设置
    print_info(f"标签1外键: project_id={tag1.demo_project_id}")
    print_info(f"标签2外键: project_id={tag2.demo_project_id}")

    # 删除项目
    print_info("删除项目...")
    project.delete(True)

    # 验证项目被软删除
    deleted_project = ProjectModel.query.execution_options(include_deleted=True).filter_by(id=project_id).first()
    if deleted_project.is_deleted:
        print_success("项目被软删除")
    else:
        print_error("项目删除失败")

    # 验证标签保持不变
    tag1_check = TagModel.query.filter_by(id=tag1_id).first()
    tag2_check = TagModel.query.filter_by(id=tag2_id).first()

    if tag1_check and tag2_check:
        print_success("标签仍然存在")
    else:
        print_error("标签被错误删除")

    if tag1_check.demo_project_id == project_id and tag2_check.demo_project_id == project_id:
        print_success("标签的外键保持不变")
    else:
        print_error("标签的外键被修改")

    if not tag1_check.is_deleted and not tag2_check.is_deleted:
        print_success("标签未被删除")
    else:
        print_error("标签被错误删除")

    print_info(f"正常查询结果: 标签数={TagModel.query.count()}")


def test_scenario_5_category_protect():
    """场景5：分类-产品限制删除"""
    print_section("场景5：PROTECT - 分类-产品限制删除")

    # 创建分类
    category = CategoryModel(
        category_name="电子产品",
        name="分类1",
        code="CAT_001"
    )
    category.add(True)
    print_success(f"创建分类: ID={category.id}, 名称={category.category_name}")

    # 添加产品
    product = ProductModel(
        product_name="iPhone",
        name="产品1",
        code="PROD_001"
    )
    category.products.append(product)
    category.save(True)
    print_success(f"添加产品: {product.product_name}")

    category_id = category.id
    product_id = product.id

    # 尝试删除有产品的分类
    print_info("尝试删除有产品的分类...")
    exception_caught = False
    try:
        category.delete(True)
        print_error("没有抛出异常！分类被删除了")
    except ValueError as e:
        exception_caught = True
        print_success(f"捕获到 ValueError: {e}")
    except Exception as e:
        exception_caught = True
        print_success(f"捕获到异常 {type(e).__name__}: {e}")

    if exception_caught:
        # 回滚 session
        from sqlalchemy.orm import object_session
        session = object_session(category)
        if session:
            session.rollback()

        # 检查状态
        category_check = CategoryModel.query.execution_options(include_deleted=True).filter_by(id=category_id).first()
        product_check = ProductModel.query.execution_options(include_deleted=True).filter_by(id=product_id).first()

        if category_check and not category_check.is_deleted:
            print_success(f"分类未被删除 (is_deleted={category_check.is_deleted})")
        else:
            print_error("分类被错误删除")

        if product_check and not product_check.is_deleted:
            print_success(f"产品未被删除 (is_deleted={product_check.is_deleted})")
        else:
            print_error("产品被错误删除")

    # 测试删除空分类
    print_info("\n测试删除空分类...")
    empty_category = CategoryModel(
        category_name="图书",
        name="分类2",
        code="CAT_002"
    )
    empty_category.add(True)
    print_success(f"创建空分类: ID={empty_category.id}")

    empty_category_id = empty_category.id
    empty_category.delete(True)

    deleted_empty_category = CategoryModel.query.execution_options(include_deleted=True).filter_by(id=empty_category_id).first()
    if deleted_empty_category.is_deleted:
        print_success("空分类被成功删除")
    else:
        print_error("空分类删除失败")


def test_scenario_6_user_unlink():
    """场景6：用户-角色解除关联"""
    print_section("场景6：UNLINK - 用户-角色解除关联")

    # 创建角色
    role_admin = RoleModel(
        role_name="管理员",
        role_code="ADMIN",
        name="角色1",
        code="ROLE_001"
    )
    role_user = RoleModel(
        role_name="普通用户",
        role_code="USER",
        name="角色2",
        code="ROLE_002"
    )
    RoleModel.add_all([role_admin, role_user], commit=True)
    print_success(f"创建角色: {role_admin.role_name}, {role_user.role_name}")

    # 创建用户并关联角色
    user = UserModel(
        username="zhangsan",
        email="zhangsan@example.com",
        name="用户1",
        code="USER_001"
    )
    user.roles.append(role_admin)
    user.roles.append(role_user)
    user.add(True)
    print_success(f"创建用户: {user.username}, 关联{len(user.roles)}个角色")

    user_id = user.id
    role_admin_id = role_admin.id
    role_user_id = role_user.id

    # 删除用户
    print_info("删除用户...")
    user.delete(True)

    # 验证用户被软删除
    deleted_user = UserModel.query.execution_options(include_deleted=True).filter_by(id=user_id).first()
    if deleted_user.is_deleted:
        print_success("用户被软删除")
    else:
        print_error("用户删除失败")

    # 验证角色未被删除
    role_admin_check = RoleModel.query.filter_by(id=role_admin_id).first()
    role_user_check = RoleModel.query.filter_by(id=role_user_id).first()

    if role_admin_check and role_user_check:
        print_success("角色仍然存在")
    else:
        print_error("角色被错误删除")

    if not role_admin_check.is_deleted and not role_user_check.is_deleted:
        print_success("角色未被删除")
    else:
        print_error("角色被错误删除")

    print_info(f"正常查询结果: 角色数={RoleModel.query.count()}")

    # 测试多用户共享角色
    print_info("\n测试多用户共享角色...")
    role_editor = RoleModel(
        role_name="编辑",
        role_code="EDITOR",
        name="角色3",
        code="ROLE_003"
    )
    role_editor.add(True)

    user1 = UserModel(username="user1", email="user1@example.com", name="用户2", code="USER_002")
    user2 = UserModel(username="user2", email="user2@example.com", name="用户3", code="USER_003")

    user1.roles.append(role_editor)
    user2.roles.append(role_editor)

    UserModel.add_all([user1, user2], commit=True)
    print_success(f"创建两个用户，都关联到角色: {role_editor.role_name}")

    user1_id = user1.id
    user2_id = user2.id
    role_editor_id = role_editor.id

    # 删除 user1
    print_info("删除 user1...")
    user1.delete(True)

    # 验证 user1 被软删除
    deleted_user1 = UserModel.query.execution_options(include_deleted=True).filter_by(id=user1_id).first()
    if deleted_user1.is_deleted:
        print_success("user1 被软删除")
    else:
        print_error("user1 删除失败")

    # 验证 user2 和角色都未受影响
    user2_check = UserModel.query.filter_by(id=user2_id).first()
    role_editor_check = RoleModel.query.filter_by(id=role_editor_id).first()

    if user2_check and not user2_check.is_deleted:
        print_success("user2 未受影响")
    else:
        print_error("user2 被错误影响")

    if role_editor_check and not role_editor_check.is_deleted:
        print_success("角色未受影响")
    else:
        print_error("角色被错误影响")

    if len(user2_check.roles) == 1:
        print_success("user2 仍然关联着角色")
    else:
        print_error("user2 的角色关联被错误修改")


# ==================== 主函数 ====================

def main():
    """主函数"""
    global tc
    tc = TestCollector(title="级联软删除完整测试")
    
    print("\n" + "="*60)
    print("  级联软删除完整测试脚本")
    print("="*60)

    # 初始化
    print_info("初始化数据库...")
    activate_soft_delete_hook()
    configure_cascade_soft_delete()

    # 初始化数据库（使用SQLite文件数据库）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, "demo_cascade_all_scenarios.db")
    engine, session_scope = init_database(f"sqlite:///{db_path}", echo=False)

    CoreModel.query = session_scope.query_property()

    # 清空并重建数据表
    print_info("清空并重建数据表...")
    BaseModel.metadata.drop_all(engine)
    BaseModel.metadata.create_all(engine)

    print_success("数据库初始化完成")

    # 运行所有测试场景
    try:
        test_scenario_1_order_cascade_delete()
        test_scenario_2_article_cascade_delete()
        test_scenario_3_department_clear_fk()
        test_scenario_4_project_ignore()
        test_scenario_5_category_protect()
        test_scenario_6_user_unlink()

        print_section("所有测试场景执行完成")
        print_success("测试脚本运行成功！")

    except Exception as e:
        tc.check(False, f"测试过程中发生错误: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

    finally:
        session_scope.remove()
        print_info(f"\n数据库文件保存在: {db_path}")
    
    # 输出测试汇总
    return tc.summary()


if __name__ == "__main__":
    main()
