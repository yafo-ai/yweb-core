"""主键策略与外键关联测试

测试不同主键策略的模型作为外键目标时，外键字段类型是否正确匹配。

测试场景：
1. 整数自增主键 -> 外键应为 Integer
2. 短UUID主键 -> 外键应为 String
3. 完整UUID主键 -> 外键应为 String
4. 雪花算法主键 -> 外键应为 BigInteger
5. 自定义主键 -> 外键应为 String

重要：外键字段类型必须与目标模型的主键类型匹配，否则会导致：
- 类型转换错误
- 外键约束失败
- 查询结果不正确
"""

import pytest
from sqlalchemy import String, Integer, BigInteger, Column, ForeignKey
from sqlalchemy.orm import sessionmaker, scoped_session, Mapped, mapped_column, relationship

from yweb.orm import (
    CoreModel,
    BaseModel,
    init_database,
    configure_primary_key,
    PrimaryKeyConfig,
    IdType,
    fields,
)


# ==================== 不同主键类型的父模型 ====================

class AutoIncrementParent(BaseModel):
    """整数自增主键的父模型"""
    __tablename__ = "test_fk_auto_increment_parent"
    __table_args__ = {'extend_existing': True}
    __pk_strategy__ = IdType.AUTO_INCREMENT
    
    title: Mapped[str] = mapped_column(String(100), nullable=True)


class ShortUUIDParent(BaseModel):
    """短UUID主键的父模型"""
    __tablename__ = "test_fk_short_uuid_parent"
    __table_args__ = {'extend_existing': True}
    __pk_strategy__ = IdType.SHORT_UUID
    
    title: Mapped[str] = mapped_column(String(100), nullable=True)


class FullUUIDParent(BaseModel):
    """完整UUID主键的父模型"""
    __tablename__ = "test_fk_full_uuid_parent"
    __table_args__ = {'extend_existing': True}
    __pk_strategy__ = IdType.UUID
    
    title: Mapped[str] = mapped_column(String(100), nullable=True)


class SnowflakeParent(BaseModel):
    """雪花算法主键的父模型"""
    __tablename__ = "test_fk_snowflake_parent"
    __table_args__ = {'extend_existing': True}
    __pk_strategy__ = IdType.SNOWFLAKE
    
    title: Mapped[str] = mapped_column(String(100), nullable=True)


# ==================== 测试 Fixture ====================

