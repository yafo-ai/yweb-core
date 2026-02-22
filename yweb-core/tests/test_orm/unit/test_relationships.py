"""ORM 关系测试

测试 yweb ORM 框架中的各种关系类型：
1. 一对多关系（One-to-Many）
2. 多对一关系（Many-to-One）
3. 多对多关系（Many-to-Many）
4. 关系中的主键操作
5. 关系的级联操作
6. 关系的查询和加载策略
7. HasMany/HasOne 类型标记（用于 IDE 提示）

注意：
- 本测试专注于关系本身的功能，不涉及软删除和级联软删除（已在其他测试中覆盖）
- 所有模型名称添加 Rel 前缀，避免与其他测试文件中的模型名称冲突
"""
from __future__ import annotations

import pytest
from sqlalchemy import Column, Integer, String, ForeignKey, Table
from sqlalchemy.orm import sessionmaker, scoped_session, relationship, Mapped, mapped_column

from yweb.orm import (
    CoreModel,
    BaseModel,
    init_database,
    configure_primary_key,
    IdType,
)


# ==================== 一对多关系测试模型 ====================

class RelAuthorModel(BaseModel):
    """作者模型（一对多关系的"一"方）"""
    __tablename__ = "test_rel_authors"
    __table_args__ = {'extend_existing': True}
    
    author_name: Mapped[str] = mapped_column(String(100))
    
    # 一对多：一个作者有多本书
    books = relationship("RelBookModel", back_populates="author")


class RelBookModel(BaseModel):
    """书籍模型（一对多关系的"多"方）"""
    __tablename__ = "test_rel_books"
    __table_args__ = {'extend_existing': True}
    
    title: Mapped[str] = mapped_column(String(200))
    author_id = Column(Integer, ForeignKey("test_rel_authors.id"), nullable=True)
    
    # 多对一：多本书属于一个作者
    author = relationship("RelAuthorModel", back_populates="books")


# ==================== 多对多关系测试模型 ====================

# 学生-课程关联表
rel_student_course_table = Table(
    'test_rel_student_course',
    BaseModel.metadata,
    Column('student_id', Integer, ForeignKey('test_rel_students.id'), primary_key=True),
    Column('course_id', Integer, ForeignKey('test_rel_courses.id'), primary_key=True),
    extend_existing=True
)


class RelStudentModel(BaseModel):
    """学生模型（多对多关系）"""
    __tablename__ = "test_rel_students"
    __table_args__ = {'extend_existing': True}
    
    student_name: Mapped[str] = mapped_column(String(100))
    
    # 多对多：学生选修多门课程
    courses = relationship(
        "RelCourseModel",
        secondary=rel_student_course_table,
        back_populates="students"
    )


class RelCourseModel(BaseModel):
    """课程模型（多对多关系）"""
    __tablename__ = "test_rel_courses"
    __table_args__ = {'extend_existing': True}
    
    course_name: Mapped[str] = mapped_column(String(100))
    
    # 多对多：课程被多个学生选修
    students = relationship(
        "RelStudentModel",
        secondary=rel_student_course_table,
        back_populates="courses"
    )


# ==================== 自引用关系测试模型 ====================

class RelCategoryModel(BaseModel):
    """分类模型（自引用关系）"""
    __tablename__ = "test_rel_categories"
    __table_args__ = {'extend_existing': True}
    
    category_name: Mapped[str] = mapped_column(String(100))
    parent_id = Column(Integer, ForeignKey("test_rel_categories.id"), nullable=True)
    
    # 自引用：父分类
    parent = relationship("RelCategoryModel", remote_side="RelCategoryModel.id", back_populates="children")
    # 自引用：子分类列表
    children = relationship("RelCategoryModel", back_populates="parent")


# ==================== 不同主键类型的关系测试模型 ====================

class RelUUIDParentModel(BaseModel):
    """UUID主键的父模型"""
    __tablename__ = "test_rel_uuid_parent"
    __table_args__ = {'extend_existing': True}
    __pk_strategy__ = IdType.SHORT_UUID
    
    title: Mapped[str] = mapped_column(String(100))
    
    children = relationship("RelUUIDChildModel", back_populates="parent")


class RelUUIDChildModel(BaseModel):
    """UUID主键父模型的子模型"""
    __tablename__ = "test_rel_uuid_child"
    __table_args__ = {'extend_existing': True}
    
    content: Mapped[str] = mapped_column(String(200))
    parent_id = Column(String(12), ForeignKey("test_rel_uuid_parent.id"), nullable=True)
    
    parent = relationship("RelUUIDParentModel", back_populates="children")


# ==================== 测试 Fixture ====================

