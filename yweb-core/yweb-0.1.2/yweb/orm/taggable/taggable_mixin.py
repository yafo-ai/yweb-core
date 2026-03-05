"""标签管理 Mixin

提供通用的标签管理功能。

使用示例:
    from yweb.orm import BaseModel
    from yweb.orm.taggable import TaggableMixin, AbstractTag, AbstractTagRelation
    
    # 定义标签模型
    class Tag(BaseModel, AbstractTag):
        __tablename__ = "tag"
    
    class TagRelation(BaseModel, AbstractTagRelation):
        __tablename__ = "tag_relation"
    
    # 业务模型使用
    class Article(BaseModel, TaggableMixin):
        __tablename__ = "article"
        __tag_model__ = Tag
        __tag_relation_model__ = TagRelation
        
        title = mapped_column(String(200))
    
    # 使用
    article = Article(title="Python 教程")
    article.save(commit=True)
    
    article.add_tags(["Python", "Tutorial"])
    article.get_tags()  # ["Python", "Tutorial"]
    article.has_tag("Python")  # True
"""

from typing import List, Optional, Type, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .tag_model import AbstractTag, AbstractTagRelation


class TaggableMixin:
    """标签管理 Mixin
    
    为模型提供标签管理能力。
    
    配置属性（子类必须设置）:
        __tag_model__: 标签模型类
        __tag_relation_model__: 标签关联模型类
    
    使用示例:
        class Article(BaseModel, TaggableMixin):
            __tablename__ = "article"
            __tag_model__ = Tag
            __tag_relation_model__ = TagRelation
            
            title = mapped_column(String(200))
        
        article = Article.get(1)
        article.add_tag("Python")
        article.add_tags(["Web", "Tutorial"])
        article.remove_tag("Web")
        
        # 查询
        articles = Article.find_by_tag("Python")
        articles = Article.find_by_all_tags(["Python", "Web"])
    """
    
    # ==================== 配置 ====================
    
    # 标签模型类（子类必须设置）
    __tag_model__: Type["AbstractTag"] = None
    
    # 标签关联模型类（子类必须设置）
    __tag_relation_model__: Type["AbstractTagRelation"] = None
    
    # ==================== 内部方法 ====================
    
    def _get_tag_model(self) -> Type["AbstractTag"]:
        """获取标签模型类"""
        model = getattr(self.__class__, '__tag_model__', None)
        if model is None:
            raise ValueError(
                f"{self.__class__.__name__} 必须设置 __tag_model__ 属性"
            )
        return model
    
    def _get_relation_model(self) -> Type["AbstractTagRelation"]:
        """获取关联模型类"""
        model = getattr(self.__class__, '__tag_relation_model__', None)
        if model is None:
            raise ValueError(
                f"{self.__class__.__name__} 必须设置 __tag_relation_model__ 属性"
            )
        return model
    
    def _get_target_type(self) -> str:
        """获取目标类型名称"""
        return self.__class__.__name__
    
    # ==================== 实例方法：添加标签 ====================
    
    def add_tag(self, name: str, **tag_kwargs) -> "AbstractTag":
        """添加单个标签
        
        Args:
            name: 标签名称
            **tag_kwargs: 创建标签时的其他字段（如 group, color）
            
        Returns:
            标签对象
            
        Example:
            article.add_tag("Python")
            article.add_tag("Django", group="框架", color="#092E20")
        """
        if self.id is None:
            raise ValueError("必须先保存记录才能添加标签")
        
        Tag = self._get_tag_model()
        TagRelation = self._get_relation_model()
        
        # 获取或创建标签
        tag = Tag.get_or_create(name, **tag_kwargs)
        
        # 创建关联
        TagRelation.create_relation(
            tag_id=tag.id,
            target_type=self._get_target_type(),
            target_id=self.id
        )
        
        # 更新使用计数
        tag.increment_use_count()
        tag.save(commit=True)
        
        return tag
    
    def add_tags(self, names: List[str], **tag_kwargs) -> List["AbstractTag"]:
        """批量添加标签
        
        Args:
            names: 标签名称列表
            **tag_kwargs: 创建标签时的共同属性
            
        Returns:
            标签对象列表
            
        Example:
            article.add_tags(["Python", "Django", "Web"])
        """
        return [self.add_tag(name, **tag_kwargs) for name in names]
    
    # ==================== 实例方法：移除标签 ====================
    
    def remove_tag(self, name: str) -> bool:
        """移除单个标签
        
        Args:
            name: 标签名称
            
        Returns:
            是否移除成功
            
        Example:
            article.remove_tag("Python")
        """
        if self.id is None:
            return False
        
        Tag = self._get_tag_model()
        TagRelation = self._get_relation_model()
        
        # 查找标签
        tag = Tag.query.filter_by(name=name).first()
        if tag is None:
            return False
        
        # 删除关联
        success = TagRelation.delete_relation(
            tag_id=tag.id,
            target_type=self._get_target_type(),
            target_id=self.id
        )
        
        # 更新使用计数
        if success:
            tag.decrement_use_count()
            tag.save(commit=True)
        
        return success
    
    def remove_tags(self, names: List[str]) -> int:
        """批量移除标签
        
        Args:
            names: 标签名称列表
            
        Returns:
            成功移除的数量
        """
        count = 0
        for name in names:
            if self.remove_tag(name):
                count += 1
        return count
    
    def remove_all_tags(self) -> int:
        """移除所有标签
        
        Returns:
            移除的标签数量
        """
        tags = self.get_tags()
        return self.remove_tags(tags)
    
    # ==================== 实例方法：查询标签 ====================
    
    def get_tags(self) -> List[str]:
        """获取标签名称列表
        
        Returns:
            标签名称列表
            
        Example:
            tags = article.get_tags()
            print(tags)  # ["Python", "Django", "Web"]
        """
        return [tag.name for tag in self.get_tag_objects()]
    
    def get_tag_objects(self) -> List["AbstractTag"]:
        """获取标签对象列表
        
        Returns:
            标签对象列表
        """
        if self.id is None:
            return []
        
        Tag = self._get_tag_model()
        TagRelation = self._get_relation_model()
        
        # 获取关联的标签ID
        tag_ids = TagRelation.get_tag_ids_for_target(
            target_type=self._get_target_type(),
            target_id=self.id
        )
        
        if not tag_ids:
            return []
        
        return Tag.query.filter(Tag.id.in_(tag_ids)).all()
    
    def get_tags_by_group(self, group: str) -> List["AbstractTag"]:
        """获取指定分组的标签
        
        Args:
            group: 分组名称
            
        Returns:
            该分组的标签列表
        """
        all_tags = self.get_tag_objects()
        return [tag for tag in all_tags if tag.group == group]
    
    # ==================== 实例方法：检查标签 ====================
    
    def has_tag(self, name: str) -> bool:
        """是否有指定标签
        
        Args:
            name: 标签名称
            
        Returns:
            是否有该标签
        """
        return name in self.get_tags()
    
    def has_any_tags(self, names: List[str]) -> bool:
        """是否有任一指定标签
        
        Args:
            names: 标签名称列表
            
        Returns:
            是否有其中任一标签
        """
        current_tags = set(self.get_tags())
        return bool(current_tags & set(names))
    
    def has_all_tags(self, names: List[str]) -> bool:
        """是否有全部指定标签
        
        Args:
            names: 标签名称列表
            
        Returns:
            是否有全部标签
        """
        current_tags = set(self.get_tags())
        return set(names).issubset(current_tags)
    
    def get_tag_count(self) -> int:
        """获取标签数量
        
        Returns:
            标签数量
        """
        if self.id is None:
            return 0
        
        TagRelation = self._get_relation_model()
        return TagRelation.query.filter_by(
            target_type=self._get_target_type(),
            target_id=self.id
        ).count()
    
    # ==================== 实例方法：设置标签 ====================
    
    def set_tags(self, names: List[str], **tag_kwargs) -> None:
        """设置标签（覆盖现有标签）
        
        Args:
            names: 标签名称列表
            **tag_kwargs: 创建标签时的共同属性
            
        Example:
            article.set_tags(["Python", "Web"])  # 覆盖所有标签
        """
        current_tags = set(self.get_tags())
        new_tags = set(names)
        
        # 需要删除的标签
        to_remove = current_tags - new_tags
        # 需要添加的标签
        to_add = new_tags - current_tags
        
        # 执行删除和添加
        self.remove_tags(list(to_remove))
        self.add_tags(list(to_add), **tag_kwargs)
    
    # ==================== 类方法：按标签查询 ====================
    
    @classmethod
    def find_by_tag(cls, name: str, limit: int = None) -> List:
        """按单个标签查询
        
        Args:
            name: 标签名称
            limit: 返回数量限制
            
        Returns:
            记录列表
            
        Example:
            articles = Article.find_by_tag("Python")
        """
        Tag = getattr(cls, '__tag_model__', None)
        TagRelation = getattr(cls, '__tag_relation_model__', None)
        
        if Tag is None or TagRelation is None:
            return []
        
        # 查找标签
        tag = Tag.query.filter_by(name=name).first()
        if tag is None:
            return []
        
        # 获取目标ID列表
        target_ids = TagRelation.get_target_ids_for_tag(
            tag_id=tag.id,
            target_type=cls.__name__
        )
        
        if not target_ids:
            return []
        
        query = cls.query.filter(cls.id.in_(target_ids))
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    @classmethod
    def find_by_any_tags(cls, names: List[str], limit: int = None) -> List:
        """按任一标签查询（OR）
        
        Args:
            names: 标签名称列表
            limit: 返回数量限制
            
        Returns:
            有任一标签的记录列表
            
        Example:
            articles = Article.find_by_any_tags(["Python", "Java"])
        """
        Tag = getattr(cls, '__tag_model__', None)
        TagRelation = getattr(cls, '__tag_relation_model__', None)
        
        if Tag is None or TagRelation is None:
            return []
        
        # 查找标签ID
        tags = Tag.query.filter(Tag.name.in_(names)).all()
        if not tags:
            return []
        
        tag_ids = [tag.id for tag in tags]
        
        # 获取有这些标签的目标ID（去重）
        target_ids = set()
        for tag_id in tag_ids:
            ids = TagRelation.get_target_ids_for_tag(
                tag_id=tag_id,
                target_type=cls.__name__
            )
            target_ids.update(ids)
        
        if not target_ids:
            return []
        
        query = cls.query.filter(cls.id.in_(target_ids))
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    @classmethod
    def find_by_all_tags(cls, names: List[str], limit: int = None) -> List:
        """按全部标签查询（AND）
        
        Args:
            names: 标签名称列表
            limit: 返回数量限制
            
        Returns:
            有全部标签的记录列表
            
        Example:
            articles = Article.find_by_all_tags(["Python", "Web"])
        """
        Tag = getattr(cls, '__tag_model__', None)
        TagRelation = getattr(cls, '__tag_relation_model__', None)
        
        if Tag is None or TagRelation is None:
            return []
        
        # 查找标签ID
        tags = Tag.query.filter(Tag.name.in_(names)).all()
        if len(tags) != len(names):
            # 有些标签不存在
            return []
        
        tag_ids = [tag.id for tag in tags]
        
        # 获取每个标签关联的目标ID，取交集
        target_id_sets = []
        for tag_id in tag_ids:
            ids = TagRelation.get_target_ids_for_tag(
                tag_id=tag_id,
                target_type=cls.__name__
            )
            target_id_sets.append(set(ids))
        
        if not target_id_sets:
            return []
        
        # 取交集
        common_ids = target_id_sets[0]
        for id_set in target_id_sets[1:]:
            common_ids &= id_set
        
        if not common_ids:
            return []
        
        query = cls.query.filter(cls.id.in_(common_ids))
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    @classmethod
    def count_by_tag(cls, name: str) -> int:
        """按标签统计数量
        
        Args:
            name: 标签名称
            
        Returns:
            记录数量
        """
        Tag = getattr(cls, '__tag_model__', None)
        TagRelation = getattr(cls, '__tag_relation_model__', None)
        
        if Tag is None or TagRelation is None:
            return 0
        
        tag = Tag.query.filter_by(name=name).first()
        if tag is None:
            return 0
        
        return TagRelation.query.filter_by(
            tag_id=tag.id,
            target_type=cls.__name__
        ).count()
    
    @classmethod
    def get_all_used_tags(cls, limit: int = None) -> List["AbstractTag"]:
        """获取该模型使用的所有标签
        
        Args:
            limit: 返回数量限制
            
        Returns:
            标签列表（按使用次数降序）
        """
        Tag = getattr(cls, '__tag_model__', None)
        TagRelation = getattr(cls, '__tag_relation_model__', None)
        
        if Tag is None or TagRelation is None:
            return []
        
        # 获取该模型关联的所有标签ID
        from sqlalchemy import select
        
        subquery = select(TagRelation.tag_id).filter(
            TagRelation.target_type == cls.__name__
        ).distinct().scalar_subquery()
        
        query = Tag.query.filter(Tag.id.in_(subquery)).order_by(Tag.use_count.desc())
        
        if limit:
            query = query.limit(limit)
        
        return query.all()


__all__ = [
    "TaggableMixin",
]