@pytest.fixture
def setup_db(memory_engine):
    """初始化数据库会话"""
    PrimaryKeyConfig.reset()
    configure_primary_key(
        strategy=IdType.AUTO_INCREMENT,
        short_uuid_length=10,
        snowflake_worker_id=1,
        snowflake_datacenter_id=1,
        custom_generator=lambda: f"CUSTOM_{id(object()):010d}",
        max_retries=5
    )
    
    BaseModel.metadata.create_all(bind=memory_engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
    session_scope = scoped_session(SessionLocal)
    CoreModel.query = session_scope.query_property()
    
    yield session_scope
    
    session_scope.remove()
    PrimaryKeyConfig.reset()


# ==================== 父模型主键类型验证 ====================

class TestParentPrimaryKeyTypes:
    """验证父模型的主键类型正确"""
    
    def test_auto_increment_parent_pk_is_integer(self):
        """测试：整数自增父模型的主键是 Integer"""
        col = AutoIncrementParent.__table__.c.id
        assert isinstance(col.type, Integer), \
            f"AutoIncrementParent.id 应该是 Integer，实际是 {type(col.type)}"
    
    def test_short_uuid_parent_pk_is_string(self):
        """测试：短UUID父模型的主键是 String"""
        col = ShortUUIDParent.__table__.c.id
        assert isinstance(col.type, String), \
            f"ShortUUIDParent.id 应该是 String，实际是 {type(col.type)}"
    
    def test_full_uuid_parent_pk_is_string(self):
        """测试：完整UUID父模型的主键是 String"""
        col = FullUUIDParent.__table__.c.id
        assert isinstance(col.type, String), \
            f"FullUUIDParent.id 应该是 String，实际是 {type(col.type)}"
    
    def test_snowflake_parent_pk_is_biginteger(self):
        """测试：雪花算法父模型的主键是 BigInteger"""
        col = SnowflakeParent.__table__.c.id
        assert isinstance(col.type, (Integer, BigInteger)), \
            f"SnowflakeParent.id 应该是 BigInteger，实际是 {type(col.type)}"


# ==================== 外键类型匹配测试（手动定义外键） ====================

class TestManualForeignKeyTypeMatch:
    """手动定义外键时的类型匹配测试"""
    
    def test_integer_fk_for_auto_increment_parent(self, setup_db):
        """测试：引用整数自增父模型时，外键应为 Integer"""
        session_scope = setup_db
        
        # 动态创建子模型
        ChildModel = type(
            'AutoIncrementChild',
            (BaseModel,),
            {
                '__tablename__': 'test_fk_auto_increment_child',
                '__table_args__': {'extend_existing': True},
                '__module__': __name__,
                'parent_id': Column(Integer, ForeignKey('test_fk_auto_increment_parent.id')),
            }
        )
        
        # 创建表
        ChildModel.__table__.create(bind=session_scope.get_bind(), checkfirst=True)
        
        # 创建父记录
        parent = AutoIncrementParent(title="Parent")
        parent.add(True)
        
        # 创建子记录
        session = session_scope()
        child = ChildModel()
        child.parent_id = parent.id
        session.add(child)
        session.commit()
        
        # 验证外键正确
        assert child.parent_id == parent.id
        assert isinstance(child.parent_id, int)
    
    def test_string_fk_for_short_uuid_parent(self, setup_db):
        """测试：引用短UUID父模型时，外键应为 String"""
        session_scope = setup_db
        
        # 动态创建子模型（使用 String 类型的外键）
        ChildModel = type(
            'ShortUUIDChild',
            (BaseModel,),
            {
                '__tablename__': 'test_fk_short_uuid_child',
                '__table_args__': {'extend_existing': True},
                '__module__': __name__,
                'parent_id': Column(String(12), ForeignKey('test_fk_short_uuid_parent.id')),
            }
        )
        
        # 创建表
        ChildModel.__table__.create(bind=session_scope.get_bind(), checkfirst=True)
        
        # 创建父记录
        parent = ShortUUIDParent(title="Parent")
        parent.add(True)
        
        # 验证父记录 id 是字符串
        assert isinstance(parent.id, str)
        assert len(parent.id) == 10
        
        # 创建子记录
        session = session_scope()
        child = ChildModel()
        child.parent_id = parent.id
        session.add(child)
        session.commit()
        
        # 验证外键正确
        assert child.parent_id == parent.id
        assert isinstance(child.parent_id, str)
    
    def test_string_fk_for_full_uuid_parent(self, setup_db):
        """测试：引用完整UUID父模型时，外键应为 String(36)"""
        session_scope = setup_db
        
        # 动态创建子模型
        ChildModel = type(
            'FullUUIDChild',
            (BaseModel,),
            {
                '__tablename__': 'test_fk_full_uuid_child',
                '__table_args__': {'extend_existing': True},
                '__module__': __name__,
                'parent_id': Column(String(36), ForeignKey('test_fk_full_uuid_parent.id')),
            }
        )
        
        # 创建表
        ChildModel.__table__.create(bind=session_scope.get_bind(), checkfirst=True)
        
        # 创建父记录
        parent = FullUUIDParent(title="Parent")
        parent.add(True)
        
        # 验证父记录 id 是 UUID 字符串
        assert isinstance(parent.id, str)
        assert len(parent.id) == 36
        assert '-' in parent.id
        
        # 创建子记录
        session = session_scope()
        child = ChildModel()
        child.parent_id = parent.id
        session.add(child)
        session.commit()
        
        # 验证外键正确
        assert child.parent_id == parent.id
    
    def test_biginteger_fk_for_snowflake_parent(self, setup_db):
        """测试：引用雪花算法父模型时，外键应为 BigInteger"""
        session_scope = setup_db
        
        # 动态创建子模型
        ChildModel = type(
            'SnowflakeChild',
            (BaseModel,),
            {
                '__tablename__': 'test_fk_snowflake_child',
                '__table_args__': {'extend_existing': True},
                '__module__': __name__,
                'parent_id': Column(BigInteger, ForeignKey('test_fk_snowflake_parent.id')),
            }
        )
        
        # 创建表
        ChildModel.__table__.create(bind=session_scope.get_bind(), checkfirst=True)
        
        # 创建父记录
        parent = SnowflakeParent(title="Parent")
        parent.add(True)
        
        # 验证父记录 id 是大整数
        assert isinstance(parent.id, int)
        assert parent.id > 1_000_000_000_000
        
        # 创建子记录
        session = session_scope()
        child = ChildModel()
        child.parent_id = parent.id
        session.add(child)
        session.commit()
        
        # 验证外键正确
        assert child.parent_id == parent.id


# ==================== 外键关联数据完整性测试 ====================

class TestForeignKeyDataIntegrity:
    """外键关联的数据完整性测试"""
    
    def test_query_child_by_parent_with_short_uuid(self, setup_db):
        """测试：通过短UUID父记录查询子记录"""
        session_scope = setup_db
        
        # 创建子模型
        ChildModel = type(
            'ShortUUIDChildQuery',
            (BaseModel,),
            {
                '__tablename__': 'test_fk_short_uuid_child_query',
                '__table_args__': {'extend_existing': True},
                '__module__': __name__,
                'parent_id': Column(String(12), ForeignKey('test_fk_short_uuid_parent.id')),
                'content': Column(String(100)),
            }
        )
        
        ChildModel.__table__.create(bind=session_scope.get_bind(), checkfirst=True)
        
        # 创建父记录
        parent = ShortUUIDParent(title="Parent")
        parent.add(True)
        parent_id = parent.id
        
        # 创建多个子记录
        session = session_scope()
        for i in range(3):
            child = ChildModel()
            child.parent_id = parent_id
            child.content = f"Child {i}"
            session.add(child)
        session.commit()
        
        # 通过父 ID 查询子记录
        children = session.query(ChildModel).filter_by(parent_id=parent_id).all()
        
        assert len(children) == 3
        for child in children:
            assert child.parent_id == parent_id
    
    def test_update_parent_id_with_different_pk_types(self, setup_db):
        """测试：更新不同主键类型的外键值"""
        session_scope = setup_db
        
        # 创建子模型
        ChildModel = type(
            'ShortUUIDChildUpdate',
            (BaseModel,),
            {
                '__tablename__': 'test_fk_short_uuid_child_update',
                '__table_args__': {'extend_existing': True},
                '__module__': __name__,
                'parent_id': Column(String(12), ForeignKey('test_fk_short_uuid_parent.id'), nullable=True),
            }
        )
        
        ChildModel.__table__.create(bind=session_scope.get_bind(), checkfirst=True)
        
        # 创建两个父记录
        parent1 = ShortUUIDParent(title="Parent1")
        parent1.add(True)
        
        parent2 = ShortUUIDParent(title="Parent2")
        parent2.add(True)
        
        # 创建子记录，关联到 parent1
        session = session_scope()
        child = ChildModel()
        child.parent_id = parent1.id
        session.add(child)
        session.commit()
        
        child_id = child.id
        
        # 更新外键到 parent2
        child.parent_id = parent2.id
        session.commit()
        
        # 重新查询验证
        updated_child = session.query(ChildModel).filter_by(id=child_id).first()
        assert updated_child.parent_id == parent2.id


# ==================== fields.ManyToOne 自动类型匹配测试 ====================

class TestManyToOneAutoTypeMatch:
    """测试 fields.ManyToOne 是否自动匹配目标模型的主键类型"""
    
    def test_many_to_one_auto_detects_integer_pk(self, setup_db):
        """测试：fields.ManyToOne 自动检测整数主键类型"""
        session_scope = setup_db
        
        # 使用 fields.ManyToOne 定义子模型
        class AutoIncrementChildFK(BaseModel):
            __tablename__ = "test_fkfield_auto_child"
            __table_args__ = {'extend_existing': True}
            
            parent = fields.ManyToOne(AutoIncrementParent, on_delete=fields.DELETE)
        
        # 检查生成的外键列类型（由 CoreModel.__init_subclass__ 自动处理）
        fk_col = AutoIncrementChildFK.__table__.c.get('parent_id')
        if fk_col is None:
            # 尝试其他可能的列名
            for col_name in AutoIncrementChildFK.__table__.c.keys():
                if 'parent' in col_name.lower() or 'auto' in col_name.lower():
                    fk_col = AutoIncrementChildFK.__table__.c[col_name]
                    break
        
        assert fk_col is not None, "外键列应该存在"
        # 当前实现使用 Integer，这对整数主键是正确的
        assert isinstance(fk_col.type, Integer), \
            f"引用整数主键时，外键应为 Integer，实际是 {type(fk_col.type)}"
    
    def test_many_to_one_should_match_string_pk(self, setup_db):
        """测试：fields.ManyToOne 引用字符串主键时自动使用 String 类型"""
        session_scope = setup_db
        
        # 使用 fields.ManyToOne 定义子模型
        class ShortUUIDChildFK(BaseModel):
            __tablename__ = "test_fkfield_uuid_child"
            __table_args__ = {'extend_existing': True}
            
            parent = fields.ManyToOne(ShortUUIDParent, on_delete=fields.DELETE)
        
        # 检查生成的外键列类型
        fk_col = None
        for col_name in ShortUUIDChildFK.__table__.c.keys():
            if 'parent' in col_name.lower() or 'uuid' in col_name.lower():
                if col_name != 'id':
                    fk_col = ShortUUIDChildFK.__table__.c[col_name]
                    break
        
        assert fk_col is not None, "外键列应该存在"
        
        # 验证外键列类型是 String（匹配目标模型的 short_uuid 主键）
        assert isinstance(fk_col.type, String), \
            f"引用字符串主键时，外键应为 String，实际是 {type(fk_col.type)}"


# ==================== 混合主键类型测试 ====================

class TestMixedPrimaryKeyTypes:
    """测试一个应用中同时使用多种主键类型的场景"""
    
    def test_multiple_fk_types_in_one_session(self, setup_db):
        """测试：同一 session 中操作多种主键类型的外键"""
        session_scope = setup_db
        session = session_scope()
        
        # 创建整数主键父记录
        auto_parent = AutoIncrementParent(title="AutoParent")
        auto_parent.add(True)
        
        # 创建短UUID主键父记录
        uuid_parent = ShortUUIDParent(title="UUIDParent")
        uuid_parent.add(True)
        
        # 创建雪花主键父记录
        snow_parent = SnowflakeParent(title="SnowParent")
        snow_parent.add(True)
        
        # 验证类型
        assert isinstance(auto_parent.id, int)
        assert isinstance(uuid_parent.id, str)
        assert isinstance(snow_parent.id, int)
        assert snow_parent.id > 1_000_000_000_000
        
        # 验证都能正确查询
        found_auto = AutoIncrementParent.get(auto_parent.id)
        found_uuid = ShortUUIDParent.get(uuid_parent.id)
        found_snow = SnowflakeParent.get(snow_parent.id)
        
        assert found_auto is not None
        assert found_uuid is not None
        assert found_snow is not None