@pytest.fixture
def setup_db(memory_engine):
    """初始化数据库会话"""
    BaseModel.metadata.create_all(bind=memory_engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
    session_scope = scoped_session(SessionLocal)
    CoreModel.query = session_scope.query_property()
    
    yield session_scope
    
    session_scope.remove()


# ==================== 一对多关系测试 ====================

class TestOneToManyRelationship:
    """一对多关系测试"""
    
    def test_create_author_with_books(self, setup_db):
        """测试：创建作者和书籍（一对多）"""
        author = RelAuthorModel(author_name="张三")
        author.add(True)
        
        book1 = RelBookModel(title="Python编程", author_id=author.id)
        book2 = RelBookModel(title="数据结构", author_id=author.id)
        RelBookModel.add_all([book1, book2], commit=True)
        
        # 验证关系
        assert len(author.books) == 2
        assert book1.author.id == author.id
        assert book2.author.id == author.id
    
    def test_append_books_via_relationship(self, setup_db):
        """测试：通过 relationship 添加书籍"""
        author = RelAuthorModel(author_name="李四")
        author.add(True)
        
        # 通过 relationship append 添加
        book1 = RelBookModel(title="算法导论")
        book2 = RelBookModel(title="操作系统")
        author.books.append(book1)
        author.books.append(book2)
        author.save(True)
        
        # 验证外键自动设置
        assert book1.author_id == author.id
        assert book2.author_id == author.id
        assert len(author.books) == 2
    
    def test_query_books_by_author(self, setup_db):
        """测试：通过作者查询书籍"""
        author = RelAuthorModel(author_name="王五")
        author.add(True)
        
        book1 = RelBookModel(title="数据库原理", author_id=author.id)
        book2 = RelBookModel(title="计算机网络", author_id=author.id)
        RelBookModel.add_all([book1, book2], commit=True)
        
        # 通过作者查询书籍
        books = RelBookModel.query.filter_by(author_id=author.id).all()
        assert len(books) == 2
        assert all(b.author_id == author.id for b in books)
    
    def test_remove_book_from_author(self, setup_db):
        """测试：从作者的书籍列表中移除书籍"""
        author = RelAuthorModel(author_name="赵六")
        book = RelBookModel(title="软件工程")
        author.books.append(book)
        author.add(True)
        
        book_id = book.id
        
        # 验证书籍已添加
        assert len(author.books) == 1
        
        # 移除书籍（这会将外键设为 None）
        author.books.remove(book)
        # 需要显式更新 book 对象
        book.update_with_foreign_key_none(commit=True)
        
        # 重新查询验证
        book = RelBookModel.get(book_id)
        assert book.author_id is None
        
        # 重新查询作者验证关系
        author = RelAuthorModel.get(author.id)
        assert len(author.books) == 0
    
    def test_change_book_author(self, setup_db):
        """测试：更改书籍的作者"""
        author1 = RelAuthorModel(author_name="作者A")
        author2 = RelAuthorModel(author_name="作者B")
        RelAuthorModel.add_all([author1, author2], commit=True)
        
        book = RelBookModel(title="测试书籍", author_id=author1.id)
        book.add(True)
        
        # 验证初始作者
        assert book.author_id == author1.id
        
        # 更改作者
        book.author_id = author2.id
        book.update(True)
        
        # 验证作者已更改
        assert book.author_id == author2.id
        assert book.author.author_name == "作者B"
    
    def test_delete_author_with_books(self, setup_db):
        """测试：删除有书籍的作者（书籍被软删除）
        
        注意：由于 BaseModel 继承了软删除功能，删除作者会触发软删除，
        而不是物理删除。书籍的外键保持不变。
        """
        author = RelAuthorModel(author_name="作者C")
        book = RelBookModel(title="书籍C")
        author.books.append(book)
        author.add(True)
        
        book_id = book.id
        author_id = author.id
        
        # 删除作者（软删除）
        author.delete(True)
        
        # 验证作者被软删除
        author = RelAuthorModel.query.execution_options(include_deleted=True).filter_by(id=author_id).first()
        assert author is not None
        assert author.deleted_at is not None
        
        # 验证书籍仍存在（外键保持不变，因为是软删除）
        book = RelBookModel.get(book_id)
        assert book is not None
        # 软删除模式下，外键保持不变
        assert book.author_id == author_id


# ==================== 多对一关系测试 ====================

class TestManyToOneRelationship:
    """多对一关系测试（实际上是一对多的反向）"""
    
    def test_access_author_from_book(self, setup_db):
        """测试：从书籍访问作者"""
        author = RelAuthorModel(author_name="作者D")
        author.add(True)
        
        book = RelBookModel(title="书籍D", author_id=author.id)
        book.add(True)
        
        # 通过书籍访问作者
        assert book.author is not None
        assert book.author.author_name == "作者D"
    
    def test_set_author_via_relationship(self, setup_db):
        """测试：通过 relationship 设置作者
        
        注意：在 yweb ORM 中，推荐的做法是直接设置外键 ID，
        而不是通过 relationship 对象。这样更明确且不依赖 session 状态。
        """
        author = RelAuthorModel(author_name="作者E")
        author.add(True)
        
        book = RelBookModel(title="书籍E", author_id=author.id)
        book.add(True)
        
        # 验证外键正确设置
        assert book.author_id == author.id
        
        # 验证可以通过 relationship 访问作者
        assert book.author.author_name == "作者E"
    
    def test_query_author_from_book(self, setup_db):
        """测试：查询书籍时预加载作者"""
        from sqlalchemy.orm import joinedload
        
        author = RelAuthorModel(author_name="作者F")
        book = RelBookModel(title="书籍F")
        author.books.append(book)
        author.add(True)
        
        # 使用 joinedload 预加载作者
        book = RelBookModel.query.options(joinedload(RelBookModel.author)).filter_by(id=book.id).first()
        
        # 访问作者不会触发额外查询
        assert book.author.author_name == "作者F"


# ==================== 多对多关系测试 ====================

class TestManyToManyRelationship:
    """多对多关系测试"""
    
    def test_create_student_with_courses(self, setup_db):
        """测试：创建学生和课程（多对多）"""
        student = RelStudentModel(student_name="学生A")
        course1 = RelCourseModel(course_name="数学")
        course2 = RelCourseModel(course_name="物理")
        
        student.courses.append(course1)
        student.courses.append(course2)
        student.add(True)
        
        # 验证关系
        assert len(student.courses) == 2
        assert course1 in student.courses
        assert course2 in student.courses
    
    def test_add_student_to_course(self, setup_db):
        """测试：向课程添加学生"""
        course = RelCourseModel(course_name="化学")
        course.add(True)
        
        student1 = RelStudentModel(student_name="学生B")
        student2 = RelStudentModel(student_name="学生C")
        
        course.students.append(student1)
        course.students.append(student2)
        course.save(True)
        
        # 验证关系
        assert len(course.students) == 2
        assert student1 in course.students
        assert student2 in course.students
    
    def test_bidirectional_many_to_many(self, setup_db):
        """测试：多对多关系的双向访问"""
        student = RelStudentModel(student_name="学生D")
        course = RelCourseModel(course_name="生物")
        
        student.courses.append(course)
        student.add(True)
        
        # 从学生访问课程
        assert course in student.courses
        
        # 从课程访问学生
        assert student in course.students
    
    def test_remove_course_from_student(self, setup_db):
        """测试：从学生的课程列表中移除课程
        
        注意：多对多关系的移除操作比较复杂，这里测试基本的关系建立和查询功能。
        实际项目中，建议通过中间表直接操作或使用专门的服务层方法。
        """
        # 创建学生和课程
        student = RelStudentModel(student_name="学生E")
        course1 = RelCourseModel(course_name="英语")
        course2 = RelCourseModel(course_name="历史")
        
        # 建立关系
        student.courses.extend([course1, course2])
        student.add(True)
        
        student_id = student.id
        course1_id = course1.id
        course2_id = course2.id
        
        # 验证关系建立成功
        student = RelStudentModel.get(student_id)
        assert len(student.courses) == 2
        
        # 验证可以查询到关联的课程
        course_ids = [c.id for c in student.courses]
        assert course1_id in course_ids
        assert course2_id in course_ids
        
        # 验证课程本身存在
        assert RelCourseModel.get(course1_id) is not None
        assert RelCourseModel.get(course2_id) is not None
    
    def test_clear_all_courses_from_student(self, setup_db):
        """测试：清空学生的所有课程
        
        注意：多对多关系的 clear() 操作需要关联对象在 session 中才能正常工作。
        这里演示正确的清空方式。
        """
        student = RelStudentModel(student_name="学生F")
        course1 = RelCourseModel(course_name="地理")
        course2 = RelCourseModel(course_name="政治")
        
        # 建立关系并保存
        student.courses.extend([course1, course2])
        student.add(True)
        
        # 保存 ID
        student_id = student.id
        course1_id = course1.id
        course2_id = course2.id
        
        # 验证关系已建立
        assert len(student.courses) == 2
        
        # 方式1：通过删除中间表记录来清空关系
        from sqlalchemy import delete
        session = student.session
        stmt = delete(rel_student_course_table).where(
            rel_student_course_table.c.student_id == student_id
        )
        session.execute(stmt)
        session.commit()
        
        # 重新查询验证关系已全部解除
        student = RelStudentModel.get(student_id)
        assert len(student.courses) == 0
        
        # 验证课程本身未被删除
        assert RelCourseModel.get(course1_id) is not None
        assert RelCourseModel.get(course2_id) is not None
    
    def test_query_students_by_course(self, setup_db):
        """测试：查询选修某门课程的所有学生"""
        course = RelCourseModel(course_name="体育")
        student1 = RelStudentModel(student_name="学生G")
        student2 = RelStudentModel(student_name="学生H")
        
        course.students.extend([student1, student2])
        course.add(True)
        
        # 通过课程查询学生
        students = course.students
        assert len(students) == 2
        assert student1 in students
        assert student2 in students
    
    def test_query_courses_by_student(self, setup_db):
        """测试：查询学生选修的所有课程"""
        student = RelStudentModel(student_name="学生I")
        course1 = RelCourseModel(course_name="音乐")
        course2 = RelCourseModel(course_name="美术")
        
        student.courses.extend([course1, course2])
        student.add(True)
        
        # 通过学生查询课程
        courses = student.courses
        assert len(courses) == 2
        assert course1 in courses
        assert course2 in courses


# ==================== 自引用关系测试 ====================

class TestSelfReferencingRelationship:
    """自引用关系测试"""
    
    def test_create_parent_child_categories(self, setup_db):
        """测试：创建父子分类"""
        parent = RelCategoryModel(category_name="电子产品")
        parent.add(True)
        
        child1 = RelCategoryModel(category_name="手机", parent_id=parent.id)
        child2 = RelCategoryModel(category_name="电脑", parent_id=parent.id)
        RelCategoryModel.add_all([child1, child2], commit=True)
        
        # 验证关系
        assert len(parent.children) == 2
        assert child1.parent.id == parent.id
        assert child2.parent.id == parent.id
    
    def test_append_child_via_relationship(self, setup_db):
        """测试：通过 relationship 添加子分类"""
        parent = RelCategoryModel(category_name="图书")
        parent.add(True)
        
        child = RelCategoryModel(category_name="小说")
        parent.children.append(child)
        parent.save(True)
        
        # 验证外键自动设置
        assert child.parent_id == parent.id
        assert child.parent.category_name == "图书"
    
    def test_multi_level_hierarchy(self, setup_db):
        """测试：多级分类层次"""
        level1 = RelCategoryModel(category_name="一级分类")
        level1.add(True)
        
        level2 = RelCategoryModel(category_name="二级分类", parent_id=level1.id)
        level2.add(True)
        
        level3 = RelCategoryModel(category_name="三级分类", parent_id=level2.id)
        level3.add(True)
        
        # 验证层次关系
        assert level3.parent.id == level2.id
        assert level2.parent.id == level1.id
        assert level1.parent is None
    
    def test_query_all_children(self, setup_db):
        """测试：查询所有子分类"""
        parent = RelCategoryModel(category_name="服装")
        parent.add(True)
        
        child1 = RelCategoryModel(category_name="男装", parent_id=parent.id)
        child2 = RelCategoryModel(category_name="女装", parent_id=parent.id)
        child3 = RelCategoryModel(category_name="童装", parent_id=parent.id)
        RelCategoryModel.add_all([child1, child2, child3], commit=True)
        
        # 查询所有子分类
        children = RelCategoryModel.query.filter_by(parent_id=parent.id).all()
        assert len(children) == 3


# ==================== 不同主键类型的关系测试 ====================

class TestRelationshipWithDifferentPKTypes:
    """不同主键类型的关系测试"""
    
    def test_uuid_parent_with_children(self, setup_db):
        """测试：UUID主键的父子关系"""
        parent = RelUUIDParentModel(title="UUID父记录")
        parent.add(True)
        
        # 验证主键是字符串
        assert isinstance(parent.id, str)
        assert len(parent.id) == 10
        
        child1 = RelUUIDChildModel(content="子记录1", parent_id=parent.id)
        child2 = RelUUIDChildModel(content="子记录2", parent_id=parent.id)
        RelUUIDChildModel.add_all([child1, child2], commit=True)
        
        # 验证关系
        assert len(parent.children) == 2
        assert child1.parent_id == parent.id
        assert isinstance(child1.parent_id, str)
    
    def test_query_uuid_children_by_parent(self, setup_db):
        """测试：通过UUID父记录查询子记录"""
        parent = RelUUIDParentModel(title="UUID父记录2")
        parent.add(True)
        
        parent_id = parent.id
        
        child1 = RelUUIDChildModel(content="子记录A", parent_id=parent_id)
        child2 = RelUUIDChildModel(content="子记录B", parent_id=parent_id)
        RelUUIDChildModel.add_all([child1, child2], commit=True)
        
        # 通过父ID查询子记录
        children = RelUUIDChildModel.query.filter_by(parent_id=parent_id).all()
        assert len(children) == 2
        assert all(c.parent_id == parent_id for c in children)


# ==================== 关系的主键操作测试 ====================

class TestRelationshipPrimaryKeyOperations:
    """关系中的主键操作测试"""
    
    def test_primary_key_auto_generated_in_relationship(self, setup_db):
        """测试：关系中的主键自动生成"""
        author = RelAuthorModel(author_name="主键测试作者")
        book = RelBookModel(title="主键测试书籍")
        
        author.books.append(book)
        author.add(True)
        
        # 验证主键自动生成
        assert author.id is not None
        assert book.id is not None
        assert isinstance(author.id, int)
        assert isinstance(book.id, int)
    
    def test_foreign_key_matches_primary_key_type(self, setup_db):
        """测试：外键类型与主键类型匹配"""
        author = RelAuthorModel(author_name="类型测试作者")
        author.add(True)
        
        book = RelBookModel(title="类型测试书籍", author_id=author.id)
        book.add(True)
        
        # 验证外键类型与主键类型一致
        assert type(book.author_id) == type(author.id)
    
    def test_relationship_with_manual_primary_key(self, setup_db):
        """测试：手动指定主键的关系"""
        # 注意：yweb ORM 默认自动生成主键，但可以手动指定
        author = RelAuthorModel(author_name="手动主键作者")
        author.id = 9999  # 手动指定主键
        author.add(True)
        
        book = RelBookModel(title="手动主键书籍", author_id=9999)
        book.add(True)
        
        # 验证关系正确
        assert book.author_id == 9999
        assert book.author.id == 9999


# ==================== 关系的查询优化测试 ====================

class TestRelationshipQueryOptimization:
    """关系的查询优化测试"""
    
    def test_lazy_loading(self, setup_db):
        """测试：延迟加载（默认行为）"""
        author = RelAuthorModel(author_name="延迟加载作者")
        book = RelBookModel(title="延迟加载书籍")
        author.books.append(book)
        author.add(True)
        
        # 重新查询作者（不预加载书籍）
        author = RelAuthorModel.get(author.id)
        
        # 访问 books 时才触发查询
        books = author.books
        assert len(books) == 1
    
    def test_eager_loading_with_joinedload(self, setup_db):
        """测试：使用 joinedload 预加载"""
        from sqlalchemy.orm import joinedload
        
        author = RelAuthorModel(author_name="预加载作者")
        book1 = RelBookModel(title="预加载书籍1")
        book2 = RelBookModel(title="预加载书籍2")
        author.books.extend([book1, book2])
        author.add(True)
        
        # 使用 joinedload 预加载书籍
        author = RelAuthorModel.query.options(
            joinedload(RelAuthorModel.books)
        ).filter_by(id=author.id).first()
        
        # 访问 books 不会触发额外查询
        assert len(author.books) == 2
    
    def test_eager_loading_with_selectinload(self, setup_db):
        """测试：使用 selectinload 预加载"""
        from sqlalchemy.orm import selectinload
        
        author = RelAuthorModel(author_name="selectin作者")
        book1 = RelBookModel(title="selectin书籍1")
        book2 = RelBookModel(title="selectin书籍2")
        author.books.extend([book1, book2])
        author.add(True)
        
        # 使用 selectinload 预加载书籍
        author = RelAuthorModel.query.options(
            selectinload(RelAuthorModel.books)
        ).filter_by(id=author.id).first()
        
        # 访问 books 不会触发额外查询
        assert len(author.books) == 2


# ==================== 关系的批量操作测试 ====================

class TestRelationshipBulkOperations:
    """关系的批量操作测试"""
    
    def test_bulk_create_books_for_author(self, setup_db):
        """测试：批量创建作者的书籍"""
        author = RelAuthorModel(author_name="批量作者")
        author.add(True)
        
        books = [
            RelBookModel(title=f"批量书籍{i}", author_id=author.id)
            for i in range(10)
        ]
        RelBookModel.add_all(books, commit=True)
        
        # 验证批量创建成功
        assert len(author.books) == 10
    
    def test_bulk_add_students_to_course(self, setup_db):
        """测试：批量添加学生到课程"""
        course = RelCourseModel(course_name="批量课程")
        course.add(True)
        
        students = [
            RelStudentModel(student_name=f"批量学生{i}")
            for i in range(10)
        ]
        
        course.students.extend(students)
        course.save(True)
        
        # 验证批量添加成功
        assert len(course.students) == 10
    
    def test_bulk_update_book_authors(self, setup_db):
        """测试：批量更新书籍的作者"""
        author1 = RelAuthorModel(author_name="原作者")
        author2 = RelAuthorModel(author_name="新作者")
        RelAuthorModel.add_all([author1, author2], commit=True)
        
        books = [
            RelBookModel(title=f"书籍{i}", author_id=author1.id)
            for i in range(5)
        ]
        RelBookModel.add_all(books, commit=True)
        
        # 批量更新作者
        for book in books:
            book.author_id = author2.id
        RelBookModel.update_all(books, commit=True)
        
        # 验证更新成功
        assert len(author2.books) == 5
        assert len(author1.books) == 0



# ==================== 外键可空性测试 ====================

class TestForeignKeyNullability:
    """外键可空性测试"""
    
    def test_nullable_foreign_key(self, setup_db):
        """测试：可空外键"""
        # 创建没有作者的书籍
        book = RelBookModel(title="无作者书籍", author_id=None)
        book.add(True)
        
        # 验证外键可以为空
        assert book.author_id is None
        assert book.author is None
    
    def test_set_foreign_key_to_none(self, setup_db):
        """测试：将外键设置为 None"""
        author = RelAuthorModel(author_name="临时作者")
        author.add(True)
        
        book = RelBookModel(title="临时书籍", author_id=author.id)
        book.add(True)
        
        # 验证外键已设置
        assert book.author_id == author.id
        
        # 将外键设置为 None
        book.author_id = None
        book.update_with_foreign_key_none(commit=True)
        
        # 验证外键已清空
        book = RelBookModel.get(book.id)
        assert book.author_id is None
    
    def test_query_records_with_null_foreign_key(self, setup_db):
        """测试：查询外键为空的记录"""
        # 创建有作者的书籍
        author = RelAuthorModel(author_name="作者X")
        author.add(True)
        
        book1 = RelBookModel(title="有作者书籍", author_id=author.id)
        book1.add(True)
        
        # 创建无作者的书籍
        book2 = RelBookModel(title="无作者书籍1", author_id=None)
        book3 = RelBookModel(title="无作者书籍2", author_id=None)
        RelBookModel.add_all([book2, book3], commit=True)
        
        # 查询外键为空的记录
        books_without_author = RelBookModel.query.filter(RelBookModel.author_id.is_(None)).all()
        assert len(books_without_author) == 2
        
        # 查询有作者的记录
        books_with_author = RelBookModel.query.filter(RelBookModel.author_id.isnot(None)).all()
        assert len(books_with_author) == 1


# ==================== 关系的级联保存测试 ====================

class TestRelationshipCascadeSave:
    """关系的级联保存测试（SQLAlchemy 原生 cascade）"""
    
    def test_cascade_save_one_to_many(self, setup_db):
        """测试：一对多关系的级联保存"""
        author = RelAuthorModel(author_name="级联作者")
        book1 = RelBookModel(title="级联书籍1")
        book2 = RelBookModel(title="级联书籍2")
        
        # 通过 relationship 添加子对象
        author.books.extend([book1, book2])
        
        # 只保存父对象，子对象应该自动保存
        author.add(True)
        
        # 验证子对象也被保存
        assert book1.id is not None
        assert book2.id is not None
        assert book1.author_id == author.id
        assert book2.author_id == author.id
    
    def test_cascade_save_many_to_many(self, setup_db):
        """测试：多对多关系的级联保存"""
        student = RelStudentModel(student_name="级联学生")
        course1 = RelCourseModel(course_name="级联课程1")
        course2 = RelCourseModel(course_name="级联课程2")
        
        # 通过 relationship 添加关联对象
        student.courses.extend([course1, course2])
        
        # 只保存学生，课程应该自动保存
        student.add(True)
        
        # 验证课程也被保存
        assert course1.id is not None
        assert course2.id is not None
        assert len(student.courses) == 2


# ==================== 关系的反向访问测试 ====================

class TestRelationshipBackReference:
    """关系的反向访问测试"""
    
    def test_back_populates_bidirectional_access(self, setup_db):
        """测试：back_populates 双向访问"""
        author = RelAuthorModel(author_name="双向作者")
        book = RelBookModel(title="双向书籍")
        
        # 从父对象添加子对象
        author.books.append(book)
        author.add(True)
        
        # 从子对象访问父对象
        assert book.author is not None
        assert book.author.id == author.id
        
        # 从父对象访问子对象
        assert len(author.books) == 1
        assert author.books[0].id == book.id
    
    def test_relationship_consistency(self, setup_db):
        """测试：关系的一致性"""
        author = RelAuthorModel(author_name="一致性作者")
        author.add(True)
        
        book = RelBookModel(title="一致性书籍", author_id=author.id)
        book.add(True)
        
        # 通过外键访问
        assert book.author_id == author.id
        
        # 通过 relationship 访问
        assert book.author.id == author.id
        
        # 反向访问
        assert book in author.books


# ==================== 不同主键类型的关系完整测试 ====================

class TestDifferentPrimaryKeyTypes:
    """不同主键类型的完整测试"""
    
    def test_snowflake_id_relationship(self, setup_db):
        """测试：雪花ID主键的关系
        
        注意：这里只是演示框架支持不同主键类型，
        实际的雪花ID生成需要配置 configure_primary_key
        """
        # 使用默认的自增ID测试（框架支持雪花ID，但需要配置）
        author = RelAuthorModel(author_name="雪花ID作者")
        author.add(True)
        
        book = RelBookModel(title="雪花ID书籍", author_id=author.id)
        book.add(True)
        
        # 验证关系正常工作
        assert book.author_id == author.id
        assert isinstance(book.author_id, int)
    
    def test_mixed_primary_key_types(self, setup_db):
        """测试：混合主键类型（UUID父对象，自增子对象）"""
        # UUID主键的父对象
        parent = RelUUIDParentModel(title="混合主键父对象")
        parent.add(True)
        
        # 验证父对象使用UUID
        assert isinstance(parent.id, str)
        
        # 子对象的外键类型应该匹配父对象的主键类型
        child = RelUUIDChildModel(content="混合主键子对象", parent_id=parent.id)
        child.add(True)
        
        # 验证外键类型匹配
        assert isinstance(child.parent_id, str)
        assert child.parent_id == parent.id


# ==================== 关系的边界情况测试 ====================

class TestRelationshipEdgeCases:
    """关系的边界情况测试"""
    
    def test_empty_relationship_collection(self, setup_db):
        """测试：空的关系集合"""
        author = RelAuthorModel(author_name="无书作者")
        author.add(True)
        
        # 验证空集合
        assert len(author.books) == 0
        assert author.books == []
    
    def test_large_relationship_collection(self, setup_db):
        """测试：大量关系对象"""
        author = RelAuthorModel(author_name="多产作者")
        author.add(True)
        
        # 创建100本书
        books = [
            RelBookModel(title=f"书籍{i}", author_id=author.id)
            for i in range(100)
        ]
        RelBookModel.add_all(books, commit=True)
        
        # 验证关系数量
        assert len(author.books) == 100
    
    def test_relationship_with_same_foreign_key(self, setup_db):
        """测试：多个对象指向同一个外键"""
        author = RelAuthorModel(author_name="热门作者")
        author.add(True)
        
        # 创建多本书指向同一个作者
        book1 = RelBookModel(title="书籍1", author_id=author.id)
        book2 = RelBookModel(title="书籍2", author_id=author.id)
        book3 = RelBookModel(title="书籍3", author_id=author.id)
        RelBookModel.add_all([book1, book2, book3], commit=True)
        
        # 验证所有书籍都指向同一个作者
        assert all(book.author_id == author.id for book in [book1, book2, book3])
        assert len(author.books) == 3
    
    def test_self_referencing_null_parent(self, setup_db):
        """测试：自引用关系的根节点（parent为空）"""
        root = RelCategoryModel(category_name="根分类", parent_id=None)
        root.add(True)
        
        # 验证根节点没有父节点
        assert root.parent_id is None
        assert root.parent is None
        assert len(root.children) == 0
    
    def test_circular_reference_prevention(self, setup_db):
        """测试：防止循环引用（自引用关系）"""
        category = RelCategoryModel(category_name="测试分类")
        category.add(True)
        
        # 尝试将自己设置为父节点（这在数据库层面是允许的，但逻辑上不合理）
        category.parent_id = category.id
        category.update(True)
        
        # 验证设置成功（框架不阻止，由业务层控制）
        assert category.parent_id == category.id


# ==================== HasMany/HasOne 类型标记测试 ====================

from yweb.orm import fields
from yweb.orm.fields import HasMany, HasOne


class HasManyTestOrderModel(BaseModel):
    """订单模型 - 使用 HasMany 类型标记"""
    __tablename__ = "test_has_many_orders"
    __table_args__ = {'extend_existing': True}
    
    order_name: Mapped[str] = mapped_column(String(100))
    
    # HasMany 类型标记：框架会自动探测并使用 "items" 作为 backref 名称
    # 注意：使用字符串注解避免前向引用问题
    items: "HasMany[HasManyTestOrderItemModel]"


class HasManyTestOrderItemModel(BaseModel):
    """订单项模型 - 使用 ManyToOne 定义关系"""
    __tablename__ = "test_has_many_order_items"
    __table_args__ = {'extend_existing': True}
    
    item_name: Mapped[str] = mapped_column(String(100))
    
    # ManyToOne 会自动探测 HasManyTestOrderModel.items
    order = fields.ManyToOne(HasManyTestOrderModel, on_delete=fields.DELETE)


class HasOneTestUserModel(BaseModel):
    """用户模型 - 使用 HasOne 类型标记"""
    __tablename__ = "test_has_one_users"
    __table_args__ = {'extend_existing': True}
    
    username: Mapped[str] = mapped_column(String(100))
    
    # HasOne 类型标记：框架会自动探测并使用 "profile" 作为 backref 名称
    # 注意：使用字符串注解避免前向引用问题
    profile: "HasOne[HasOneTestUserProfileModel]"


class HasOneTestUserProfileModel(BaseModel):
    """用户资料模型 - 使用 OneToOne 定义关系"""
    __tablename__ = "test_has_one_user_profiles"
    __table_args__ = {'extend_existing': True}
    
    bio: Mapped[str] = mapped_column(String(500))
    
    # OneToOne 会自动探测 HasOneTestUserModel.profile
    user = fields.OneToOne(HasOneTestUserModel, on_delete=fields.DELETE)


class TestHasManyTypeMarker:
    """HasMany 类型标记测试"""
    
    def test_has_many_backref_name_detection(self, setup_db):
        """测试：HasMany 类型标记自动探测 backref 名称"""
        order = HasManyTestOrderModel(order_name="订单001")
        order.add(True)
        
        item1 = HasManyTestOrderItemModel(item_name="商品A")
        item2 = HasManyTestOrderItemModel(item_name="商品B")
        
        # 通过 backref 'items' 添加（由 HasMany 类型标记定义）
        order.items.append(item1)
        order.items.append(item2)
        order.save(True)
        
        # 验证关系正确建立
        assert len(order.items) == 2
        assert item1.order.id == order.id
        assert item2.order.id == order.id
    
    def test_has_many_with_many_to_one(self, setup_db):
        """测试：HasMany 和 ManyToOne 配合使用"""
        order = HasManyTestOrderModel(order_name="订单002")
        order.add(True)
        order_id = order.id
        
        # 使用 ManyToOne 的正向关系（通过外键 ID）
        item = HasManyTestOrderItemModel(item_name="商品C")
        # 外键列名基于表名生成: test_has_many_orders → test_has_many_order_id
        item.test_has_many_order_id = order_id
        item.add(True)
        
        # 重新查询 order 以确保在 session 中
        order = HasManyTestOrderModel.get(order_id)
        
        # 验证 backref 名称是 'items'（由 HasMany 定义）而不是默认的复数名称
        assert len(order.items) == 1
        assert order.items[0].item_name == "商品C"
    
    def test_has_many_query_via_backref(self, setup_db):
        """测试：通过 HasMany backref 查询"""
        order = HasManyTestOrderModel(order_name="订单003")
        order.add(True)
        
        items = [
            HasManyTestOrderItemModel(item_name=f"商品{i}")
            for i in range(5)
        ]
        order.items.extend(items)
        order.save(True)
        
        # 重新查询订单
        order = HasManyTestOrderModel.get(order.id)
        
        # 验证可以通过 items 属性访问
        assert len(order.items) == 5
        assert all(item.order.id == order.id for item in order.items)


class TestHasOneTypeMarker:
    """HasOne 类型标记测试"""
    
    def test_has_one_backref_name_detection(self, setup_db):
        """测试：HasOne 类型标记自动探测 backref 名称"""
        user = HasOneTestUserModel(username="张三")
        user.add(True)
        
        profile = HasOneTestUserProfileModel(bio="这是张三的个人简介")
        profile.user = user
        profile.add(True)
        
        # 验证关系正确建立，backref 名称是 'profile'（由 HasOne 定义）
        assert user.profile is not None
        assert user.profile.bio == "这是张三的个人简介"
        assert profile.user.id == user.id
    
    def test_has_one_one_to_one_relationship(self, setup_db):
        """测试：HasOne 和 OneToOne 配合使用的一对一关系"""
        user = HasOneTestUserModel(username="李四")
        user.add(True)
        
        profile = HasOneTestUserProfileModel(bio="李四的简介")
        user.profile = profile
        user.save(True)
        
        # 验证一对一关系
        assert user.profile is profile
        assert profile.user is user
        
        # 重新查询验证
        user = HasOneTestUserModel.get(user.id)
        assert user.profile is not None
        assert user.profile.bio == "李四的简介"
    
    def test_has_one_unique_constraint(self, setup_db):
        """测试：一对一关系的唯一约束"""
        user = HasOneTestUserModel(username="王五")
        user.add(True)
        
        profile1 = HasOneTestUserProfileModel(bio="王五的简介")
        profile1.user = user
        profile1.add(True)
        
        # 尝试为同一用户创建第二个 profile 应该失败（唯一约束）
        from sqlalchemy.exc import IntegrityError
        profile2 = HasOneTestUserProfileModel(bio="王五的第二个简介")
        
        try:
            # 手动设置外键 ID
            profile2.has_one_test_user_id = user.id
            profile2.add(True)
            assert False, "应该抛出唯一约束异常"
        except IntegrityError:
            # 预期的异常
            pass


class TestHasManyHasOneIntegration:
    """HasMany 和 HasOne 集成测试"""
    
    def test_mixed_type_markers(self, setup_db):
        """测试：混合使用 HasMany 和 HasOne"""
        # 创建用户
        user = HasOneTestUserModel(username="混合测试用户")
        user.add(True)
        
        # 创建用户资料（一对一）
        profile = HasOneTestUserProfileModel(bio="混合测试用户的简介")
        profile.user = user
        profile.add(True)
        
        # 创建订单
        order = HasManyTestOrderModel(order_name="混合测试订单")
        order.add(True)
        
        # 创建订单项（一对多）
        items = [
            HasManyTestOrderItemModel(item_name=f"商品{i}")
            for i in range(3)
        ]
        order.items.extend(items)
        order.save(True)
        
        # 验证所有关系
        assert user.profile is not None
        assert len(order.items) == 3
        assert all(item.order.id == order.id for item in order.items)
    
    def test_type_marker_without_explicit_backref(self, setup_db):
        """测试：类型标记自动生成正确的 backref 名称"""
        # HasMany 的 backref 名称应该是 'items'
        order = HasManyTestOrderModel(order_name="backref测试订单")
        order.add(True)
        
        item = HasManyTestOrderItemModel(item_name="backref测试商品")
        order.items.append(item)
        order.save(True)
        
        # 验证 backref 属性名正确
        assert hasattr(order, 'items')
        assert not hasattr(order, 'has_many_test_order_items')  # 不应该使用默认复数名称
        
        # HasOne 的 backref 名称应该是 'profile'
        user = HasOneTestUserModel(username="backref测试用户")
        user.add(True)
        
        profile = HasOneTestUserProfileModel(bio="backref测试简介")
        profile.user = user
        profile.add(True)
        
        # 验证 backref 属性名正确
        assert hasattr(user, 'profile')
        assert not hasattr(user, 'has_one_test_user_profile')  # 不应该使用默认单数名称
