"""排序管理 Mixin

提供通用的排序操作方法，支持简单列表排序和分组排序。

使用示例:
    from yweb.orm import BaseModel
    from yweb.orm.sortable import SortFieldMixin, SortableMixin
    
    # 简单列表排序（无分组）
    class Banner(BaseModel, SortFieldMixin, SortableMixin):
        __tablename__ = "banner"
        title = mapped_column(String(100))
    
    banner = Banner.get(1)
    banner.move_up()          # 上移一位
    banner.move_down()        # 下移一位
    banner.move_to_top()      # 置顶
    banner.move_to_bottom()   # 置底
    
    # 分组排序（同一分类内排序）
    class Product(BaseModel, SortFieldMixin, SortableMixin):
        __tablename__ = "product"
        __sort_group_by__ = "category_id"  # 按分类分组
        
        category_id = mapped_column(Integer)
        name = mapped_column(String(100))
    
    product = Product.get(1)
    product.move_up()  # 在同一分类内上移
"""

from typing import List, Optional, Union, TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


class SortableMixin:
    """排序管理 Mixin
    
    为模型提供排序操作能力。
    
    字段要求（使用者需定义或使用 SortFieldMixin）:
        - sort_order: int  排序序号
    
    可配置属性（子类可覆盖）:
        - __sort_field__: 排序字段名，默认 "sort_order"
        - __sort_group_by__: 分组字段，默认 None（不分组）
            - 字符串: 单字段分组，如 "category_id"
            - 列表: 多字段分组，如 ["category_id", "status"]
    
    使用示例:
        # 简单排序
        class Banner(BaseModel, SortFieldMixin, SortableMixin):
            title: Mapped[str]
        
        banner = Banner.get(1)
        banner.move_up()
        banner.move_to_top()
        
        # 分组排序
        class Product(BaseModel, SortFieldMixin, SortableMixin):
            __sort_group_by__ = "category_id"
            category_id: Mapped[int]
            name: Mapped[str]
        
        # 批量重排序（前端拖拽后）
        Banner.reorder([3, 1, 2])  # 按此顺序重新编号
    """
    
    # ==================== 配置 ====================
    
    # 排序字段名（子类可覆盖）
    __sort_field__: str = "sort_order"
    
    # 分组字段（子类可覆盖）
    # - None: 不分组，全局排序
    # - str: 单字段分组
    # - list: 多字段分组
    __sort_group_by__: Union[str, List[str], None] = None
    
    # ==================== 内部方法 ====================
    
    def _get_sort_field_column(self):
        """获取排序字段的 Column 对象"""
        field_name = getattr(self.__class__, '__sort_field__', 'sort_order')
        return getattr(self.__class__, field_name)
    
    def _get_sort_value(self) -> int:
        """获取当前排序值"""
        field_name = getattr(self.__class__, '__sort_field__', 'sort_order')
        return getattr(self, field_name, 0) or 0
    
    def _set_sort_value(self, value: int) -> None:
        """设置排序值"""
        field_name = getattr(self.__class__, '__sort_field__', 'sort_order')
        setattr(self, field_name, value)
    
    def _get_group_fields(self) -> List[str]:
        """获取分组字段列表"""
        group_by = getattr(self.__class__, '__sort_group_by__', None)
        if not group_by:
            return []
        if isinstance(group_by, str):
            return [group_by]
        return list(group_by)
    
    def _get_group_filters(self) -> dict:
        """获取分组过滤条件（基于当前实例的值）"""
        return {field: getattr(self, field) for field in self._get_group_fields()}
    
    def _build_group_query(self, query, group_filters: dict = None):
        """为查询添加分组过滤条件
        
        Args:
            query: SQLAlchemy 查询对象
            group_filters: 分组过滤条件，None 时使用当前实例的值
            
        Returns:
            添加过滤条件后的查询对象
        """
        if group_filters is None:
            group_filters = self._get_group_filters()
        
        for field, value in group_filters.items():
            column = getattr(self.__class__, field)
            if value is None:
                query = query.filter(column.is_(None))
            else:
                query = query.filter(column == value)
        
        return query
    
    def _get_siblings_query(self, include_self: bool = False):
        """获取同组记录的查询
        
        Args:
            include_self: 是否包含自己
            
        Returns:
            SQLAlchemy 查询对象
        """
        query = self.__class__.query
        query = self._build_group_query(query)
        
        if not include_self and self.id is not None:
            query = query.filter(self.__class__.id != self.id)
        
        return query
    
    # ==================== 实例方法 ====================
    
    def move_up(self) -> bool:
        """上移一位
        
        与前一个记录交换位置。
        
        Returns:
            是否成功移动（如果已在最顶部则返回 False）
            
        Example:
            banner = Banner.get(1)
            if banner.move_up():
                db.session.commit()
                print("上移成功")
            else:
                print("已在最顶部")
        """
        previous = self.get_previous()
        if previous is None:
            return False
        
        self.swap_with(previous)
        return True
    
    def move_down(self) -> bool:
        """下移一位
        
        与后一个记录交换位置。
        
        Returns:
            是否成功移动（如果已在最底部则返回 False）
            
        Example:
            banner = Banner.get(1)
            if banner.move_down():
                db.session.commit()
                print("下移成功")
            else:
                print("已在最底部")
        """
        next_item = self.get_next()
        if next_item is None:
            return False
        
        self.swap_with(next_item)
        return True
    
    def move_to_top(self) -> bool:
        """置顶（移动到第一位）
        
        Returns:
            是否成功移动（如果已在最顶部则返回 False）
            
        Example:
            banner = Banner.get(1)
            banner.move_to_top()
            db.session.commit()
        """
        from sqlalchemy import func
        
        # 获取当前组内最小排序值
        min_order = self._get_siblings_query(include_self=True).with_entities(
            func.min(self._get_sort_field_column())
        ).scalar() or 0
        
        current_order = self._get_sort_value()
        
        if current_order <= min_order:
            return False  # 已经在最顶部
        
        # 将所有排序值比当前小的记录下移
        siblings = self._get_siblings_query().filter(
            self._get_sort_field_column() < current_order
        ).all()
        
        for item in siblings:
            item._set_sort_value(item._get_sort_value() + 1)
        
        self._set_sort_value(min_order)
        return True
    
    def move_to_bottom(self) -> bool:
        """置底（移动到最后一位）
        
        Returns:
            是否成功移动（如果已在最底部则返回 False）
            
        Example:
            banner = Banner.get(1)
            banner.move_to_bottom()
            db.session.commit()
        """
        max_order = self.__class__.get_max_sort_order(self._get_group_filters())
        current_order = self._get_sort_value()
        
        if current_order >= max_order:
            return False  # 已经在最底部
        
        # 将所有排序值比当前大的记录上移
        siblings = self._get_siblings_query().filter(
            self._get_sort_field_column() > current_order
        ).all()
        
        for item in siblings:
            item._set_sort_value(item._get_sort_value() - 1)
        
        self._set_sort_value(max_order)
        return True
    
    def move_to(self, position: int) -> bool:
        """移动到指定位置
        
        Args:
            position: 目标位置（1-based），1表示第一位
            
        Returns:
            是否成功移动（如果已在目标位置则返回 False）
            
        Example:
            banner = Banner.get(1)
            banner.move_to(3)  # 移动到第3位
            db.session.commit()
        """
        if position < 1:
            position = 1
        
        current_position = self.get_sort_position()
        if current_position == position:
            return False
        
        # 获取同组所有记录（按排序值排序，包含自己）
        all_items = self._get_siblings_query(include_self=True).order_by(
            self._get_sort_field_column()
        ).all()
        
        if not all_items:
            return False
        
        # 从列表中移除自己
        all_items = [item for item in all_items if item.id != self.id]
        
        # 计算目标索引
        target_index = min(position - 1, len(all_items))
        target_index = max(0, target_index)
        
        # 插入到目标位置
        all_items.insert(target_index, self)
        
        # 重新分配排序号
        for i, item in enumerate(all_items, 1):
            item._set_sort_value(i)
        
        return True
    
    def swap_with(self, other: "SortableMixin") -> None:
        """与另一个对象交换位置
        
        Args:
            other: 要交换的对象（应为同组记录）
            
        Example:
            banner1 = Banner.get(1)
            banner2 = Banner.get(2)
            banner1.swap_with(banner2)
            db.session.commit()
        """
        if other is None:
            return
        
        my_order = self._get_sort_value()
        other_order = other._get_sort_value()
        
        self._set_sort_value(other_order)
        other._set_sort_value(my_order)
    
    def get_sort_position(self) -> int:
        """获取当前排序位置（1-based）
        
        Returns:
            当前位置，从1开始
            
        Example:
            banner = Banner.get(1)
            position = banner.get_sort_position()
            print(f"当前在第 {position} 位")
        """
        count = self._get_siblings_query().filter(
            self._get_sort_field_column() < self._get_sort_value()
        ).count()
        return count + 1
    
    def get_previous(self) -> Optional["SortableMixin"]:
        """获取前一个对象（排序值更小的最近记录）
        
        Returns:
            前一个对象，如果没有返回 None
            
        Example:
            banner = Banner.get(1)
            prev = banner.get_previous()
            if prev:
                print(f"前一个是: {prev.title}")
        """
        return self._get_siblings_query().filter(
            self._get_sort_field_column() < self._get_sort_value()
        ).order_by(self._get_sort_field_column().desc()).first()
    
    def get_next(self) -> Optional["SortableMixin"]:
        """获取后一个对象（排序值更大的最近记录）
        
        Returns:
            后一个对象，如果没有返回 None
            
        Example:
            banner = Banner.get(1)
            next_banner = banner.get_next()
            if next_banner:
                print(f"下一个是: {next_banner.title}")
        """
        return self._get_siblings_query().filter(
            self._get_sort_field_column() > self._get_sort_value()
        ).order_by(self._get_sort_field_column()).first()
    
    def init_sort_order(self, position: str = "last") -> None:
        """初始化排序序号
        
        在创建新记录时调用，设置初始排序位置。
        
        Args:
            position: 初始位置
                - "last": 放到最后（默认）
                - "first": 放到最前
                
        Example:
            banner = Banner(title="新轮播图")
            banner.init_sort_order()  # 放到最后
            banner.save()
            
            # 或者放到最前
            banner.init_sort_order(position="first")
        """
        if position == "first":
            # 放到最前，需要将其他记录后移
            min_order = self.__class__.get_min_sort_order(self._get_group_filters())
            if min_order > 0:
                self._set_sort_value(min_order - 1)
            else:
                # 需要将所有记录后移
                siblings = self._get_siblings_query().all()
                for item in siblings:
                    item._set_sort_value(item._get_sort_value() + 1)
                self._set_sort_value(0)
        else:
            # 放到最后
            max_order = self.__class__.get_max_sort_order(self._get_group_filters())
            self._set_sort_value(max_order + 1)
    
    # ==================== 类方法 ====================
    
    @classmethod
    def get_max_sort_order(cls, group_filters: dict = None) -> int:
        """获取最大排序号
        
        Args:
            group_filters: 分组过滤条件，None 表示不过滤
            
        Returns:
            最大排序号，无记录返回 0
            
        Example:
            max_order = Banner.get_max_sort_order()
            print(f"最大排序号: {max_order}")
            
            # 分组查询
            max_order = Product.get_max_sort_order({"category_id": 1})
        """
        from sqlalchemy import func
        
        field_name = getattr(cls, '__sort_field__', 'sort_order')
        sort_field = getattr(cls, field_name)
        
        query = cls.query
        
        if group_filters:
            for field, value in group_filters.items():
                column = getattr(cls, field)
                if value is None:
                    query = query.filter(column.is_(None))
                else:
                    query = query.filter(column == value)
        
        result = query.with_entities(func.max(sort_field)).scalar()
        return result or 0
    
    @classmethod
    def get_min_sort_order(cls, group_filters: dict = None) -> int:
        """获取最小排序号
        
        Args:
            group_filters: 分组过滤条件，None 表示不过滤
            
        Returns:
            最小排序号，无记录返回 0
        """
        from sqlalchemy import func
        
        field_name = getattr(cls, '__sort_field__', 'sort_order')
        sort_field = getattr(cls, field_name)
        
        query = cls.query
        
        if group_filters:
            for field, value in group_filters.items():
                column = getattr(cls, field)
                if value is None:
                    query = query.filter(column.is_(None))
                else:
                    query = query.filter(column == value)
        
        result = query.with_entities(func.min(sort_field)).scalar()
        return result or 0
    
    @classmethod
    def reorder(cls, ids: List[Any], group_filters: dict = None) -> int:
        """批量重排序
        
        根据传入的 ID 顺序重新设置排序号。
        适用于前端拖拽排序后提交新顺序的场景。
        
        Args:
            ids: ID 列表，按期望的顺序排列
            group_filters: 分组过滤条件（可选，用于验证）
            
        Returns:
            更新的记录数
            
        Example:
            # 前端提交新顺序 [3, 1, 2]
            count = Banner.reorder([3, 1, 2])
            db.session.commit()
            print(f"更新了 {count} 条记录")
        """
        if not ids:
            return 0
        
        items = cls.query.filter(cls.id.in_(ids)).all()
        id_to_item = {item.id: item for item in items}
        
        field_name = getattr(cls, '__sort_field__', 'sort_order')
        
        count = 0
        for i, item_id in enumerate(ids, 1):
            if item_id in id_to_item:
                item = id_to_item[item_id]
                current_value = getattr(item, field_name)
                if current_value != i:
                    setattr(item, field_name, i)
                    count += 1
        
        return count
    
    @classmethod
    def normalize_sort_order(cls, group_filters: dict = None) -> int:
        """规范化排序号
        
        消除序号间隙，从1开始重新连续编号。
        适用于删除记录后清理间隙的场景。
        
        Args:
            group_filters: 分组过滤条件
            
        Returns:
            更新的记录数
            
        Example:
            # 删除一些记录后，排序号可能不连续: 1, 3, 7, 10
            count = Banner.normalize_sort_order()
            # 规范化后变成: 1, 2, 3, 4
            db.session.commit()
        """
        field_name = getattr(cls, '__sort_field__', 'sort_order')
        sort_field = getattr(cls, field_name)
        
        query = cls.query
        
        if group_filters:
            for field, value in group_filters.items():
                column = getattr(cls, field)
                if value is None:
                    query = query.filter(column.is_(None))
                else:
                    query = query.filter(column == value)
        
        items = query.order_by(sort_field).all()
        
        count = 0
        for i, item in enumerate(items, 1):
            current_value = getattr(item, field_name)
            if current_value != i:
                setattr(item, field_name, i)
                count += 1
        
        return count
    
    @classmethod
    def get_sorted(cls, group_filters: dict = None, desc: bool = False):
        """获取排序后的记录列表
        
        Args:
            group_filters: 分组过滤条件
            desc: 是否降序
            
        Returns:
            排序后的记录列表
            
        Example:
            banners = Banner.get_sorted()
            products = Product.get_sorted({"category_id": 1})
        """
        field_name = getattr(cls, '__sort_field__', 'sort_order')
        sort_field = getattr(cls, field_name)
        
        query = cls.query
        
        if group_filters:
            for field, value in group_filters.items():
                column = getattr(cls, field)
                if value is None:
                    query = query.filter(column.is_(None))
                else:
                    query = query.filter(column == value)
        
        if desc:
            query = query.order_by(sort_field.desc())
        else:
            query = query.order_by(sort_field)
        
        return query.all()


__all__ = [
    "SortableMixin",
]
