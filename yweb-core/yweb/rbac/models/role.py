"""
权限模块 - 角色抽象模型（完整 RBAC 版）

继承自 yweb.auth.AbstractSimpleRole，在轻量级角色基础上扩展：
- 树形继承（parent_id / path / level，来自 TreeMixin）
- 启用/禁用（is_active）
- 系统内置标记（is_system）
- 排序（sort_order）

层级关系:
    AbstractSimpleRole (yweb.auth)       ← id, name, code, description, 软删除
        └── AbstractRole (yweb.permission)  ← + 树形继承 + is_active + is_system

两者共享 RoleMixin API（User.has_role / User.role_codes），
从轻量版升级到完整版只需更换 Role 基类，无需改动用户侧代码。
"""

from typing import Optional, List, Set, TYPE_CHECKING
from sqlalchemy import String, Integer, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, declared_attr

from yweb.auth.models import AbstractSimpleRole
from yweb.organization import TreeMixin

if TYPE_CHECKING:
    pass


class AbstractRole(AbstractSimpleRole, TreeMixin):
    """角色抽象模型（支持树形继承）
    
    继承自 AbstractSimpleRole（轻量级角色），扩展树形结构和管理字段。
    子角色自动继承父角色的所有权限。
    
    继承自 AbstractSimpleRole 的字段:
        - id: 主键
        - name: 角色名称（如 "管理员"）
        - code: 角色编码（如 "admin"），唯一标识
        - description: 角色描述
        - note / caption: 备注
        - created_at / updated_at: 时间戳
        - 软删除支持
    
    本类新增字段:
        - parent_id: 父角色ID（用于继承）
        - is_active: 是否启用
        - is_system: 是否系统内置角色（不可删除）
        - path: 路径，用于快速查询子孙节点（来自 TreeMixin）
        - level: 层级（来自 TreeMixin）
        - sort_order: 排序
    
    继承的便捷方法（来自 AbstractSimpleRole）:
        - get_by_code(code): 根据编码获取角色
        - list_all(): 获取所有角色
        - create_role(name, code, description): 创建角色
    
    使用示例::
    
        from yweb.permission.models import AbstractRole
        
        class Role(AbstractRole):
            __tablename__ = "sys_role"
            __role_tablename__ = "sys_role"  # 用于外键引用
            enable_history = True
    
    角色继承示例::
    
        # 创建角色层级
        admin = Role(code="admin", name="管理员")
        admin.save()
        
        manager = Role(code="manager", name="经理", parent_id=admin.id)
        manager.save()
        manager.update_path_and_level()  # 更新路径
        
        # manager 自动继承 admin 的所有权限
    """
    __abstract__ = True
    
    # 子类可以设置此属性来指定角色表名（用于外键）
    # __role_tablename__: ClassVar[str] = "role"
    
    # ==================== 本类新增字段 ====================
    # （code / name / description 继承自 AbstractSimpleRole，无需重复定义）
    
    # 父角色ID（支持继承）
    @declared_attr
    def parent_id(cls) -> Mapped[Optional[int]]:
        """父角色ID
        
        子类可以通过设置 __role_tablename__ 来指定角色表名
        """
        role_tablename = getattr(cls, '__role_tablename__', 'role')
        return mapped_column(
            Integer,
            ForeignKey(f"{role_tablename}.id"),
            nullable=True,
            comment="父角色ID（支持继承）"
        )
    
    # 是否启用
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="是否启用"
    )
    
    # 是否系统内置角色（不可删除）
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="是否系统内置角色（不可删除）"
    )
    
    # TreeMixin 所需字段
    path: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        index=True,
        comment="路径，如 /1/2/3/"
    )
    
    level: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
        comment="层级，根节点为1"
    )
    
    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="排序"
    )
    
    def __repr__(self) -> str:
        return f"<Role(code='{self.code}', name='{self.name}')>"
    
    # ==================== 扩展查询方法 ====================
    # get_by_code / list_all / create_role 继承自 AbstractSimpleRole
    
    @classmethod
    def get_active_roles(cls) -> List["AbstractRole"]:
        """获取所有启用的角色
        
        Returns:
            角色列表
        """
        return cls.query.filter_by(is_active=True).order_by(cls.level, cls.sort_order).all()
    
    @classmethod
    def get_root_roles(cls) -> List["AbstractRole"]:
        """获取所有根角色（无父角色）
        
        Returns:
            根角色列表
        """
        return cls.query.filter(
            cls.parent_id.is_(None),
            cls.is_active == True
        ).order_by(cls.sort_order).all()
    
    def get_all_ancestor_codes(self) -> Set[str]:
        """获取所有祖先角色的编码
        
        Returns:
            祖先角色编码集合
        """
        ancestors = self.get_ancestors()
        return {r.code for r in ancestors}
    
    def get_all_descendant_codes(self) -> Set[str]:
        """获取所有子孙角色的编码
        
        Returns:
            子孙角色编码集合
        """
        descendants = self.get_descendants()
        return {r.code for r in descendants}


__all__ = ["AbstractRole"]
