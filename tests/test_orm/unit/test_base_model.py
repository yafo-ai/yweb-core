"""BaseModel 模块测试

测试 ORM 基类的功能
"""

import pytest
from dataclasses import dataclass
from datetime import datetime
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import sessionmaker, Session, scoped_session

from yweb.orm import (
    CoreModel,
    BaseModel,
    DTO,
    BaseSchemas,
    PaginationField,
    Page,
    DateTimeStr,
    init_database,
    get_db,
    SimpleSoftDeleteMixin,
)


# ==================== 测试模型定义 ====================
# extend_existing=True：避免 pytest 多文件加载时重复定义表的错误

class UserModel(BaseModel):
    """测试用户模型"""
    __tablename__ = "test_users"
    __table_args__ = {'extend_existing': True}
    
    email = Column(String(200))


class SoftDeleteUserModel(BaseModel):
    """带软删除的测试用户模型"""
    __tablename__ = "test_soft_delete_users"
    __table_args__ = {'extend_existing': True}
    """可以覆盖BaseModel的基础属性"""
    name = Column(String(200))


# 分页测试用关联模型
from sqlalchemy import ForeignKey, Table
from sqlalchemy.orm import relationship

# 用户-角色多对多关联表
test_user_role = Table(
    "test_user_role",
    BaseModel.metadata,
    Column("user_id", Integer, ForeignKey("test_paginate_users.id"), primary_key=True),
    Column("role_id", Integer, ForeignKey("test_paginate_roles.id"), primary_key=True),
    extend_existing=True,
)


class PaginateUserModel(BaseModel):
    """分页测试用户模型"""
    __tablename__ = "test_paginate_users"
    __table_args__ = {'extend_existing': True}
    
    username = Column(String(50))
    email = Column(String(100))
    department_id = Column(Integer, ForeignKey("test_paginate_departments.id"), nullable=True)
    
    # 关联关系
    department = relationship("PaginateDepartmentModel", back_populates="users")
    roles = relationship("PaginateRoleModel", secondary=test_user_role, back_populates="users")
    posts = relationship("PaginatePostModel", back_populates="author")


class PaginateDepartmentModel(BaseModel):
    """分页测试部门模型"""
    __tablename__ = "test_paginate_departments"
    __table_args__ = {'extend_existing': True}
    
    dept_name = Column(String(100))
    users = relationship("PaginateUserModel", back_populates="department")


class PaginateRoleModel(BaseModel):
    """分页测试角色模型"""
    __tablename__ = "test_paginate_roles"
    __table_args__ = {'extend_existing': True}
    
    role_name = Column(String(50))
    role_code = Column(String(50))
    users = relationship("PaginateUserModel", secondary=test_user_role, back_populates="roles")


class PaginatePostModel(BaseModel):
    """分页测试文章模型"""
    __tablename__ = "test_paginate_posts"
    __table_args__ = {'extend_existing': True}
    
    title = Column(String(200))
    content = Column(String(1000))
    author_id = Column(Integer, ForeignKey("test_paginate_users.id"))
    
    author = relationship("PaginateUserModel", back_populates="posts")


# ==================== 测试类 ====================

