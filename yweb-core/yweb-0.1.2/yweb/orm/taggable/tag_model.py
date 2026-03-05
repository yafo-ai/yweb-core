"""标签模型定义

提供标签系统的抽象模型定义。

使用示例:
    from yweb.orm import BaseModel
    from yweb.orm.taggable import AbstractTag, AbstractTagRelation
    
    # 定义项目的标签模型
    class Tag(BaseModel, AbstractTag):
        __tablename__ = "tag"
    
    class TagRelation(BaseModel, AbstractTagRelation):
        __tablename__ = "tag_relation"
"""

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import Integer, String, Boolean, Text, Index, func
from sqlalchemy.orm import Mapped, mapped_column

if TYPE_CHECKING:
    pass


class AbstractTag:
    """标签抽象模型
    
    提供完整的标签字段定义，支持分组和层级。
    
    字段说明:
        - name: 标签名称（唯一）
        - slug: URL 友好标识（如 "machine-learning"）
        - group: 标签分组（如 "技术"、"颜色"）
        - parent_id: 父标签ID（支持层级）
        - color: 显示颜色（如 "#FF5733"）
        - description: 标签描述
        - use_count: 使用次数（冗余字段）
        - is_system: 是否系统标签（不可删除）
    
    使用示例:
        class Tag(BaseModel, AbstractTag):
            __tablename__ = "tag"
        
        # 创建标签
        tag = Tag(name="Python", slug="python", group="编程语言")
        tag.save()
        
        # 获取热门标签
        popular = Tag.get_popular(limit=10)
    """
    
    # 标签名称（唯一）
    # name 字段由 BaseModel 提供，这里只需要确保唯一性
    # 如果继承的 BaseModel 没有 name 字段，需要自行定义
    
    # URL 友好标识
    slug: Mapped[str] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="URL友好标识（如 machine-learning）"
    )
    
    # 标签分组
    group: Mapped[str] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="标签分组（如 技术、颜色）"
    )
    
    # 父标签ID（支持层级）
    parent_id: Mapped[int] = mapped_column(
        Integer,
        nullable=True,
        index=True,
        comment="父标签ID"
    )
    
    # 显示颜色
    color: Mapped[str] = mapped_column(
        String(20),
        nullable=True,
        default="#3498db",
        comment="显示颜色（如 #FF5733）"
    )
    
    # 标签描述
    description: Mapped[str] = mapped_column(
        Text,
        nullable=True,
        comment="标签描述"
    )
    
    # 使用次数（冗余字段，提升查询性能）
    use_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        index=True,
        comment="使用次数"
    )
    
    # 是否系统标签（不可删除）
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="是否系统标签"
    )
    
    # ==================== 类方法 ====================
    
    @classmethod
    def get_or_create(cls, name: str, **kwargs) -> "AbstractTag":
        """获取或创建标签
        
        Args:
            name: 标签名称
            **kwargs: 创建时的其他字段值
            
        Returns:
            标签对象
        """
        tag = cls.query.filter_by(name=name).first()
        if tag is None:
            # 自动生成 slug
            if 'slug' not in kwargs:
                kwargs['slug'] = cls._generate_slug(name)
            tag = cls(name=name, **kwargs)
            tag.save(commit=True)  # 必须提交以获取 ID
        return tag
    
    @classmethod
    def get_by_group(cls, group: str) -> List["AbstractTag"]:
        """获取指定分组的标签
        
        Args:
            group: 分组名称
            
        Returns:
            标签列表
        """
        return cls.query.filter_by(group=group).order_by(cls.use_count.desc()).all()
    
    @classmethod
    def get_popular(cls, limit: int = 10, group: str = None) -> List["AbstractTag"]:
        """获取热门标签
        
        Args:
            limit: 返回数量
            group: 可选的分组过滤
            
        Returns:
            按使用次数降序的标签列表
        """
        query = cls.query
        if group:
            query = query.filter_by(group=group)
        return query.order_by(cls.use_count.desc()).limit(limit).all()
    
    @classmethod
    def get_groups(cls) -> List[str]:
        """获取所有标签分组
        
        Returns:
            分组名称列表
        """
        result = cls.query.with_entities(cls.group).filter(
            cls.group.isnot(None)
        ).distinct().all()
        return [r[0] for r in result]
    
    @classmethod
    def search(cls, keyword: str, limit: int = 20) -> List["AbstractTag"]:
        """搜索标签
        
        Args:
            keyword: 搜索关键词
            limit: 返回数量
            
        Returns:
            匹配的标签列表
        """
        return cls.query.filter(
            cls.name.ilike(f"%{keyword}%")
        ).order_by(cls.use_count.desc()).limit(limit).all()
    
    @classmethod
    def _generate_slug(cls, name: str) -> str:
        """生成 URL 友好的 slug
        
        Args:
            name: 标签名称
            
        Returns:
            slug 字符串
        """
        import re
        # 转小写，替换空格为连字符，移除特殊字符
        slug = name.lower().strip()
        slug = re.sub(r'\s+', '-', slug)
        slug = re.sub(r'[^\w\-]', '', slug)
        return slug
    
    # ==================== 实例方法 ====================
    
    def increment_use_count(self, count: int = 1) -> None:
        """增加使用次数"""
        self.use_count = (self.use_count or 0) + count
    
    def decrement_use_count(self, count: int = 1) -> None:
        """减少使用次数"""
        self.use_count = max(0, (self.use_count or 0) - count)
    
    def get_children(self) -> List["AbstractTag"]:
        """获取子标签"""
        return self.__class__.query.filter_by(parent_id=self.id).all()
    
    def get_parent(self) -> Optional["AbstractTag"]:
        """获取父标签"""
        if self.parent_id:
            return self.__class__.query.get(self.parent_id)
        return None
    
    def get_ancestors(self) -> List["AbstractTag"]:
        """获取所有祖先标签"""
        ancestors = []
        parent = self.get_parent()
        while parent:
            ancestors.append(parent)
            parent = parent.get_parent()
        return ancestors
    
    def is_deletable(self) -> bool:
        """是否可删除"""
        return not self.is_system and self.use_count == 0


