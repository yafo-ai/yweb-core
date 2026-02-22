"""树形结构 Mixin

提供通用的树形操作方法，使用物化路径（Materialized Path）模式。

物化路径模式说明：
    - 每个节点存储从根到自身的完整路径，如 "/1/2/3/"
    - 优点：查询祖先/子孙非常高效（使用 LIKE 前缀匹配）
    - 缺点：移动节点时需要更新所有子孙的路径

使用示例:
    from yweb.orm import BaseModel
    from yweb.orm.tree import TreeMixin
    
    class Menu(BaseModel, TreeMixin):
        __tablename__ = "menu"
        
        parent_id = mapped_column(Integer, ForeignKey("menu.id"), nullable=True)
        path = mapped_column(String(500), nullable=True)
        level = mapped_column(Integer, default=1)
        sort_order = mapped_column(Integer, default=0)
        
        title = mapped_column(String(100))
    
    # 使用
    menu = Menu.get(1)
    children = menu.get_children()      # 直接子节点
    descendants = menu.get_descendants() # 所有子孙
    ancestors = menu.get_ancestors()     # 所有祖先
    menu.move_to(new_parent_id)          # 移动节点
"""

from typing import List, Optional, TYPE_CHECKING, Union

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class TreeMixin:
    """树形结构 Mixin
    
    为模型提供通用的树形操作方法。
    
    字段要求（使用者需定义）:
        - id: 主键（支持 int/str，自动适配）
        - parent_id: 父节点ID（与 id 类型一致）
        - path: 路径字符串，如 "/1/2/3/"
        - level: 层级，根节点为1
        - sort_order: 排序序号（可选，用于同级排序）
    
    可配置属性（子类可覆盖）:
        - PATH_SEPARATOR: 路径分隔符，默认 "/"
        - __tree_sort_field__: 排序字段名，默认 "sort_order"
    
    使用示例:
        class Department(BaseModel, TreeMixin):
            __tablename__ = "department"
            
            parent_id = mapped_column(Integer, ForeignKey("department.id"))
            path = mapped_column(String(500))
            level = mapped_column(Integer, default=1)
            sort_order = mapped_column(Integer, default=0)
        
        dept = Department.get(1)
        children = dept.get_children()
        ancestors = dept.get_ancestors()
    """
    
    # ==================== 可配置属性 ====================
    
    # 路径分隔符
    PATH_SEPARATOR: str = "/"
    
    # 排序字段名（子类可覆盖）
    __tree_sort_field__: str = "sort_order"
    
    # ==================== 路径与层级计算 ====================
    
    def _parse_path_id(self, id_str: str) -> Union[int, str, None]:
        """解析路径中的 ID，自动匹配主键类型
        
        根据当前实例的 id 类型决定如何解析路径中的 ID 字符串。
        
        Args:
            id_str: 路径中的 ID 字符串
            
        Returns:
            解析后的 ID（int 或 str），无效输入返回 None
        """
        if not id_str:
            return None
        
        # 根据当前实例的 id 类型决定如何解析
        if isinstance(self.id, int):
            try:
                return int(id_str)
            except (ValueError, TypeError):
                return None
        
        # 字符串类型直接返回
        return id_str
    
    def _get_sort_field(self):
        """获取排序字段
        
        Returns:
            排序字段的 Column 对象
        """
        sort_field_name = getattr(self.__class__, '__tree_sort_field__', 'sort_order')
        return getattr(self.__class__, sort_field_name, None)
    
    def build_path(self) -> str:
        """构建当前节点的路径
        
        Returns:
            路径字符串，如 "/1/2/3/"
        """
        if self.parent_id is None:
            return f"{self.PATH_SEPARATOR}{self.id}{self.PATH_SEPARATOR}"
        
        parent = self.__class__.get(self.parent_id)
        if parent is None:
            return f"{self.PATH_SEPARATOR}{self.id}{self.PATH_SEPARATOR}"
        
        return f"{parent.path}{self.id}{self.PATH_SEPARATOR}"
    
    def calculate_level(self) -> int:
        """计算当前节点的层级
        
        Returns:
            层级数，根节点为1
        """
        if self.parent_id is None:
            return 1
        
        parent = self.__class__.get(self.parent_id)
        if parent is None:
            return 1
        
        return parent.level + 1
    
    def update_path_and_level(self):
        """更新当前节点的 path 和 level
        
        在创建或移动节点时调用。
        """
        self.path = self.build_path()
        self.level = self.calculate_level()
    
    # ==================== 节点查询方法 ====================
    
    def get_children(self) -> List:
        """获取直接子节点
        
        Returns:
            子节点列表，按排序字段排序
        """
        query = self.__class__.query.filter(
            self.__class__.parent_id == self.id
        )
        
        # 添加排序
        sort_field = self._get_sort_field()
        if sort_field is not None:
            query = query.order_by(sort_field)
        
        return query.all()
    
    def get_descendants(self) -> List:
        """获取所有子孙节点
        
        使用 path 前缀匹配实现高效查询。
        
        Returns:
            所有子孙节点列表，按层级和排序字段排序
        """
        if not self.path:
            return []
        
        query = self.__class__.query.filter(
            self.__class__.path.like(f"{self.path}%"),
            self.__class__.id != self.id
        )
        
        # 添加排序：先按层级，再按排序字段
        sort_field = self._get_sort_field()
        if sort_field is not None:
            query = query.order_by(self.__class__.level, sort_field)
        else:
            query = query.order_by(self.__class__.level)
        
        return query.all()
    
    def get_ancestors(self) -> List:
        """获取所有祖先节点
        
        Returns:
            祖先节点列表，从根节点开始排序
        """
        if not self.path or self.parent_id is None:
            return []
        
        # 从 path 中解析祖先 ID
        # path 格式: "/1/2/3/" -> [1, 2] (不包含自己)
        parts = self.path.strip(self.PATH_SEPARATOR).split(self.PATH_SEPARATOR)
        ancestor_ids = [
            self._parse_path_id(p)
            for p in parts
            if p and self._parse_path_id(p) != self.id
        ]
        
        # 过滤掉 None 值
        ancestor_ids = [aid for aid in ancestor_ids if aid is not None]
        
        if not ancestor_ids:
            return []
        
        return self.__class__.query.filter(
            self.__class__.id.in_(ancestor_ids)
        ).order_by(self.__class__.level).all()
    
    def get_parent(self):
        """获取父节点
        
        Returns:
            父节点对象，如果是根节点则返回 None
        """
        if self.parent_id is None:
            return None
        return self.__class__.get(self.parent_id)
    
    def get_siblings(self) -> List:
        """获取兄弟节点（不包含自己）
        
        Returns:
            兄弟节点列表
        """
        query = self.__class__.query.filter(
            self.__class__.parent_id == self.parent_id,
            self.__class__.id != self.id
        )
        
        sort_field = self._get_sort_field()
        if sort_field is not None:
            query = query.order_by(sort_field)
        
        return query.all()
    
    def get_root(self):
        """获取根节点
        
        Returns:
            根节点对象
        """
        if self.parent_id is None:
            return self
        
        ancestors = self.get_ancestors()
        return ancestors[0] if ancestors else self
    
    # ==================== 节点状态判断 ====================
    
    def is_root(self) -> bool:
        """判断是否为根节点"""
        return self.parent_id is None
    
    def is_leaf(self) -> bool:
        """判断是否为叶子节点（无子节点）"""
        return self.__class__.query.filter(
            self.__class__.parent_id == self.id
        ).count() == 0
    
    def is_ancestor_of(self, node) -> bool:
        """判断当前节点是否为指定节点的祖先
        
        Args:
            node: 要判断的节点
            
        Returns:
            是否为祖先
        """
        if not node.path or not self.path:
            return False
        return node.path.startswith(self.path) and node.id != self.id
    
    def is_descendant_of(self, node) -> bool:
        """判断当前节点是否为指定节点的子孙
        
        Args:
            node: 要判断的节点
            
        Returns:
            是否为子孙
        """
        return node.is_ancestor_of(self)
    
    # ==================== 节点操作方法 ====================
    
    def move_to(self, new_parent_id: Optional[Union[int, str]]):
        """移动节点到新的父节点下
        
        会自动更新当前节点及所有子孙节点的 path 和 level。
        
        Args:
            new_parent_id: 新父节点ID，None 表示移动到根级别
            
        Raises:
            ValueError: 如果移动会导致循环引用或父节点不存在
        """
        # 检查循环引用
        if new_parent_id is not None:
            new_parent = self.__class__.get(new_parent_id)
            if new_parent is None:
                raise ValueError(f"父节点不存在: {new_parent_id}")
            if self.is_ancestor_of(new_parent):
                raise ValueError("不能将节点移动到其子孙节点下")
        
        old_path = self.path
        
        # 更新父节点
        self.parent_id = new_parent_id
        self.update_path_and_level()
        
        # 更新所有子孙节点的 path 和 level
        if old_path:
            descendants = self.__class__.query.filter(
                self.__class__.path.like(f"{old_path}%"),
                self.__class__.id != self.id
            ).all()
            
            for desc in descendants:
                # 替换路径前缀
                desc.path = desc.path.replace(old_path, self.path, 1)
                # 重新计算层级
                desc.level = len(desc.path.strip(self.PATH_SEPARATOR).split(self.PATH_SEPARATOR))
    
    # ==================== 统计方法 ====================
    
    def get_descendant_count(self) -> int:
        """获取子孙节点数量
        
        Returns:
            子孙节点总数
        """
        if not self.path:
            return 0
        
        return self.__class__.query.filter(
            self.__class__.path.like(f"{self.path}%"),
            self.__class__.id != self.id
        ).count()
    
    def get_children_count(self) -> int:
        """获取直接子节点数量
        
        Returns:
            直接子节点数量
        """
        return self.__class__.query.filter(
            self.__class__.parent_id == self.id
        ).count()
    
    def get_depth(self) -> int:
        """获取以当前节点为根的子树深度
        
        Returns:
            子树深度（当前节点深度为1，无子节点则返回1）
        """
        descendants = self.get_descendants()
        if not descendants:
            return 1
        
        max_level = max(d.level for d in descendants)
        return max_level - self.level + 1
    
    # ==================== 便捷方法 ====================
    
    def get_path_names(self, separator: str = " > ", name_field: str = "name") -> str:
        """获取完整路径名称
        
        Args:
            separator: 分隔符
            name_field: 名称字段名
            
        Returns:
            完整路径名称，如 "一级 > 二级 > 三级"
        """
        ancestors = self.get_ancestors()
        names = []
        
        for a in ancestors:
            name = getattr(a, name_field, None)
            if name:
                names.append(str(name))
        
        # 添加当前节点名称
        current_name = getattr(self, name_field, None)
        if current_name:
            names.append(str(current_name))
        
        return separator.join(names)
    
    def get_path_ids(self) -> List[Union[int, str]]:
        """获取从根到当前节点的 ID 列表
        
        Returns:
            ID 列表，如 [1, 2, 3]
        """
        if not self.path:
            return [self.id] if self.id else []
        
        parts = self.path.strip(self.PATH_SEPARATOR).split(self.PATH_SEPARATOR)
        return [self._parse_path_id(p) for p in parts if p]
    
    # ==================== 类方法 ====================
    
    @classmethod
    def get_roots(cls) -> List:
        """获取所有根节点
        
        Returns:
            根节点列表
        """
        query = cls.query.filter(cls.parent_id.is_(None))
        
        # 尝试获取排序字段
        sort_field_name = getattr(cls, '__tree_sort_field__', 'sort_order')
        sort_field = getattr(cls, sort_field_name, None)
        if sort_field is not None:
            query = query.order_by(sort_field)
        
        return query.all()
    
    @classmethod
    def get_tree_list(cls, root_id: Union[int, str] = None) -> List[dict]:
        """获取树形结构列表（嵌套格式）
        
        Args:
            root_id: 根节点ID，None 表示获取所有根节点的树
            
        Returns:
            嵌套的树形结构列表
        """
        from .tree_utils import build_tree_list
        
        # 获取排序字段
        sort_field_name = getattr(cls, '__tree_sort_field__', 'sort_order')
        sort_field = getattr(cls, sort_field_name, None)
        
        if root_id is not None:
            # 获取指定根节点及其所有子孙
            root = cls.get(root_id)
            if not root:
                return []
            
            query = cls.query.filter(
                cls.path.like(f"{root.path}%")
            )
        else:
            query = cls.query
        
        # 排序
        if sort_field is not None:
            query = query.order_by(cls.level, sort_field)
        else:
            query = query.order_by(cls.level)
        
        nodes = query.all()
        
        # 转换为字典列表
        node_dicts = []
        for node in nodes:
            if hasattr(node, 'to_dict'):
                node_dicts.append(node.to_dict())
            else:
                node_dicts.append({
                    'id': node.id,
                    'parent_id': node.parent_id,
                    'path': node.path,
                    'level': node.level,
                })
        
        return build_tree_list(node_dicts)
    
    @classmethod
    def rebuild_all_paths(cls) -> int:
        """重建所有节点的路径
        
        用于修复路径数据不一致的情况。
        
        Returns:
            更新的节点数量
        """
        # 获取所有节点，按层级排序
        sort_field_name = getattr(cls, '__tree_sort_field__', 'sort_order')
        sort_field = getattr(cls, sort_field_name, None)
        
        if sort_field is not None:
            nodes = cls.query.order_by(cls.level.asc(), sort_field).all()
        else:
            nodes = cls.query.order_by(cls.level.asc()).all()
        
        count = 0
        for node in nodes:
            old_path = node.path
            old_level = node.level
            node.update_path_and_level()
            if node.path != old_path or node.level != old_level:
                count += 1
        
        return count


__all__ = ["TreeMixin"]