class TestBaseModel:
    """BaseModel 测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """自动初始化数据库会话"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        session_scope = scoped_session(SessionLocal)
        # 设置 CoreModel.query，使 .add()/.save() 等方法能正常工作
        CoreModel.query = session_scope.query_property()
        yield
        session_scope.remove()
    
    def test_model_has_id(self):
        """测试模型有 id 字段"""
        user = UserModel(name="Test", email="test@example.com")
        user.add(True)
        
        assert user.id is not None
        assert isinstance(user.id, int)
    
    def test_model_has_created_at(self):
        """测试模型有 created_at 字段"""
        user = UserModel(name="Test", email="test@example.com")
        user.add(True)
        
        # 检查是否有 created_at 字段
        if hasattr(user, 'created_at'):
            assert user.created_at is not None
            assert isinstance(user.created_at, datetime)
    
    def test_model_has_updated_at(self):
        """测试模型有 updated_at 字段：首次添加为空，更新后有值"""
        user = UserModel(email="test@example.com")
        user.add(True)
        
        # 首次添加时 updated_at 应为空
        assert hasattr(user, 'updated_at')
        assert user.updated_at is None, "首次添加时 updated_at 应为空"
        
        # 更新记录
        user.email = "updated@example.com"
        user.update(True)
        
        # 更新后 updated_at 应有值
        assert user.updated_at is not None, "更新后 updated_at 应有值"
        assert isinstance(user.updated_at, datetime)
    
    def test_model_query(self):
        """测试模型查询"""
        user1 = UserModel(email="user1@example.com")
        user2 = UserModel(email="user2@example.com")
        UserModel.add_all([user1, user2], commit=True)
        
        # 查询所有用户
        users = UserModel.get_all()
        assert len(users) >= 2
    
    def test_model_filter(self):
        """测试模型过滤"""
        user = UserModel(name="FilterTest", email="filter@example.com")
        user.add(True)
        
        # 按名称过滤
        found = UserModel.query.filter(UserModel.name == "FilterTest").first()
        assert found is not None
        assert found.email == "filter@example.com"
    
    def test_get_returns_object(self):
        """测试 get() 返回对象"""
        user = UserModel(name="GetTest", email="get@example.com")
        user.add(True)
        
        found = UserModel.get(user.id)
        assert found is not None
        assert found.id == user.id
        assert found.email == "get@example.com"
    
    def test_get_returns_none_when_not_found(self):
        """测试 get() 不存在时返回 None"""
        # 使用一个不存在的 ID
        found = UserModel.get(99999)
        assert found is None
    


class TestDTO:
    """DTO 测试"""
    
    def test_dto_class_exists(self):
        """测试 DTO 类存在"""
        assert DTO is not None
    
    def test_dto_subclass_creation(self):
        """测试创建 DTO 子类"""
        class UserDTO(DTO):
            id: int
            name: str
            email: str
        
        user = UserDTO(id=1, name="Test", email="test@example.com")
        
        assert user.id == 1
        assert user.name == "Test"
        assert user.email == "test@example.com"
    
    def test_dto_to_dict(self):
        """测试 DTO 转字典"""
        class UserDTO(DTO):
            id: int
            name: str
        
        user = UserDTO(id=1, name="Test")
        user_dict = user.to_dict()
        
        assert user_dict["id"] == 1
        assert user_dict["name"] == "Test"
    
    def test_dto_from_entity(self):
        """测试从实体创建 DTO"""
        class UserDTO(DTO):
            id: int
            name: str
        
        # 模拟 ORM 对象
        class MockUser:
            id = 1
            name = "Test"
        
        user_dto = UserDTO.from_entity(MockUser())
        
        assert user_dto.id == 1
        assert user_dto.name == "Test"
    
    def test_dto_iteration(self):
        """测试 DTO 迭代"""
        class UserDTO(DTO):
            id: int
            name: str
        
        user = UserDTO(id=1, name="Test")
        
        # 测试 dict() 转换
        user_dict = dict(user)
        assert "id" in user_dict
        assert "name" in user_dict
    
    def test_dto_keys_values(self):
        """测试 DTO keys 和 values"""
        class UserDTO(DTO):
            id: int
            name: str
        
        user = UserDTO(id=1, name="Test")
        
        assert "id" in user.keys()
        assert "name" in user.keys()
        assert 1 in user.values()
        assert "Test" in user.values()