class AbstractTagRelation:
    """标签关联抽象模型（多态关联）
    
    通过 target_type + target_id 实现多态关联，
    任意模型都可以使用同一套标签系统。
    
    字段说明:
        - tag_id: 标签ID
        - target_type: 目标模型类型（如 "Article"）
        - target_id: 目标记录ID
    
    索引:
        - (target_type, target_id): 快速查询某记录的所有标签
        - (tag_id, target_type): 快速查询某标签关联的所有记录
    
    使用示例:
        class TagRelation(BaseModel, AbstractTagRelation):
            __tablename__ = "tag_relation"
    """
    
    # 标签ID
    tag_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
        comment="标签ID"
    )
    
    # 目标模型类型
    target_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="目标模型类型"
    )
    
    # 目标记录ID
    target_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
        comment="目标记录ID"
    )
    
    # 复合索引（在具体模型中定义）
    # __table_args__ = (
    #     Index('ix_tag_relation_target', 'target_type', 'target_id'),
    #     Index('ix_tag_relation_tag_type', 'tag_id', 'target_type'),
    # )
    
    @classmethod
    def create_relation(
        cls, 
        tag_id: int, 
        target_type: str, 
        target_id: int
    ) -> "AbstractTagRelation":
        """创建标签关联
        
        Args:
            tag_id: 标签ID
            target_type: 目标类型
            target_id: 目标ID
            
        Returns:
            关联对象
        """
        # 检查是否已存在
        existing = cls.query.filter_by(
            tag_id=tag_id,
            target_type=target_type,
            target_id=target_id
        ).first()
        
        if existing:
            return existing
        
        relation = cls(
            tag_id=tag_id,
            target_type=target_type,
            target_id=target_id
        )
        relation.save(commit=True)
        return relation
    
    @classmethod
    def delete_relation(
        cls, 
        tag_id: int, 
        target_type: str, 
        target_id: int
    ) -> bool:
        """删除标签关联
        
        Args:
            tag_id: 标签ID
            target_type: 目标类型
            target_id: 目标ID
            
        Returns:
            是否删除成功
        """
        relation = cls.query.filter_by(
            tag_id=tag_id,
            target_type=target_type,
            target_id=target_id
        ).first()
        
        if relation:
            relation.delete(commit=True)
            return True
        return False
    
    @classmethod
    def get_tag_ids_for_target(
        cls, 
        target_type: str, 
        target_id: int
    ) -> List[int]:
        """获取目标的所有标签ID
        
        Args:
            target_type: 目标类型
            target_id: 目标ID
            
        Returns:
            标签ID列表
        """
        result = cls.query.filter_by(
            target_type=target_type,
            target_id=target_id
        ).with_entities(cls.tag_id).all()
        return [r[0] for r in result]
    
    @classmethod
    def get_target_ids_for_tag(
        cls, 
        tag_id: int, 
        target_type: str
    ) -> List[int]:
        """获取标签关联的所有目标ID
        
        Args:
            tag_id: 标签ID
            target_type: 目标类型
            
        Returns:
            目标ID列表
        """
        result = cls.query.filter_by(
            tag_id=tag_id,
            target_type=target_type
        ).with_entities(cls.target_id).all()
        return [r[0] for r in result]


__all__ = [
    "AbstractTag",
    "AbstractTagRelation",
]
