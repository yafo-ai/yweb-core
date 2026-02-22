"""
组织管理模块 - 部门抽象模型

定义部门（Department）的抽象基类。

设计原则（DDD 分层）：
- 领域模型封装单聚合内的业务规则
- 验证方法抛出 ValueError，由上层捕获处理
- 不依赖框架异常，保持领域模型纯净
"""

from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Integer, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, declared_attr, relationship

from yweb.orm import BaseModel
from yweb.orm.tree import TreeMixin

if TYPE_CHECKING:
    from .employee import AbstractEmployee


class AbstractDepartment(BaseModel, TreeMixin):
    """部门抽象模型
    
    部门是组织下的二级结构，支持树形层级（父子部门）。
    
    字段说明:
        - org_id: 所属组织ID
        - parent_id: 父部门ID（自关联，为空表示根部门）
        - name: 部门名称
        - code: 部门编码
        - path: 部门路径（如 /1/2/3/），用于快速查询祖先/子孙
        - level: 部门层级（1=根部门）
        - sort_order: 排序序号
        - primary_leader_id: 主负责人ID
        - external_dept_id: 外部部门ID
        - external_parent_id: 外部父部门ID
    
    树形操作方法（继承自 TreeMixin）:
        - get_children(): 获取直接子部门
        - get_descendants(): 获取所有子孙部门
        - get_ancestors(): 获取所有祖先部门
        - get_parent(): 获取父部门
        - move_to(new_parent_id): 移动部门
    
    使用示例:
        from yweb.organization import AbstractDepartment
        
        class Department(AbstractDepartment):
            __tablename__ = "sys_department"
            
            # 可添加自定义字段
            budget = mapped_column(Numeric(12, 2), comment="部门预算")
    
    注意:
        应用层需要自行定义 org_id 和 primary_leader_id 的外键关系，
        因为具体的 Organization 和 Employee 模型类在应用层定义。
    """
    __abstract__ = True
    
    # ==================== 基础字段 ====================
    # name, code, note, caption 继承自 BaseModel
    
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        comment="是否启用"
    )
    
    # ==================== 组织关联 ====================
    # 注意：外键目标表名需要在子类中通过 __org_tablename__ 指定
    # 或者在子类中重新定义 org_id 字段
    
    @declared_attr
    def org_id(cls) -> Mapped[int]:
        """所属组织ID
        
        子类可以通过设置 __org_tablename__ 来指定组织表名，
        或者直接在子类中重新定义此字段。
        """
        org_tablename = getattr(cls, '__org_tablename__', 'organization')
        return mapped_column(
            Integer,
            ForeignKey(f"{org_tablename}.id"),
            nullable=False,
            comment="所属组织ID"
        )
    
    # ==================== 树形结构字段 ====================
    
    @declared_attr
    def parent_id(cls) -> Mapped[Optional[int]]:
        """父部门ID（自关联）"""
        # 获取子类的实际表名
        tablename = getattr(cls, '__tablename__', 'department')
        return mapped_column(
            Integer,
            ForeignKey(f"{tablename}.id"),
            nullable=True,
            comment="父部门ID"
        )
    
    path: Mapped[str] = mapped_column(
        String(500),
        nullable=True,
        comment="部门路径（如 /1/2/3/）"
    )
    
    level: Mapped[int] = mapped_column(
        Integer,
        default=1,
        comment="部门层级（1=根部门）"
    )
    
    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="排序序号"
    )
    
    # ==================== 主负责人 ====================
    # 注意：外键目标表名需要在子类中通过 __employee_tablename__ 指定
    
    @declared_attr
    def primary_leader_id(cls) -> Mapped[Optional[int]]:
        """主负责人ID
        
        子类可以通过设置 __employee_tablename__ 来指定员工表名，
        或者直接在子类中重新定义此字段。
        """
        employee_tablename = getattr(cls, '__employee_tablename__', 'employee')
        return mapped_column(
            Integer,
            ForeignKey(f"{employee_tablename}.id"),
            nullable=True,
            comment="主负责人ID"
        )
    
    # ==================== 外部系统字段 ====================
    
    external_dept_id: Mapped[str] = mapped_column(
        String(255),
        nullable=True,
        comment="外部部门ID"
    )
    
    external_parent_id: Mapped[str] = mapped_column(
        String(255),
        nullable=True,
        comment="外部父部门ID"
    )
    
    # ==================== 关系定义（子类需要实现） ====================
    # 以下关系需要在子类中定义，因为具体的模型类在应用层
    
    # organization = relationship("Organization", back_populates="departments")
    # parent = relationship("Department", remote_side=[id], back_populates="children")
    # children = relationship("Department", back_populates="parent")
    # primary_leader = relationship("Employee", foreign_keys=[primary_leader_id])
    # employees = relationship("Employee", secondary="emp_dept_rel", back_populates="departments")
    # leaders = relationship("Employee", secondary="dept_leader", back_populates="leading_departments")
    
    # ==================== 便捷方法 ====================
    
    def is_root_department(self) -> bool:
        """判断是否为根部门"""
        return self.parent_id is None
    
    def get_full_name(self, separator: str = " > ") -> str:
        """获取完整的部门名称（包含所有祖先）
        
        Args:
            separator: 分隔符
            
        Returns:
            完整名称，如 "总公司 > 技术部 > 研发组"
        """
        ancestors = self.get_ancestors()
        names = [a.name for a in ancestors] + [self.name]
        return separator.join(names)
    
    # ==================== 业务规则方法（DDD 核心） ====================
    
    @classmethod
    def validate_code_unique(
        cls, 
        org_id: int, 
        code: str, 
        exclude_id: Optional[int] = None
    ) -> None:
        """验证部门编码在组织内唯一
        
        Args:
            org_id: 组织ID
            code: 部门编码
            exclude_id: 排除的部门ID（用于更新时）
            
        Raises:
            ValueError: 如果编码已存在
        """
        if not code:
            return
        
        query = cls.query.filter_by(org_id=org_id, code=code)
        if exclude_id:
            query = query.filter(cls.id != exclude_id)
        
        if query.first():
            raise ValueError(f"部门编码已存在: {code}")
    
    @classmethod
    def validate_parent(
        cls, 
        parent_id: int, 
        org_id: int
    ) -> "AbstractDepartment":
        """验证父部门有效性
        
        Args:
            parent_id: 父部门ID
            org_id: 期望的组织ID
            
        Returns:
            父部门对象
            
        Raises:
            ValueError: 如果父部门不存在或不属于同一组织
        """
        parent = cls.get(parent_id)
        if not parent:
            raise ValueError(f"父部门不存在: {parent_id}")
        
        if parent.org_id != org_id:
            raise ValueError("父部门不属于同一组织")
        
        return parent
    
    def validate_can_move_to(self, new_parent_id: Optional[int]) -> Optional["AbstractDepartment"]:
        """验证是否可以移动到目标父部门
        
        Args:
            new_parent_id: 新父部门ID，None 表示移到根级
            
        Returns:
            新父部门对象（如果有）
            
        Raises:
            ValueError: 如果会导致循环引用、跨组织移动或新父部门不存在
        """
        if new_parent_id is None:
            return None
        
        # 不能移动到自己下面
        if new_parent_id == self.id:
            raise ValueError("不能将部门移动到自己下面")
        
        # 验证新父部门存在
        new_parent = self.__class__.get(new_parent_id)
        if not new_parent:
            raise ValueError(f"目标父部门不存在: {new_parent_id}")
        
        # 不能跨组织移动
        if new_parent.org_id != self.org_id:
            raise ValueError("不能移动到其他组织的部门下")
        
        # 不能移动到自己的子部门下
        if self.is_ancestor_of(new_parent):
            raise ValueError("不能将部门移动到其子部门下")
        
        return new_parent
    
    def validate_can_delete(self, force: bool = False) -> dict:
        """验证是否可以删除
        
        Args:
            force: 是否强制删除
            
        Returns:
            包含 children 和 employee_count 的字典
            
        Raises:
            ValueError: 如果有子部门或员工且非强制删除
        """
        result = {"children": [], "employee_count": 0}
        
        # 检查子部门
        if hasattr(self, 'get_children'):
            children = self.get_children()
            result["children"] = children
            if children and not force:
                raise ValueError(f"部门下还有 {len(children)} 个子部门，请先删除或移动")
        
        # 检查员工
        if hasattr(self, 'employee_dept_rels'):
            emp_count = len(self.employee_dept_rels)
            result["employee_count"] = emp_count
            if emp_count > 0 and not force:
                raise ValueError(f"部门下还有 {emp_count} 名员工，请先移除")
        
        return result
    
    def move_to_parent(self, new_parent_id: Optional[int]) -> None:
        """移动到新的父部门（包含级联更新）
        
        此方法会：
        1. 验证移动有效性
        2. 更新自身的 parent_id, path, level
        3. 更新所有子孙部门的 path, level
        
        Args:
            new_parent_id: 新父部门ID
            
        Raises:
            ValueError: 如果会导致循环引用或跨组织移动
        """
        # 验证移动有效性
        self.validate_can_move_to(new_parent_id)
        
        # 使用 TreeMixin 的 move_to 方法（已包含子孙更新）
        self.move_to(new_parent_id)
    
    def promote_children_to_parent(self) -> List["AbstractDepartment"]:
        """将子部门提升到当前部门的父级
        
        用于删除部门时，将子部门提升。
        
        Returns:
            被提升的子部门列表
        """
        children = self.get_children() if hasattr(self, 'get_children') else []
        
        for child in children:
            child.parent_id = self.parent_id
            if hasattr(child, 'update_path_and_level'):
                child.update_path_and_level()
        
        return children


__all__ = ["AbstractDepartment"]