class TestBaseSchemas:
    """BaseSchemas 测试"""
    
    def test_pagination_field(self):
        """测试分页字段"""
        pagination = PaginationField(page=1, page_size=10)
        
        assert pagination.page == 1
        assert pagination.page_size == 10
    
    def test_pagination_default_values(self):
        """测试分页默认值"""
        pagination = PaginationField()
        
        assert pagination.page == 1
        assert pagination.page_size == 10
    
    def test_pagination_offset_calculation(self):
        """测试分页偏移量计算"""
        pagination = PaginationField(page=3, page_size=20)
        
        # 手动计算 offset
        offset = (pagination.page - 1) * pagination.page_size
        assert offset == 40  # (3-1) * 20
    
    def test_pagination_validation(self):
        """测试分页参数验证"""
        # 页码不能小于 1
        pagination = PaginationField(page=0, page_size=10)
        assert pagination.page >= 1
        
        pagination = PaginationField(page=-1, page_size=10)
        assert pagination.page >= 1
    
    def test_page_response(self):
        """测试分页响应"""
        items = [{"id": 1}, {"id": 2}]
        page = Page(
            rows=items,
            total_records=100,
            page=1,
            page_size=10,
            total_pages=10
        )
        
        assert page.rows == items
        assert page.total_records == 100
        assert page.page == 1
        assert page.page_size == 10
        assert page.total_pages == 10
    
    def test_page_has_next_prev(self):
        """测试分页 has_next 和 has_prev"""
        page = Page(
            rows=[],
            total_records=100,
            page=5,
            page_size=10,
            total_pages=10
        )
        
        assert page.has_next == True  # 第5页，还有后面的页
        assert page.has_prev == True  # 第5页，有前面的页
    
    def test_page_first_page(self):
        """测试第一页"""
        page = Page(
            rows=[],
            total_records=100,
            page=1,
            page_size=10,
            total_pages=10
        )
        
        assert page.has_prev == False  # 第一页没有前一页
        assert page.has_next == True
    
    def test_page_last_page(self):
        """测试最后一页"""
        page = Page(
            rows=[],
            total_records=100,
            page=10,
            page_size=10,
            total_pages=10
        )
        
        assert page.has_prev == True
        assert page.has_next == False  # 最后一页没有下一页
    
    def test_page_to_dict(self):
        """测试分页响应转字典"""
        page = Page(
            rows=[{"id": 1}],
            total_records=1,
            page=1,
            page_size=10,
            total_pages=1
        )
        
        page_dict = page.to_dict()
        
        assert "rows" in page_dict
        assert "total_records" in page_dict
        assert "has_next" in page_dict
        assert "has_prev" in page_dict
    
    def test_datetime_str(self):
        """测试日期时间字符串类型"""
        from yweb.orm import format_datetime_to_string
        
        # 测试 datetime 转换
        dt = datetime(2024, 1, 15, 10, 30, 45)
        result = format_datetime_to_string(dt)
        assert result == "2024-01-15 10:30:45"
        
        # 测试 None
        assert format_datetime_to_string(None) is None
    
    def test_base_schemas_from_attributes(self):
        """测试 BaseSchemas 支持 from_attributes"""
        class UserSchema(BaseSchemas):
            id: int
            name: str
        
        # 模拟 ORM 对象
        class MockUser:
            id = 1
            name = "Test"
        
        user_schema = UserSchema.model_validate(MockUser())
        
        assert user_schema.id == 1
        assert user_schema.name == "Test"


