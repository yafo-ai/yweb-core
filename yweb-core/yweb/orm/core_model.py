"""
ORM基础模型

提供常用的CRUD操作、分页查询、批量操作等功能
"""

from __future__ import annotations

import math
import re
from sqlalchemy import select, func, event, delete, update, inspect
from sqlalchemy import Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, declared_attr, Session, Query
from datetime import datetime
from typing import Optional, Type, TypeVar, List, Union, ClassVar, TYPE_CHECKING, overload

if TYPE_CHECKING:
    from typing_extensions import Self

from .base_schemas import Page
from .orm_extensions.soft_delete_mixin import SimpleSoftDeleteMixin
from .history.history_helper import is_versioning_initialized
from .id_model import IdModel, Base
from .utils import to_snake_case


T = TypeVar("T")

# 主键类型别名：支持整数（自增/雪花算法）或字符串（UUID/短UUID）
PKType = Union[int, str]


# 历史记录功能说明：
# sqlalchemy_history 的 make_versioned() 已移至 history.py 的 init_versioning() 中
# 用户需要在应用启动时按以下顺序初始化：
#   1. init_database()           - 初始化数据库
#   2. configure_primary_key()   - 配置主键策略（可选）
#   3. init_versioning()         - 初始化版本化功能
# 这样确保历史表能正确继承动态主键类型
class CoreModel(IdModel):
    """ORM基础模型类
    
    继承自 IdModel，提供功能：
    - 动态主键字段（继承自 IdModel）
    - 自动表名生成（驼峰转下划线）
    - 常用CRUD操作方法
    - 分页查询支持
    - 批量操作方法
    - 数据序列化方法
    - 支持 Django 风格的 ForeignKeyField
    
    使用示例:
        from yweb.orm import BaseModel, init_database
        
        # 初始化数据库
        init_database("sqlite:///./test.db")
        
        # 定义模型
        class User(BaseModel):
            __tablename__ = "user"  # 可选，不指定则自动生成
            
            username: Mapped[str] = mapped_column(String(50), unique=True)
            email: Mapped[str] = mapped_column(String(100))
            is_active: Mapped[bool] = mapped_column(default=True)
        
        # 使用
        user = User(username="tom", email="tom@example.com")
        user.save()
        
    关系字段示例（Django 风格）:
        
        from yweb.orm import fields
        
        # 一对一关系
        class UserProfile(BaseModel):
            bio: Mapped[str] = mapped_column(String(500))
            user = fields.OneToOne(User, on_delete=fields.DELETE)
            # → user_id 列 + user relationship + User.user_profile backref
        
        # 多对一关系（外键）
        class OrderItem(BaseModel):
            order = fields.ManyToOne(Order, on_delete=fields.DELETE)
            # → order_id 列 + order relationship + Order.order_items backref
        
        # 多对多关系（自动创建中间表）
        class User(BaseModel):
            roles = fields.ManyToMany(Role, on_delete=fields.UNLINK)
            # → user_roles 中间表 + roles relationship + Role.users backref
        
        # on_delete 常量：
        # fields.DELETE     → 级联删除子记录
        # fields.SET_NULL   → 设置外键为空
        # fields.PROTECT    → 有子记录时禁止删除
        # fields.UNLINK     → 解除多对多关联
        # fields.DO_NOTHING → 不处理
        
        # backref 参数：
        # backref=True      → 自动生成名称（一对一用单数，其他用复数）
        # backref="name"    → 自定义名称
        # backref=False     → 不创建反向引用
    """
    __abstract__ = True
    
    # 允许非 Mapped[] 的类型注解（如 HasMany, HasOne 类型标记）
    __allow_unmapped__ = True

    
    # 控制是否启用历史记录（子类可覆盖）
    enable_history: ClassVar[bool] = False
    
    def __init_subclass__(cls, **kwargs):
        """子类初始化钩子
        
        处理 ForeignKeyField 和 ManyToManyField 定义，自动创建外键列、中间表和关系
        """
        super().__init_subclass__(**kwargs)

        # 只在非抽象类上处理
        # 注意：不能用 getattr(cls, '__abstract__', False)，因为这会继承父类的值
        # SQLAlchemy 中，如果子类定义了 __tablename__，即使父类是抽象的，子类也是具体类
        # 正确的判断方法：检查类自身是否声明为抽象，或者没有定义 __tablename__
        is_abstract = cls.__dict__.get('__abstract__', False)
        has_tablename = '__tablename__' in cls.__dict__ or hasattr(cls, '__tablename__')
        
        # 如果类自身声明为抽象，或者没有表名（真正的抽象基类），则跳过
        if is_abstract or (not has_tablename and getattr(cls, '__abstract__', False)):
            return
        
        
        # 延迟导入，避免循环依赖
        from .fields import (
            process_relationship_fields,
            _OneToOneConfig, _ManyToOneConfig, _ManyToManyConfig,
        )
        
        # 检查是否有 fields.* 字段需要处理
        # 除了类自身，还需要扫描 Mixin / abstract 基类
        # （它们的字段不会被自身处理，需要在具体子类中处理）
        # 跳过已有 __tablename__ 的具体模型基类（它们创建时已处理过自己的字段）
        has_relationship_fields = False
        for klass in cls.__mro__:
            if klass is object:
                continue
            if klass is not cls and '__tablename__' in klass.__dict__:
                continue
            if any(
                isinstance(v, (_OneToOneConfig, _ManyToOneConfig, _ManyToManyConfig))
                for v in vars(klass).values()
            ):
                has_relationship_fields = True
                break
        
        if has_relationship_fields:
            process_relationship_fields(cls)

        # 如果子类设置了 enable_history = True，自动添加 __versioned__
        if getattr(cls, 'enable_history', False):
            # 检查版本化是否已初始化
            if not is_versioning_initialized():
                import warnings
                warnings.warn(
                    f"定义 {cls.__name__} 时 versioning 尚未初始化。"
                    f"请在定义模型之前调用 init_versioning()。"
                    f"否则版本历史功能可能无法正常工作。",
                    UserWarning
                )
            if not hasattr(cls, '__versioned__'):
                cls.__versioned__ = {}
    
    # 注意：query 属性需要在 init_database 后通过 scoped_session.query_property() 设置
    # 类型标注仅在 TYPE_CHECKING 时生效，运行时由 init_database() 动态设置
    if TYPE_CHECKING:
        query: ClassVar[Query[Self]]
    
    _session: Session = None
    
    # 自动根据类名创建表名
    @declared_attr.directive
    def __tablename__(cls) -> str:
        """驼峰命名转下划线（支持 E2E、API 等缩写）"""
        name = cls.__name__
        if '_' in name:
            raise ValueError(f'{name}字符中包含下划线，无法转换')
        return to_snake_case(name)
    
    # 时间戳字段
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), 
        server_default=func.now(),
        comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), 
        nullable=True,
        onupdate=func.now(),
        comment="更新时间"
    )
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), 
        nullable=True,
        default=None,
        comment="删除时间（软删除标记）"
    )
    
    # 版本控制字段
    ver: Mapped[int] = mapped_column(Integer, default=1, nullable=False, comment="版本号")
    
    # 系统字段列表（构造时自动忽略这些字段）
    _system_fields: ClassVar[set] = {'id', 'created_at', 'updated_at', 'deleted_at', 'ver'}
    
    def __init__(self, **kwargs):
        """初始化模型实例
        
        自动忽略系统字段（id, created_at, updated_at, deleted_at, ver），
        这些字段由系统自动管理，用户传入的值会被静默忽略。
        """
        # 移除系统字段，防止用户手动设置
        for field in self._system_fields:
            kwargs.pop(field, None)
        super().__init__(**kwargs)
    __mapper_args__ = {"version_id_col": ver}
    
    def __repr__(self):
        return f"<{self.__class__.__name__} id={self.id}>"
    
    def __getattribute__(self, name):
        """属性访问拦截器
        
        当访问 id 属性时，如果 id 为 None 且对象处于 pending 状态，
        自动触发 flush 以获取主键 ID。
        
        主键生成时机（都在 flush 过程中）：
        - 自增主键：数据库 INSERT 时生成
        - 非自增主键（UUID、雪花算法等）：before_insert 事件中生成
        
        这样用户无需手动调用 flush() 或 save(commit=True) 就能获取 ID：
        
            user = User(name="张三")
            user.save()
            print(user.id)  # 自动 flush，立即可用
        """
        value = super().__getattribute__(name)
        
        # 只拦截 id 属性访问
        if name == 'id' and value is None:
            try:
                # 获取 SQLAlchemy 实例状态
                state = super().__getattribute__('_sa_instance_state')
                session = state.session
                # 如果对象在 session 的 new 集合中（pending 状态），且 session 未在 flushing
                # 注意：必须检查 _flushing 标志，避免在 flush 过程中（如 before_insert 事件）再次 flush
                if session is not None and state.pending and not session._flushing:
                    session.flush()
                    # flush 后重新获取 id 值
                    return super().__getattribute__(name)
            except (AttributeError, KeyError):
                # 对象可能还没有 _sa_instance_state（未添加到 session）
                pass
        
        return value
    
    @property
    def session(self) -> Session:
        """获取当前session
        
        优先从 query 属性获取 session，如果不可用则从全局 scoped_session 获取
        """
        if self._session is None:
            # 优先从 query 获取 session（支持测试环境）
            if self.__class__.query is not None:
                self._session = self.__class__.query.session
            else:
                from .db_session import db_manager
                self._session = db_manager.get_session()
        return self._session
    
    # ==================== CRUD 操作方法 ====================
    
    def save(self, commit: bool = False) -> Self:
        """保存对象（自动判断新增或更新）
        
        对于新对象或分离的对象，会添加到 session；
        对于已在 session 中的对象，add 操作是幂等的，不会重复添加。
        SQLAlchemy 会自动追踪 persistent 对象的变化。
        
        Args:
            commit: 是否立即提交，默认False
                   - 无事务时：执行 session.commit()
                   - 有事务时：commit 被抑制，但会自动 flush 以获取自动生成字段
        
        Returns:
            self: 返回自身，支持链式调用
        """
        # session.add() 是幂等的，对已在 session 中的对象调用是安全的
        self.session.add(self)
        self.__is_commit(commit)
        return self
    
    def add(self, commit: bool = False) -> Self:
        """添加对象到session
        
        .. deprecated::
            建议使用 save() 方法，add() 将在未来版本中移除。
            save() 语义更清晰，表示"保存对象（新增或更新）"。
        
        Args:
            commit: 是否立即提交，默认False
        
        Returns:
            self: 返回自身，支持链式调用
        """
        return self.save(commit)
    
    @classmethod
    def save_all(cls, objects: list, commit: bool = False):
        """批量保存对象（新增或更新）
        
        SQLAlchemy 的 session.add() 对已存在的对象是幂等的，
        所以此方法可同时用于批量新增和批量更新。
        
        Args:
            objects: 对象列表
            commit: 是否立即提交，默认False
            
        Returns:
            保存的对象列表
        """
        if not objects:
            return objects
        cls.query.session.add_all(objects)
        cls.__cls_commit(commit)
        return objects
    
    @classmethod
    def add_all(cls, objects: list, commit: bool = False):
        """批量添加对象到session
        
        .. deprecated::
            建议使用 save_all() 方法，add_all() 将在未来版本中移除。
        
        Args:
            objects: 对象列表
            commit: 是否立即提交，默认False
            
        Returns:
            添加的对象列表
        """
        return cls.save_all(objects, commit)
    
    @classmethod
    def delete_all(cls, objects: list, commit: bool = False):
        """批量删除对象
        
        Args:
            objects: 对象列表
            commit: 是否立即提交，默认False
        """
        if not objects:
            return
        for obj in objects:
            cls.query.session.delete(obj)
        cls.__cls_commit(commit)
    
    def update(self, commit: bool = False, **kwargs) -> Self:
        """更新对象属性
        
        支持两种使用方式：
        1. 先修改属性，再调用 update()：
           user.name = "new_name"
           user.update(commit=True)
           
        2. 通过 kwargs 直接更新属性：
           user.update(name="new_name", age=25, commit=True)
        
        Args:
            commit: 是否立即提交，默认False
            **kwargs: 要更新的属性键值对
            
        Returns:
            self: 返回自身，支持链式调用
        """
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.__is_commit(commit)
        return self
    
    @classmethod
    def update_all(cls, objects: list, commit: bool = False, **kwargs):
        """批量更新对象
        
        支持两种使用方式：
        1. 对象已修改属性，只需触发提交：
           for user in users:
               user.name = "new_name"
           User.update_all(users, commit=True)
           
        2. 通过 kwargs 批量设置相同属性：
           User.update_all(users, status="active", commit=True)
        
        Args:
            objects: 对象列表
            commit: 是否立即提交，默认False
            **kwargs: 要批量更新的属性键值对（所有对象设置相同值）
            
        Returns:
            更新的对象列表
        """
        if not objects:
            return objects
        if kwargs:
            for obj in objects:
                for key, value in kwargs.items():
                    if hasattr(obj, key):
                        setattr(obj, key, value)
        cls.__cls_commit(commit)
        return objects
    
    def delete(self, commit: bool = False):
        """删除对象"""
        self.session.delete(self)
        self.__is_commit(commit)
    
    def refresh(self, attribute_names: list = None) -> Self:
        """从数据库重新加载对象状态
        
        用于在 commit 后刷新对象，确保获取数据库中的最新数据。
        
        ⚠️ 注意事项：
        -----------
        1. **优先使用单次提交模式**：大多数场景下，应该将所有相关操作放在
           同一个事务中一次性提交，而不是多次 commit 后再 refresh。
           
        2. **refresh 会产生额外查询**：每次调用都会执行一次 SELECT，
           批量操作时注意性能影响。
           
        3. **典型使用场景**（需要 refresh 的特殊情况）：
           - 需要获取数据库触发器/默认值生成的字段
           - 需要在 commit 后继续操作对象的关系属性
           - 长事务中需要获取其他事务提交的最新数据
        
        Args:
            attribute_names: 可选，指定要刷新的属性列表。
                            如果不指定，则刷新所有属性。
        
        Returns:
            self: 返回自身，支持链式调用
        
        使用示例::
        
            # ✅ 推荐：单次提交模式（不需要 refresh）
            role = Role(name="admin")
            user = User(name="test")
            user.roles.append(role)  # 都是新对象，直接关联
            session.add_all([role, user])
            session.commit()  # 一次性提交
            
            # ⚠️ 特殊场景：需要 refresh
            role.save(commit=True)
            role.refresh()  # 刷新后再操作
            user.roles.append(role)
            user.save(commit=True)
            
            # 链式调用
            role.save(True).refresh()
            
            # 只刷新特定属性
            user.refresh(['name', 'updated_at'])
        """
        if attribute_names:
            self.session.refresh(self, attribute_names)
        else:
            self.session.refresh(self)
        return self
    
    @classmethod
    def refresh_all(cls, objects: list, attribute_names: list = None):
        """批量从数据库重新加载对象状态
        
        ⚠️ 注意事项：
        -----------
        1. **优先使用单次提交模式**：将所有对象在同一事务中一次性提交，
           避免需要 refresh 的情况。
           
        2. **性能警告**：此方法会对每个对象执行一次 SELECT 查询。
           例如 refresh_all(100个对象) = 100 次数据库查询。
           批量操作时请谨慎使用。
        
        Args:
            objects: 对象列表
            attribute_names: 可选，指定要刷新的属性列表
        
        Returns:
            刷新后的对象列表
        
        使用示例::
        
            # ✅ 推荐：单次提交模式（不需要 refresh_all）
            roles = [Role(name="admin"), Role(name="user")]
            user = User(name="test")
            user.roles.extend(roles)  # 都是新对象，直接关联
            session.add_all(roles + [user])
            session.commit()
            
            # ⚠️ 特殊场景：需要 refresh_all
            Role.save_all(roles, commit=True)
            Role.refresh_all(roles)  # 刷新后再操作
            user.roles.extend(roles)
            user.save(commit=True)
        """
        if not objects:
            return objects
        session = cls.query.session
        for obj in objects:
            if attribute_names:
                session.refresh(obj, attribute_names)
            else:
                session.refresh(obj)
        return objects
    
    def update_properties(self, **kwargs) -> Self:
        """批量更新属性
        
        .. deprecated::
            建议使用 update(**kwargs) 方法，update_properties() 将在未来版本中移除。
            update() 方法功能更完整，支持同时更新属性和提交。
        
        Returns:
            self: 返回自身，支持链式调用
        """
        return self.update(**kwargs)
    
    def update_with_foreign_key_none(self, commit: bool = False) -> Self:
        """设置当前对象的外键=None时，调用此方法
        
        防止在事件监听中被误认为是软删除
        
        Returns:
            self: 返回自身，支持链式调用
        """
        self.with_foreign_key_none = True
        self.__is_commit(commit)
        return self
    
    @classmethod
    def get(cls, id: int):
        """根据ID获取对象，不存在返回None"""
        obj = cls.query.filter_by(id=id)
        if obj.count()>1:
            raise ValueError(f"{cls.__name__}【{id}】：找到多条数据，请检查主键是否唯一")
        if obj.count()==0:
            return None
        return obj.first()
    
    @classmethod    
    def get_list_by_conditions(cls, conditions: dict):
        """根据条件获取列表"""
        return cls.query.filter_by(**conditions).all()
    
    @classmethod
    def get_all(cls):
        """获取所有记录"""
        return cls.query.all()
    
    # ==================== 历史记录方法 ====================
    
    def _check_history_enabled(self):
        """检查是否启用了历史记录功能"""
        if not getattr(self.__class__, 'enable_history', False):
            raise AttributeError(
                f"{self.__class__.__name__} 未启用历史记录功能。"
                f"请设置 enable_history = True 并确保已调用 init_versioning()"
            )
    
    def get_history(
        self,
        version: Optional[int] = None,
        limit: int = 100,
        field_names: Optional[List[str]] = None
    ):
        """获取当前实例的历史记录
        
        Args:
            version: 可选，指定版本号。None 表示获取所有版本
            limit: 返回的最大记录数，默认 100
            field_names: 可选，只返回指定字段。None 表示返回所有字段
        
        Returns:
            历史记录列表（字典格式），按版本号降序排列
            如果没有历史记录，返回 None
        
        使用示例:
            doc = DocumentModel.query.filter_by(id=1).first()
            
            # 获取所有历史记录
            history = doc.get_history()
            
            # 获取特定版本
            history = doc.get_history(version=5)
            
            # 只获取特定字段
            history = doc.get_history(field_names=['title', 'content', 'ver'])
        """
        self._check_history_enabled()
        from .history.history_helper import get_history as _get_history
        return _get_history(
            self.__class__,
            self.id,
            version=version,
            limit=limit,
            session=self.session,
            field_names=field_names
        )
    
    @property
    def history(self):
        """便捷属性：获取所有历史记录
        
        使用示例:
            doc = DocumentModel.query.filter_by(id=1).first()
            for record in doc.history:
                print(f"版本 {record['ver']}: {record['title']}")
        """
        return self.get_history()
    
    @property
    def history_count(self) -> int:
        """获取历史记录数量
        
        使用示例:
            doc = DocumentModel.query.filter_by(id=1).first()
            print(f"共有 {doc.history_count} 个历史版本")
        """
        self._check_history_enabled()
        from .history.history_helper import get_history_count as _get_history_count
        return _get_history_count(self.__class__, self.id, session=self.session)
    
    def get_history_diff(
        self,
        from_version: int,
        to_version: int,
        exclude_fields: Optional[set] = None
    ):
        """比较两个版本之间的差异
        
        Args:
            from_version: 起始版本号
            to_version: 目标版本号
            exclude_fields: 要排除的字段集合
        
        Returns:
            差异字典，格式: {"field_name": {"from": old_value, "to": new_value}}
            如果版本不存在，返回 None
        
        使用示例:
            doc = DocumentModel.query.filter_by(id=1).first()
            diff = doc.get_history_diff(1, 3)
            for field, change in diff.items():
                print(f"{field}: {change['from']} -> {change['to']}")
        """
        self._check_history_enabled()
        from .history.history_helper import get_history_diff as _get_history_diff
        return _get_history_diff(
            self.__class__,
            self.id,
            from_version,
            to_version,
            session=self.session,
            exclude_fields=exclude_fields
        )
    
    def get_field_text_diff(
        self,
        field_name: str,
        from_version: int,
        to_version: int,
        output_format: str = "unified",
        context_lines: int = 3
    ):
        """获取单个字段的文本细节差异
        
        使用 difflib 对比两个版本之间某个字段的文本内容变化，
        适合文章内容、配置文本等长文本的精确对比。
        
        Args:
            field_name: 要对比的字段名
            from_version: 起始版本号
            to_version: 目标版本号
            output_format: 输出格式 ("unified", "inline", "html", "opcodes")
            context_lines: 上下文行数，默认 3
        
        Returns:
            差异字典，包含 diff 结果和统计信息
        
        使用示例:
            doc = DocumentModel.query.filter_by(id=1).first()
            
            # 获取 unified diff（类似 git diff）
            detail = doc.get_field_text_diff("content", 1, 3)
            print(detail["diff"])
            
            # 获取 HTML 格式
            detail = doc.get_field_text_diff("content", 1, 3, output_format="html")
        """
        self._check_history_enabled()
        from .history.history_helper import get_field_text_diff as _get_field_text_diff
        return _get_field_text_diff(
            self.__class__,
            self.id,
            field_name,
            from_version,
            to_version,
            session=self.session,
            output_format=output_format,
            context_lines=context_lines
        )
    
    def restore_to_version(
        self,
        version: int,
        exclude_fields: Optional[set] = None
    ):
        """恢复当前实例到指定版本
        
        此方法会从历史记录中读取指定版本的数据，并更新当前实例。
        
        Args:
            version: 要恢复到的版本号
            exclude_fields: 恢复时要排除的字段
        
        Returns:
            更新后的实例对象（self）
            如果版本不存在，返回 None
        
        使用示例:
            doc = DocumentModel.query.filter_by(id=1).first()
            doc.restore_to_version(2)
            session.commit()
        
        注意事项:
            - 此操作会创建一条新的历史记录
            - 排除字段默认包含: id, ver, version, created_at 等
        """
        self._check_history_enabled()
        from .history.history_helper import restore_to_version as _restore_to_version
        return _restore_to_version(
            self.__class__,
            self.id,
            version,
            session=self.session,
            exclude_fields=exclude_fields
        )
    
    @classmethod
    def get_history_by_id(
        cls,
        instance_id: int,
        version: Optional[int] = None,
        limit: int = 100,
        session: Optional[Session] = None,
        field_names: Optional[List[str]] = None
    ):
        """根据 ID 获取历史记录（类方法，不需要先获取实例）
        
        Args:
            instance_id: 实例 ID
            version: 可选，指定版本号
            limit: 返回的最大记录数
            session: 可选的数据库会话
            field_names: 可选，只返回指定字段
        
        Returns:
            历史记录列表
        
        使用示例:
            # 不需要先查询实例
            history = DocumentModel.get_history_by_id(doc_id)
        """
        if not getattr(cls, 'enable_history', False):
            raise AttributeError(
                f"{cls.__name__} 未启用历史记录功能。"
                f"请设置 enable_history = True 并确保已调用 init_versioning()"
            )
        from .history.history_helper import get_history as _get_history
        _session = session or (cls.query.session if cls.query else None)
        return _get_history(cls, instance_id, version, limit, _session, field_names)
    
    @classmethod
    def get_history_count_by_id(
        cls,
        instance_id: int,
        session: Optional[Session] = None
    ) -> int:
        """根据 ID 获取历史记录数量（类方法）
        
        Args:
            instance_id: 实例 ID
            session: 可选的数据库会话
        
        Returns:
            历史记录数量
        """
        if not getattr(cls, 'enable_history', False):
            raise AttributeError(f"{cls.__name__} 未启用历史记录功能")
        from .history.history_helper import get_history_count as _get_history_count
        _session = session or (cls.query.session if cls.query else None)
        return _get_history_count(cls, instance_id, session=_session)
    
    # ==================== 序列化方法 ====================
    
    def to_dict(self, exclude: set = None) -> dict:
        """转换为字典
        
        Args:
            exclude: 需要排除的字段集合
            
        Returns:
            字典格式的对象数据
        """
        exclude = exclude or set()
        return {
            c.key: getattr(self, c.key)
            for c in inspect(self).mapper.column_attrs
            if c.key not in exclude
        }
    
    def to_dict_with_relations(self, relations: list = None, exclude: set = None) -> dict:
        """转换为字典（包含关联对象）
        
        Args:
            relations: 需要包含的关联属性名列表
            exclude: 需要排除的字段集合
            
        Returns:
            包含关联数据的字典
        """
        data = self.to_dict(exclude=exclude)
        
        for rel_name in (relations or []):
            rel_obj = getattr(self, rel_name, None)
            if rel_obj is not None:
                if isinstance(rel_obj, list):
                    data[rel_name] = [
                        item.to_dict(exclude=exclude) if hasattr(item, 'to_dict') else item
                        for item in rel_obj
                    ]
                elif hasattr(rel_obj, 'to_dict'):
                    data[rel_name] = rel_obj.to_dict(exclude=exclude)
                else:
                    data[rel_name] = rel_obj
            else:
                data[rel_name] = None
        
        return data
    
    # ==================== 跨请求/异步任务安全方法 ====================
    
    def detach(self) -> Self:
        """将对象从session中完全分离，使其可以跨请求安全访问已加载的属性
        
        工作原理：
        1. 首先强制加载所有列属性（防止分离后访问时报错）
        2. 将对象从当前session中移除（expunge）
        3. 标记对象为"已分离"状态（make_transient_to_detached）
        
        与 to_dict() 的区别：
        - to_dict() 返回普通字典，丢失了ORM对象的类型信息和方法
        - detach() 保留ORM对象本身，可以继续使用对象的方法和类型检查
        - detach() 后的对象可以用 session.merge() 重新关联到新session
        
        使用场景：
        - 需要保留ORM对象类型的场景
        - 需要在其他请求中通过merge()重新关联session的场景
        - 缓存ORM对象的场景
        
        注意事项：
        - 分离后无法访问未加载的关联属性（会报DetachedInstanceError）
        - 如需访问关联数据，请先使用joinedload预加载，或在分离前访问一次
        - 分离后对对象的修改不会自动同步到数据库
        
        Returns:
            self: 返回自身，支持链式调用
        
        示例:
            user = User.get(1)
            user.detach()  # 分离对象
            
            # 现在可以跨请求安全访问
            print(user.name)  # 正常工作
            
            # 在其他请求中重新关联
            new_session.merge(user)
        """
        from sqlalchemy.orm import make_transient_to_detached
        from sqlalchemy.orm.session import object_session
        
        # 获取当前对象绑定的session
        session = object_session(self)
        
        if session:
            # 强制加载所有列属性，防止分离后访问报错
            for attr in inspect(self).mapper.column_attrs:
                try:
                    getattr(self, attr.key, None)
                except Exception:
                    pass
            
            # 从session中移除对象
            session.expunge(self)
        
        # 将对象标记为detached状态
        make_transient_to_detached(self)
        
        return self
    
    def detach_with_relations(self, relations: list = None) -> Self:
        """分离对象及其指定的关联对象
        
        Args:
            relations: 需要一并分离的关联属性名列表
        
        Returns:
            self: 返回自身，支持链式调用
        
        示例:
            user = User.query.options(joinedload(User.roles)).filter_by(id=1).first()
            user.detach_with_relations(relations=['roles'])
            
            # 现在可以安全访问关联数据
            for role in user.roles:
                print(role.name)
        """
        # 先分离当前对象
        self.detach()
        
        # 分离指定的关联对象
        for rel_name in (relations or []):
            rel_obj = getattr(self, rel_name, None)
            if rel_obj is not None:
                if isinstance(rel_obj, list):
                    for item in rel_obj:
                        if hasattr(item, 'detach'):
                            item.detach()
                elif hasattr(rel_obj, 'detach'):
                    rel_obj.detach()
        
        return self
    
    # ==================== 分页查询 ====================
    
    @classmethod
    def paginate(
        cls,
        query_or_stmt,
        page: int = 1,
        page_size: int = 10,
        max_page_size: int = 100,
        schema: Optional[Type[T]] = None
    ) -> Page:
        """分页查询
        
        Args:
            query_or_stmt: Query对象或Select语句
            page: 页码
            page_size: 每页数量
            max_page_size: 最大页大小
            schema: 可选的Pydantic schema
            
        Returns:
            Page分页对象
            
        使用示例:
            # Query对象分页
            page_result = User.query.filter_by(is_active=True).paginate(page=1, page_size=10)
            
            # Select语句分页
            stmt = select(User).where(User.is_active == True)
            page_result = User.paginate(stmt, page=1, page_size=10)
        """
        # 参数规范化
        page = max(page, 1)
        page_size = max(1, min(page_size, max_page_size))
        
        from sqlalchemy.orm.query import Query
        from sqlalchemy.sql.selectable import Select
        
        if isinstance(query_or_stmt, Query):
            # 处理Query对象
            query = query_or_stmt
            total = query.count()
            total_pages = math.ceil(total / page_size) if total > 0 else 0
            items = query.offset((page - 1) * page_size).limit(page_size).all()
            
        elif isinstance(query_or_stmt, Select):
            # 处理Select语句
            stmt = query_or_stmt
            
            # 获取总数
            count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
            total = cls.query.session.scalar(count_stmt) or 0
            total_pages = math.ceil(total / page_size) if total > 0 else 0
            
            # 执行分页查询
            pagination_stmt = stmt.offset((page - 1) * page_size).limit(page_size)
            result = cls.query.session.execute(pagination_stmt)
            
            # 智能数据转换
            column_keys = result.keys()
            if len(column_keys) == 1:
                raw_data = result.scalars().unique().all()
            else:
                raw_data = result.mappings().all()
            
            items = []
            for item in raw_data:
                if schema:
                    items.append(schema.model_validate(item))
                else:
                    items.append(item)
        else:
            raise TypeError(f"不支持的参数类型: {type(query_or_stmt)}")
        
        return Page(
            rows=items,
            total_records=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    
    @classmethod
    def _add_paginate_to_query(cls):
        """为Query对象添加paginate方法"""
        from sqlalchemy.orm.query import Query
        
        def paginate_method(self, page: int = 1, page_size: int = 10, max_page_size: int = 100, schema=None):
            """Query对象的paginate方法"""
            model_class = self.column_descriptions[0]['type'] if self.column_descriptions else None
            if model_class and hasattr(model_class, 'paginate'):
                return model_class.paginate(self, page=page, page_size=page_size, max_page_size=max_page_size, schema=schema)
            else:
                # 回退到通用分页逻辑
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
        
        if not hasattr(Query, 'paginate'):
            Query.paginate = paginate_method
    
    # ==================== 批量操作方法 ====================
    
    @classmethod
    def bulk_update(cls, filters: dict, values: dict, commit: bool = False) -> int:
        """批量更新数据
        
        Args:
            filters: 过滤条件字典
            values: 要更新的字段和值
            commit: 是否自动提交
            
        Returns:
            受影响的行数
        """
        stmt = update(cls)
        for key, value in filters.items():
            column = getattr(cls, key, None)
            if column is not None:
                stmt = stmt.where(column == value)
        
        stmt = stmt.values(**values)
        result = cls.query.session.execute(stmt)
        rowcount = result.rowcount
        cls.__cls_commit(commit)
        return rowcount
    
    @classmethod
    def bulk_update_by_ids(cls, ids: list, values: dict, commit: bool = False) -> int:
        """根据ID列表批量更新"""
        if not ids:
            return 0
        
        stmt = update(cls).where(cls.id.in_(ids)).values(**values)
        result = cls.query.session.execute(stmt)
        rowcount = result.rowcount
        cls.__cls_commit(commit)
        return rowcount
    
    @classmethod
    def bulk_delete(cls, filters: dict, commit: bool = False) -> int:
        """批量删除数据（物理删除）
        
        ⚠️ 警告：此操作会永久删除数据！
        """
        stmt = delete(cls)
        for key, value in filters.items():
            column = getattr(cls, key, None)
            if column is not None:
                stmt = stmt.where(column == value)
        
        result = cls.query.session.execute(stmt)
        rowcount = result.rowcount
        cls.__cls_commit(commit)
        return rowcount
    
    @classmethod
    def bulk_delete_by_ids(cls, ids: list, commit: bool = False) -> int:
        """根据ID列表批量删除"""
        if not ids:
            return 0
        
        stmt = delete(cls).where(cls.id.in_(ids))
        result = cls.query.session.execute(stmt)
        rowcount = result.rowcount
        cls.__cls_commit(commit)
        return rowcount
    
    # ==================== 软删除方法（可选） ====================
    
    @classmethod
    def bulk_soft_delete(cls, filters: dict, commit: bool = False) -> int:
        """批量软删除（设置deleted_at）"""
        return cls.bulk_update(
            filters=filters,
            values={'deleted_at': datetime.now().isoformat()},
            commit=commit
        )
    
    @classmethod
    def bulk_soft_delete_by_ids(cls, ids: list, commit: bool = False) -> int:
        """根据ID列表批量软删除"""
        return cls.bulk_update_by_ids(
            ids=ids,
            values={'deleted_at': datetime.now().isoformat()},
            commit=commit
        )
    
    # ==================== 软删除清理方法 ====================
    
    @classmethod
    def cleanup_soft_deleted(cls, days: int = None, commit: bool = False) -> int:
        """清理软删除的数据（将软删除的记录物理删除）
        
        功能：
        - 查找所有 deleted_at 不为空的记录
        - 可选：只删除软删除超过指定天数的记录
        - 物理删除这些记录，释放数据库空间
        
        ⚠️ 警告：此操作会永久删除数据，无法恢复！
        
        Args:
            days: 可选，只删除软删除超过N天的记录
                  - None: 删除所有软删除的记录
                  - 30: 只删除软删除超过30天的记录
            commit: 是否自动提交，默认True
        
        Returns:
            受影响的行数
        
        示例:
            # 删除所有软删除的记录
            count = User.cleanup_soft_deleted()
            
            # 只删除软删除超过30天的记录
            count = User.cleanup_soft_deleted(days=30)
        """
        from datetime import timedelta
        
        stmt = delete(cls).where(cls.deleted_at.isnot(None))
        
        if days is not None and days > 0:
            threshold = datetime.now() - timedelta(days=days)
            stmt = stmt.where(cls.deleted_at < threshold.isoformat())
        
        result = cls.query.session.execute(stmt)
        rowcount = result.rowcount
        cls.__cls_commit(commit)
        return rowcount
    
    @classmethod
    def cleanup_all_soft_deleted(cls, days: int = None, commit: bool = False) -> dict:
        """清理所有继承BaseModel的表中的软删除数据
        
        功能：
        - 遍历所有继承BaseModel的子类
        - 对每个子类执行cleanup_soft_deleted
        - 返回每个表清理的记录数
        
        ⚠️ 警告：此操作会永久删除所有表中的软删除数据！
        
        Args:
            days: 可选，只删除软删除超过N天的记录
            commit: 是否自动提交，默认True
        
        Returns:
            字典，key为表名，value为删除的记录数
        
        示例:
            result = BaseModel.cleanup_all_soft_deleted(days=30)
            for table, count in result.items():
                if count > 0:
                    print(f"{table}: 清理了 {count} 条记录")
        """
        result = {}
        
        for subclass in cls.__subclasses__():
            if not hasattr(subclass, '__tablename__'):
                continue
            
            try:
                table_name = subclass.__tablename__
                count = subclass.cleanup_soft_deleted(days=days, commit=commit)
                result[table_name] = count
            except Exception as e:
                result[subclass.__name__] = f"Error: {str(e)}"
        
        return result
    
    @classmethod
    def get_soft_deleted_count(cls, days: int = None) -> int:
        """获取软删除数据的数量（不删除，仅统计）
        
        用途：
        - 在执行清理前预览将要删除的数据量
        - 监控软删除数据的积累情况
        
        Args:
            days: 可选，只统计软删除超过N天的记录
        
        Returns:
            软删除数据的数量
        
        示例:
            count = User.get_soft_deleted_count()
            print(f"共有 {count} 条软删除记录")
            
            count = User.get_soft_deleted_count(days=30)
            print(f"有 {count} 条记录软删除超过30天")
        """
        from datetime import timedelta
        
        count_query = cls.query.session.query(func.count(cls.id)).filter(
            cls.deleted_at.isnot(None)
        )
        
        if days is not None and days > 0:
            threshold = datetime.now() - timedelta(days=days)
            count_query = count_query.filter(cls.deleted_at < threshold.isoformat())
        
        return count_query.scalar() or 0
    
    def __is_commit(self, commit=False):
        """实例方法：根据参数决定是否提交
        
        当在事务上下文中且启用了提交抑制时，commit=True 会被忽略，
        但会自动执行 flush 以获取自动生成的字段（id, created_at 等）。
        """
        if commit:
            # 检查是否应该抑制提交
            if self._should_suppress_commit():
                # 被抑制时，自动 flush 以获取自动生成字段
                self.session.flush()
                self.session.refresh(self)
                return
            self.session.commit()
    
    @classmethod
    def __cls_commit(cls, commit=False):
        """类方法：根据参数决定是否提交
        
        当在事务上下文中且启用了提交抑制时，commit=True 会被忽略。
        """
        if commit:
            # 检查是否应该抑制提交
            if cls._cls_should_suppress_commit():
                return
            cls.query.session.commit()
    
    def _should_suppress_commit(self) -> bool:
        """检查是否应该抑制提交（实例方法）"""
        try:
            from .transaction import get_current_transaction
            tx = get_current_transaction()
            if tx is not None and tx.should_suppress_commit():
                from yweb.log import get_logger
                logger = get_logger("orm.transaction")
                logger.debug("commit=True 被事务上下文抑制")
                return True
        except ImportError:
            pass
        return False
    
    @classmethod
    def _cls_should_suppress_commit(cls) -> bool:
        """检查是否应该抑制提交（类方法）"""
        try:
            from .transaction import get_current_transaction
            tx = get_current_transaction()
            if tx is not None and tx.should_suppress_commit():
                from yweb.log import get_logger
                logger = get_logger("orm.transaction")
                logger.debug("commit=True 被事务上下文抑制")
                return True
        except ImportError:
            pass
        return False


# 在模块加载时为Query对象添加paginate方法
CoreModel._add_paginate_to_query()



# ==================== 事件监听器 ====================

@event.listens_for(CoreModel, 'before_delete', propagate=True)
def event_before_delete(mapper, connection, target):
    """在删除前设置软删除时间戳
    
    处理场景：主子表关系中，通过 relationship 的 cascade 删除子表记录时，
    session.delete() 会在 soft_delete_hook.py 的 before_flush 中拦截，
    而这里处理的是通过 relationship 配置的级联删除（如 delete-orphan）。
    """
    target.deleted_at = datetime.now().isoformat()
    
    # 检查是否有 delete_orphan 配置（软删除模式下不支持）
    for rel_name, rel in inspect(target.__class__).relationships.items():
        if rel.cascade.delete_orphan:
            raise Exception(
                f"{target.__class__.__name__} 类的relationship配置有误，"
                f"软删除模式下暂不支持delete_orphan"
            )


@event.listens_for(CoreModel, 'before_update', propagate=True)
def event_before_update(mapper, connection, target):
    """在更新前检查外键变更，实现子表记录的软删除
    
    处理场景：当执行 user.addresses.remove(address) 时，
    SQLAlchemy 默认会把 address.user_id 设为 None。
    本事件拦截此行为，改为：保留原外键值 + 设置 deleted_at（软删除）
    
    注意：只有当对象没有设置 with_foreign_key_none 标志时才会触发软删除
    """
    # 如果明确设置了允许外键为None，跳过软删除处理
    if hasattr(target, 'with_foreign_key_none') and target.with_foreign_key_none:
        return
    
    # 获取主键名称
    primary_key_names = [column.name for column in mapper.primary_key]
    if not primary_key_names:
        return
    
    # 获取外键名称
    foreign_key_names = [
        foreign_key.name 
        for relationship in mapper.relationships 
        for foreign_key in relationship._calculated_foreign_keys
    ]
    if not foreign_key_names:
        return
    
    # 检查哪些外键被设置为None
    target_columns = [column.name for column in inspect(target).mapper.columns]
    foreign_keys_set_to_none = []
    foreign_keys_in_target = []
    
    for col_name in target_columns:
        if col_name in foreign_key_names:
            foreign_keys_in_target.append(col_name)
            try:
                if getattr(target, col_name) is None:
                    foreign_keys_set_to_none.append(col_name)
            except Exception:
                continue
    
    # 如果没有外键被设置为None，或者只有部分外键被设置为None，不处理
    if not foreign_keys_set_to_none:
        return
    if len(foreign_keys_in_target) != len(foreign_keys_set_to_none):
        return
    
    # 获取提交前的外键值
    committed_state = inspect(target).committed_state
    original_fk_values = {}
    
    for key in foreign_keys_set_to_none:
        if key in committed_state and committed_state[key] is not None:
            original_fk_values[key] = committed_state[key]
    
    if not original_fk_values:
        return
    
    # 恢复原外键值并设置软删除时间
    for key, value in original_fk_values.items():
        setattr(target, key, value)
    setattr(target, 'deleted_at', datetime.now().isoformat())


@event.listens_for(Session, 'before_flush')
def event_before_flush(session, flush_context, instances):
    """在flush之前检查dirty对象，跳过没有实际数据变更的对象

    功能：
    - 检测只有 updated_at 变更的对象
    - 将这些对象从 session 中移除，避免执行无意义的 UPDATE
    - 防止乐观锁版本号（ver）无意义递增

    注意：
    - 当 attrs_changed 为空集时，对象可能因 ManyToMany 的 back_populates
      被标记为 dirty，此时不能 expunge，否则会破坏关联表的 INSERT 操作。
    - 只有明确检测到"仅 updated_at 变更"时才跳过。
    """
    objects_to_skip = []

    for obj in list(session.dirty):
        if obj is None or not isinstance(obj, CoreModel):
            continue

        insp = inspect(obj, raiseerr=False)
        if insp is None or insp.session is not session:
            continue

        # 获取所有发生变更的属性
        attrs_changed = {
            attr.key for attr in insp.attrs
            if attr.history.has_changes()
        }

        # 仅当唯一的变更是 updated_at 时才跳过
        # 注意：attrs_changed 为空集时不能跳过，因为对象可能因
        # ManyToMany back_populates 被标记为 dirty，expunge 会导致
        # 关联表 INSERT 失败（SAWarning: Object not in session）
        if attrs_changed == {'updated_at'}:
            objects_to_skip.append(obj)

    # 从session中移除不需要flush的对象
    for obj in objects_to_skip:
        session.expunge(obj)
