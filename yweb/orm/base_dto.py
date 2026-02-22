from typing import Dict, Any, Type, TypeVar, Iterator, ClassVar, Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict

T = TypeVar('T', bound='DTO')


class DTO(BaseModel):
    """数据传输对象基类 - 整合 Pydantic 支持
    
    提供以下功能：
    1. 继承 Pydantic BaseModel，自动支持字段验证和序列化
    2. 支持从 ORM 实体创建 DTO (from_entity) - 单个实体
    3. 支持从列表批量转换 (from_list) - 简单列表
    4. 支持从分页结果批量转换 (from_page) - 分页列表
    5. 支持从层级数据转换 (from_tree) - 树形结构
    6. 支持字段名映射 (_field_mapping) - 输出时重命名字段
    7. 支持字段值处理器 (_value_processors) - 创建时转换值
    
    _value_processors 执行时机：
        在 from_entity() / from_dict() 创建 DTO 实例 **之前** 执行，
        因此字段类型声明应与处理器 **转换后** 的类型一致。
    
    使用示例::
    
        from yweb import DTO
        
        class UserResponse(DTO):
            id: int
            username: str
            name: Optional[str] = None
            is_active: str = "active"      # 处理后是字符串
            created_at: str = ""
            roles: List[dict] = []         # 处理后是字典列表
            
            # 字段名映射：输出时 is_active -> status
            _field_mapping = {'is_active': 'status'}
            
            # 值处理器：在 from_entity 创建时转换值
            # 字段类型应与转换后的类型一致
            _value_processors = {
                'is_active': lambda v: 'active' if v else 'inactive',
                'roles': lambda v: [
                    {'code': r.code, 'name': r.name}
                    for r in (v or [])
                ],
            }
        
        # 单个实体
        user = UserResponse.from_entity(entity)
        
        # 简单列表（不分页）
        users = UserResponse.from_list(entities)
        
        # 分页列表
        page_data = UserResponse.from_page(page_result)
        
        # 树形结构
        class MenuResponse(DTO):
            id: int
            name: str
            parent_id: Optional[int] = None
        
        tree = MenuResponse.from_tree(menus)
    """
    
    model_config = ConfigDict(
        from_attributes=True,       # 支持从 ORM 对象创建
        populate_by_name=True,      # 支持字段别名
        arbitrary_types_allowed=True,
        extra='ignore',             # 忽略额外字段，便于从字典创建
    )
    
    # 类变量：字段名映射（输出时重命名）
    _field_mapping: ClassVar[Dict[str, str]] = {}
    
    # 类变量：字段值处理器（from_entity/from_dict 创建时转换值）
    # 字段类型声明应与处理器转换后的类型一致
    _value_processors: ClassVar[Dict[str, Any]] = {}
    
    @staticmethod
    def _format_datetime(value) -> Optional[str]:
        """通用的 datetime 格式化函数
        
        Args:
            value: 可能是 datetime 对象、字符串或其他类型
            
        Returns:
            格式化的时间字符串，如果输入为 None 则返回 None
        """
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.strftime('%Y-%m-%d %H:%M:%S')
        return str(value)
    
    @staticmethod
    def _safe_value(value) -> Any:
        """处理空值，将 {} 或空对象转为 None
        
        Args:
            value: 任意值
            
        Returns:
            处理后的值
        """
        if value is None:
            return None
        if isinstance(value, dict) and not value:
            return None
        # 处理空字符串对象（某些 ORM 可能返回的特殊对象）
        if hasattr(value, '__dict__') and not value.__dict__:
            return None
        return value
    
    @classmethod
    def _process_value(cls, value) -> Any:
        """处理单个值：空值处理 + datetime 格式化
        
        Args:
            value: 任意值
            
        Returns:
            处理后的值
        """
        # 处理空值（{} -> None）
        value = cls._safe_value(value)
        
        # 自动处理 datetime 类型
        if isinstance(value, datetime):
            value = cls._format_datetime(value)
        
        return value
    
    @classmethod
    def from_entity(cls: Type[T], entity) -> T:
        """从实体对象创建 DTO 实例
        
        处理流程：
        1. 从实体提取字段值
        2. 自动处理空值和 datetime 格式化
        3. 应用 _value_processors 转换值
        4. 创建 DTO 实例（Pydantic 验证）
        
        因此 DTO 字段的类型声明应与 _value_processors **处理后**的类型一致。
        
        Args:
            entity: 实体对象，应包含与 DTO 属性对应的字段
            
        Returns:
            DTO 实例
        """
        kwargs = {}
        
        # 获取 Pydantic 模型的所有字段
        for field_name, field_info in cls.model_fields.items():
            # 尝试从实体获取对应属性值
            if hasattr(entity, field_name):
                value = getattr(entity, field_name)
                kwargs[field_name] = cls._process_value(value)
        
        # 在创建前应用值处理器，确保类型与字段声明一致
        for field_name, processor in cls._value_processors.items():
            if field_name in kwargs:
                kwargs[field_name] = processor(kwargs[field_name])
        
        return cls(**kwargs)
    
    @classmethod
    def from_list(cls: Type[T], items) -> List[T]:
        """从列表批量转换为 DTO 列表（不分页）
        
        适用场景：下拉选项、角色列表等不需要分页的数据
        
        Args:
            items: 实体对象列表
            
        Returns:
            DTO 实例列表
            
        使用示例:
            roles = RoleResponse.from_list(role_entities)
            return Resp.OK(roles)
        """
        if items is None:
            return []
        return [cls.from_entity(item) for item in items]
    
    @classmethod
    def from_page(cls: Type[T], page_result):
        """从分页结果批量转换，返回兼容 PageResponse 的结构
        
        适用场景：分页列表查询
        
        Args:
            page_result: 分页结果对象，需包含 rows/items、total_records、page 等属性
            
        Returns:
            字典，包含 rows（DTO 列表）和分页信息
            
        使用示例:
            page_result = User.query.paginate(page=1, page_size=10)
            return Resp.OK(UserResponse.from_page(page_result))
        """
        # 获取数据列表（优先使用 yweb 的 rows，兼容其他库的 items）
        items = getattr(page_result, 'rows', None) or getattr(page_result, 'items', [])
        
        # 批量转换为 DTO
        rows = [cls.from_entity(item) for item in items]
        
        # 返回兼容 PageResponse 的结构（优先使用 yweb 属性名）
        return {
            "rows": rows,
            "total_records": getattr(page_result, 'total_records', getattr(page_result, 'total', 0)),
            "page": getattr(page_result, 'page', 1),
            "page_size": getattr(page_result, 'page_size', getattr(page_result, 'per_page', 10)),
            "total_pages": getattr(page_result, 'total_pages', getattr(page_result, 'pages', 1)),
            "has_prev": getattr(page_result, 'has_prev', False),
            "has_next": getattr(page_result, 'has_next', False),
        }
    
    # 保留别名以兼容旧代码
    from_page_result = from_page
    
    @classmethod
    def from_dict(cls: Type[T], data: Dict[str, Any]) -> T:
        """从字典创建 DTO 实例
        
        与 from_entity 行为一致，会自动：
        1. 处理空值（{} -> None）
        2. 格式化 datetime 类型为字符串
        
        会自动忽略字典中 DTO 未定义的字段（得益于 extra='ignore' 配置）。
        
        Args:
            data: 字典数据
            
        Returns:
            DTO 实例
            
        使用示例:
            job_dict = scheduler.get_job(code)
            response = JobResponse.from_dict(job_dict)
        """
        if data is None:
            data = {}
        
        # 处理字典中的值（与 from_entity 保持一致）
        processed_data = {key: cls._process_value(value) for key, value in data.items()}
        
        # 在创建前应用值处理器，确保类型与字段声明一致
        for field_name, processor in cls._value_processors.items():
            if field_name in processed_data:
                processed_data[field_name] = processor(processed_data[field_name])
        
        return cls.model_validate(processed_data)
    
    @classmethod
    def from_tree(
        cls: Type[T], 
        items, 
        parent_id=None, 
        id_key: str = 'id', 
        parent_key: str = 'parent_id',
        children_key: str = 'children'
    ) -> List[Dict[str, Any]]:
        """从扁平列表转换为树形结构
        
        适用场景：菜单、组织架构、分类目录等层级数据
        
        Args:
            items: 实体对象列表（扁平结构）
            parent_id: 父节点 ID，None 表示根节点
            id_key: ID 字段名，默认 'id'
            parent_key: 父 ID 字段名，默认 'parent_id'
            children_key: 子节点字段名，默认 'children'
            
        Returns:
            树形结构的字典列表
            
        使用示例:
            class MenuResponse(DTO):
                id: int
                name: str
                parent_id: Optional[int] = None
            
            menus = Menu.query.all()
            tree = MenuResponse.from_tree(menus)
            return Resp.OK(tree)
        """
        if items is None:
            return []
        
        # 先将所有实体转换为 DTO 字典
        all_nodes = []
        for item in items:
            dto = cls.from_entity(item)
            node = dto.model_dump()
            node[children_key] = []
            all_nodes.append(node)
        
        # 建立 ID -> 节点的映射
        node_map = {node[id_key]: node for node in all_nodes}
        
        # 构建树形结构
        tree = []
        for node in all_nodes:
            node_parent_id = node.get(parent_key)
            if node_parent_id == parent_id or node_parent_id is None:
                # 根节点
                tree.append(node)
            elif node_parent_id in node_map:
                # 添加到父节点的 children
                parent_node = node_map[node_parent_id]
                parent_node[children_key].append(node)
        
        return tree
    
    def model_dump(self, **kwargs) -> Dict[str, Any]:
        """重写序列化方法，支持字段名映射
        
        _value_processors 已在 from_entity/from_dict 创建时应用，
        此处只负责 _field_mapping 字段名重映射。
        
        Returns:
            序列化后的字典
        """
        # 先调用父类方法获取基础数据
        data = super().model_dump(**kwargs)
        
        # 应用字段名映射
        for old_key, new_key in self._field_mapping.items():
            if old_key in data:
                data[new_key] = data.pop(old_key)
        
        return data
    
    def __iter__(self) -> Iterator[tuple]:
        """使对象可迭代，支持 dict(dto) 转换
        
        自动应用字段名映射和值处理器
        """
        for key, value in self.model_dump().items():
            yield (key, value)
    
    def __getitem__(self, key):
        """支持通过索引访问字段，使 dict(dto) 正常工作"""
        return self.model_dump()[key]
    
    def keys(self):
        """返回字段名列表（兼容旧 API）"""
        return list(self.model_dump().keys())
    
    def values(self):
        """返回值列表（兼容旧 API）"""
        return list(self.model_dump().values())
    
    def items(self):
        """返回字段和值的元组列表（兼容旧 API）"""
        return list(self.model_dump().items())
    
    def to_dict(self) -> Dict[str, Any]:
        """将对象转换为字典格式（兼容旧 API）
        
        等同于 model_dump()
        """
        return self.model_dump()