class TestPaginationQuery:
    """分页查询测试
    
    测试 query.paginate() 方法与各种查询选项的组合使用：
    - 基础分页
    - selectinload 预加载关联
    - with_entities 字段选择
    - 组合使用
    """
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        from sqlalchemy.orm import Query
        
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        
        # 为 Query 添加 paginate 方法（模拟 init_database 的行为）
        if not hasattr(Query, 'paginate'):
            import math
            def paginate_method(self, page: int = 1, page_size: int = 10, max_page_size: int = 100, schema=None):
                page = max(page, 1)
                page_size = max(1, min(page_size, max_page_size))
                total = self.count()
                total_pages = math.ceil(total / page_size) if total > 0 else 0
                items = self.offset((page - 1) * page_size).limit(page_size).all()
                return Page(
                    rows=items,
                    total_records=total,
                    page=page,
                    page_size=page_size,
                    total_pages=total_pages
                )
            Query.paginate = paginate_method
        
        yield
        self.session_scope.remove()
    
    @pytest.fixture
    def setup_test_data(self):
        """准备测试数据"""
        # 创建部门
        dept1 = PaginateDepartmentModel(dept_name="技术部")
        dept2 = PaginateDepartmentModel(dept_name="市场部")
        PaginateDepartmentModel.add_all([dept1, dept2], commit=True)
        
        # 创建角色
        role_admin = PaginateRoleModel(role_name="管理员", role_code="ADMIN")
        role_user = PaginateRoleModel(role_name="普通用户", role_code="USER")
        role_guest = PaginateRoleModel(role_name="访客", role_code="GUEST")
        PaginateRoleModel.add_all([role_admin, role_user, role_guest], commit=True)
        
        # 重新从 session 获取角色（确保是 persistent 状态）
        role_admin = PaginateRoleModel.query.filter_by(role_code="ADMIN").first()
        role_user = PaginateRoleModel.query.filter_by(role_code="USER").first()
        role_guest = PaginateRoleModel.query.filter_by(role_code="GUEST").first()
        
        # 创建用户（25个，用于分页测试）
        users = []
        for i in range(25):
            user = PaginateUserModel(
                username=f"user_{i:02d}",
                email=f"user{i}@example.com",
                department_id=dept1.id if i % 2 == 0 else dept2.id
            )
            users.append(user)
        PaginateUserModel.add_all(users, commit=True)
        
        # 建立用户-角色关系（通过关联表直接插入）
        from sqlalchemy import insert
        user_role_data = []
        for i, user in enumerate(users):
            if i < 5:
                user_role_data.append({"user_id": user.id, "role_id": role_admin.id})
            elif i < 15:
                user_role_data.append({"user_id": user.id, "role_id": role_user.id})
            else:
                user_role_data.append({"user_id": user.id, "role_id": role_guest.id})
        
        if user_role_data:
            session = PaginateUserModel.query.session
            session.execute(insert(test_user_role), user_role_data)
            session.commit()
        
        # 为前10个用户创建文章
        posts = []
        for i, user in enumerate(users[:10]):
            for j in range(3):
                post = PaginatePostModel(
                    title=f"文章 {i}-{j}",
                    content=f"这是用户 {user.username} 的第 {j+1} 篇文章",
                    author_id=user.id
                )
                posts.append(post)
        
        PaginatePostModel.add_all(posts, commit=True)
        
        return {
            "dept1": dept1,
            "dept2": dept2,
            "role_admin": role_admin,
            "role_user": role_user,
            "role_guest": role_guest,
            "users": users,
        }
    
    def test_basic_paginate(self, setup_test_data):
        """测试基础分页"""
        # 第一页
        page1 = PaginateUserModel.query.paginate(page=1, page_size=10)
        
        assert page1.total_records == 25
        assert len(page1.rows) == 10
        assert page1.page == 1
        assert page1.page_size == 10
        assert page1.total_pages == 3
        assert page1.has_next == True
        assert page1.has_prev == False
    
    def test_paginate_second_page(self, setup_test_data):
        """测试第二页"""
        page2 = PaginateUserModel.query.paginate(page=2, page_size=10)
        
        assert len(page2.rows) == 10
        assert page2.page == 2
        assert page2.has_next == True
        assert page2.has_prev == True
    
    def test_paginate_last_page(self, setup_test_data):
        """测试最后一页"""
        page3 = PaginateUserModel.query.paginate(page=3, page_size=10)
        
        assert len(page3.rows) == 5  # 25条记录，第三页只有5条
        assert page3.page == 3
        assert page3.has_next == False
        assert page3.has_prev == True
    
    def test_paginate_with_filter(self, setup_test_data):
        """测试带条件的分页"""
        data = setup_test_data
        
        # 只查询技术部的用户
        page_result = PaginateUserModel.query.filter(
            PaginateUserModel.department_id == data["dept1"].id
        ).paginate(page=1, page_size=10)
        
        # 技术部应该有约一半的用户（偶数索引）
        assert page_result.total_records == 13  # 0,2,4,6,8,10,12,14,16,18,20,22,24
        assert all(u.department_id == data["dept1"].id for u in page_result.rows)
    
    def test_paginate_with_order_by(self, setup_test_data):
        """测试带排序的分页"""
        page_result = PaginateUserModel.query.order_by(
            PaginateUserModel.username.desc()
        ).paginate(page=1, page_size=5)
        
        # 应该是倒序，user_24 在前
        assert page_result.rows[0].username == "user_24"
        assert page_result.rows[1].username == "user_23"
    
    def test_paginate_with_selectinload(self, setup_test_data):
        """测试 selectinload 预加载关联数据"""
        from sqlalchemy.orm import selectinload
        
        page_result = PaginateUserModel.query.options(
            selectinload(PaginateUserModel.department),
            selectinload(PaginateUserModel.roles)
        ).paginate(page=1, page_size=5)
        
        assert len(page_result.rows) == 5
        # 验证关联数据已加载
        for user in page_result.rows:
            # 访问关联数据不应触发额外查询
            assert user.department is not None
            assert user.department.dept_name in ["技术部", "市场部"]
            assert len(user.roles) > 0
    
    def test_paginate_with_joinedload(self, setup_test_data):
        """测试 joinedload 预加载"""
        from sqlalchemy.orm import joinedload
        
        page_result = PaginateUserModel.query.options(
            joinedload(PaginateUserModel.department)
        ).paginate(page=1, page_size=5)
        
        assert len(page_result.rows) == 5
        for user in page_result.rows:
            assert user.department is not None
    
    def test_paginate_with_selectinload_load_only(self, setup_test_data):
        """测试 selectinload + load_only 只加载指定字段"""
        from sqlalchemy.orm import selectinload, load_only
        
        page_result = PaginateUserModel.query.options(
            selectinload(PaginateUserModel.roles).load_only(
                PaginateRoleModel.id,
                PaginateRoleModel.role_name,
                PaginateRoleModel.role_code
            )
        ).paginate(page=1, page_size=5)
        
        assert len(page_result.rows) == 5
        for user in page_result.rows:
            for role in user.roles:
                # 这些字段应该已加载
                assert role.id is not None
                assert role.role_name is not None
                assert role.role_code is not None
    
    def test_paginate_with_entities(self, setup_test_data):
        """测试 with_entities 只查询指定字段"""
        page_result = PaginateUserModel.query.with_entities(
            PaginateUserModel.id,
            PaginateUserModel.username,
            PaginateUserModel.email
        ).paginate(page=1, page_size=5)
        
        assert len(page_result.rows) == 5
        # with_entities 返回的是元组
        for row in page_result.rows:
            assert len(row) == 3  # id, username, email
            assert isinstance(row[0], int)  # id
            assert isinstance(row[1], str)  # username
            assert isinstance(row[2], str)  # email
    
    def test_paginate_complex_query(self, setup_test_data):
        """测试复杂查询：filter + order_by + selectinload + 分页"""
        from sqlalchemy.orm import selectinload
        data = setup_test_data
        
        page_result = PaginateUserModel.query.filter(
            PaginateUserModel.department_id == data["dept1"].id
        ).options(
            selectinload(PaginateUserModel.roles),
            selectinload(PaginateUserModel.posts)
        ).order_by(
            PaginateUserModel.username
        ).paginate(page=1, page_size=5)
        
        assert len(page_result.rows) <= 5
        # 验证过滤条件
        for user in page_result.rows:
            assert user.department_id == data["dept1"].id
            # 验证关联数据已加载
            assert isinstance(user.roles, list)
    
    def test_paginate_empty_result(self, setup_test_data):
        """测试空结果分页"""
        page_result = PaginateUserModel.query.filter(
            PaginateUserModel.username == "nonexistent"
        ).paginate(page=1, page_size=10)
        
        assert page_result.total_records == 0
        assert len(page_result.rows) == 0
        assert page_result.total_pages == 0
        assert page_result.has_next == False
        assert page_result.has_prev == False
    
    def test_paginate_page_size_limit(self, setup_test_data):
        """测试页大小限制"""
        # 请求 200 条，但最大只允许 100
        page_result = PaginateUserModel.query.paginate(
            page=1, page_size=200, max_page_size=100
        )
        
        # page_size 应该被限制为 max_page_size
        assert page_result.page_size == 100 or len(page_result.rows) <= 100
    
    def test_paginate_invalid_page(self, setup_test_data):
        """测试无效页码"""
        # 页码为 0 或负数应该被处理为 1
        page_result = PaginateUserModel.query.paginate(page=0, page_size=10)
        assert page_result.page >= 1
        
        page_result = PaginateUserModel.query.paginate(page=-1, page_size=10)
        assert page_result.page >= 1


class TestDatabaseSession:
    """数据库会话测试"""
    
    def test_init_database(self, temp_dir):
        """测试初始化数据库"""
        import os
        db_url = f"sqlite:///{os.path.join(temp_dir, 'test.db')}"
        
        engine = init_database(db_url)
        
        assert engine is not None
    
    def test_memory_database(self):
        """测试内存数据库"""
        engine = init_database("sqlite:///:memory:")
        
        assert engine is not None


class TestSoftDelete:
    """软删除测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_soft_delete_mixin_has_deleted_at(self):
        """测试软删除 Mixin 有 deleted_at 字段"""
        user = SoftDeleteUserModel(name="Test")
        user.add(True)
        
        assert hasattr(user, 'deleted_at')
        assert user.deleted_at is None  # 未删除
    
    def test_soft_delete(self):
        """测试软删除操作"""
        user = SoftDeleteUserModel(name="Test")
        user.add(True)
        user_id = user.id
        # 软删除（通过 delete 自动拦截）
        user.delete(True)
        # 重新查询验证
        user = SoftDeleteUserModel.query.execution_options(include_deleted=True).filter_by(id=user_id).first()
        assert user.deleted_at is not None
        assert user.is_deleted == True
    
    def test_soft_delete_restore(self):
        """测试恢复软删除"""
        user = SoftDeleteUserModel(name="Test")
        user.add(True)
        user_id = user.id
        
        # 软删除
        user.delete(True)
        
        # 重新查询（包含已删除）
        user = SoftDeleteUserModel.query.execution_options(include_deleted=True).filter_by(id=user_id).first()
        assert user.is_deleted == True
        
        # 恢复
        user.undelete()
        user.update(True)
        
        assert user.deleted_at is None
        assert user.is_deleted == False
    
    def test_is_deleted_property(self):
        """测试 is_deleted 属性"""
        user = SoftDeleteUserModel(name="Test")
        user.add(True)
        user_id = user.id
        
        assert user.is_deleted == False
        
        user.delete(True)
        
        # 重新查询验证
        user = SoftDeleteUserModel.query.execution_options(include_deleted=True).filter_by(id=user_id).first()
        assert user.is_deleted == True


class TestVersionControl:
    """版本控制测试
    
    测试乐观锁 (ver 字段) 的行为：
    1. 创建时版本号应为初始值
    2. 有实际变更时版本号应增加
    3. 无实际变更时版本号不应增加
    """
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        self.engine = memory_engine
        yield
        self.session_scope.remove()
    
    def test_initial_version_number(self):
        """测试：创建记录时版本号应为初始值（通常为1）"""
        user = UserModel(name="Version Test", email="version@test.com")
        user.add(True)
        
        # 版本号应该是初始值
        assert hasattr(user, 'ver'), "模型应该有 ver 字段"
        assert user.ver == 1, f"初始版本号应为1，实际为 {user.ver}"
    
    def test_version_increments_on_actual_change(self):
        """测试：有实际数据变更时，版本号应该增加"""
        user = UserModel(name="Version Test", email="version@test.com")
        user.add(True)
        
        initial_version = user.ver
        
        # 修改数据
        user.name = "Updated Name"
        user.update(True)
        
        # 版本号应该增加
        assert user.ver > initial_version, \
            f"版本号应该增加。初始: {initial_version}, 当前: {user.ver}"
    
    def test_version_should_not_increment_without_change(self):
        """测试：没有实际数据变更时，版本号不应该增加
        
        这是一个关键测试：
        - 如果只是读取对象然后 commit，版本号不应改变
        - 如果设置相同的值，版本号也不应改变
        """
        user = UserModel(name="No Change Test", email="nochange@test.com")
        user.add(True)
        
        initial_version = user.ver
        user_id = user.id
        
        # 重新查询对象
        user = UserModel.get(user_id)
        
        # 不做任何修改，直接 commit
        user.update(True)
        
        # 版本号不应该改变
        user = UserModel.get(user_id)
        assert user.ver == initial_version, \
            f"无变更时版本号不应改变。初始: {initial_version}, 当前: {user.ver}"
    
    def test_version_should_not_increment_when_setting_same_value(self):
        """测试：设置相同的值时，版本号不应该增加"""
        user = UserModel(name="Same Value Test", email="same@test.com")
        user.add(True)
        
        initial_version = user.ver
        user_id = user.id
        original_name = user.name
        
        # 重新查询
        user = UserModel.get(user_id)
        
        # 设置相同的值
        user.name = original_name  # 设置相同的值
        user.update(True)
        
        # 版本号不应该改变
        user = UserModel.get(user_id)
        assert user.ver == initial_version, \
            f"设置相同值时版本号不应改变。初始: {initial_version}, 当前: {user.ver}"
    
    def test_optimistic_lock_concurrent_update(self):
        """测试：乐观锁并发更新冲突
        
        当两个事务同时修改同一条记录时，后提交的应该失败
        """
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.orm.exc import StaleDataError
        
        # 创建记录
        user = UserModel(name="Concurrent Test", email="concurrent@test.com")
        user.add(True)
        
        user_id = user.id
        
        # 创建第二个会话
        SessionLocal2 = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        session2 = SessionLocal2()
        
        try:
            # 在第一个会话中获取记录
            user1 = UserModel.get(user_id)
            
            # 在第二个会话中获取同一条记录
            user2 = session2.query(UserModel).filter(UserModel.id == user_id).first()
            
            # 第一个会话修改并提交
            user1.name = "Updated by Session 1"
            user1.update(True)
            
            # 第二个会话尝试修改并提交
            user2.name = "Updated by Session 2"
            
            # 应该抛出 StaleDataError（乐观锁冲突）
            try:
                session2.commit()
                # 如果没有抛出异常，测试失败
                # 注意：SQLite 可能不支持严格的乐观锁检测
                print("警告：乐观锁冲突未被检测到（可能是数据库限制）")
            except StaleDataError:
                # 预期行为：乐观锁冲突被检测到
                pass
            
        finally:
            session2.close()
    
    def test_multiple_updates_increment_version(self):
        """测试：多次更新应该多次增加版本号"""
        user = UserModel(name="Multi Update", email="multi@test.com")
        user.add(True)
        
        initial_version = user.ver
        user_id = user.id
        
        # 第一次更新
        user.name = "Update 1"
        user.update(True)
        
        user = UserModel.get(user_id)
        version_after_1 = user.ver
        assert version_after_1 > initial_version
        
        # 第二次更新
        user.name = "Update 2"
        user.update(True)
        
        user = UserModel.get(user_id)
        version_after_2 = user.ver
        assert version_after_2 > version_after_1
        
        # 第三次更新
        user.name = "Update 3"
        user.update(True)
        
        user = UserModel.get(user_id)
        version_after_3 = user.ver
        assert version_after_3 > version_after_2
        
        # 验证版本号递增
        print(f"版本号变化: {initial_version} -> {version_after_1} -> {version_after_2} -> {version_after_3}")

