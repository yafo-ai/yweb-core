"""业务模型基类

包含常用业务字段的模型基类，继承自 CoreModel 和 SimpleSoftDeleteMixin。
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from .core_model import CoreModel
from .orm_extensions import SimpleSoftDeleteMixin


class BaseModel(CoreModel, SimpleSoftDeleteMixin):
    """业务模型基类，包含常用业务字段
    
    继承自:
        - CoreModel: 核心ORM功能（ID、时间戳、CRUD、分页等）
        - SimpleSoftDeleteMixin: 软删除功能
    
    包含字段（BaseModel 新增）:
        - name: 名称
        - code: 编码
        - note: 备注
        - caption: 介绍
    
    继承字段（来自 CoreModel）:
        - id: 主键
        - created_at: 创建时间
        - updated_at: 更新时间
        - deleted_at: 软删除时间
        - ver: 版本号（乐观锁）
    
    方法来源速查表:
    
        来自 CoreModel:
            - get(id)                    获取单个对象
            - get_all()                  获取所有对象
            - add(commit)                添加对象
            - update(commit, **kwargs)   更新对象
            - delete(commit)             删除对象（配合软删除钩子自动转为软删除）
            - delete_all(objects)        批量删除
            - bulk_update(filters, values)     批量更新
            - bulk_update_by_ids(ids, values)  按ID批量更新
            - bulk_delete(filters)             批量物理删除
            - bulk_delete_by_ids(ids)          按ID批量物理删除
            - bulk_soft_delete(filters)        批量软删除
            - bulk_soft_delete_by_ids(ids)     按ID批量软删除
            - cleanup_soft_deleted(days)       清理软删除数据
            - cleanup_all_soft_deleted(days)   清理所有表的软删除数据
            - get_soft_deleted_count(days)     获取软删除数据数量
            - paginate(page, per_page)         分页查询
        
        来自 SimpleSoftDeleteMixin（动态生成）:
            - soft_delete()              软删除（设置 deleted_at）
            - undelete()                 恢复软删除（不推荐使用）
            - is_deleted                 属性，检查是否已软删除
        
        BaseModel 新增:
            - get_by_name(name)          根据名称获取
            - get_by_code(code)          根据编码获取
    
    使用示例:
        class User(BaseModel):
            # __tablename__ 自动生成为 "user"
            
            username = mapped_column(String(50), nullable=False)
            email = mapped_column(String(100), nullable=True)
    """
    __abstract__ = True
    
    # 业务字段（default=None 使其在构造时可选）
    name: Mapped[str] = mapped_column(String(255), nullable=True, default=None, comment="名称")
    code: Mapped[str] = mapped_column(String(255), nullable=True, default=None, comment="编码")
    note: Mapped[str] = mapped_column(String(1000), nullable=True, default=None, comment="备注")
    caption: Mapped[str] = mapped_column(String(512), nullable=True, default=None, comment="介绍")
    
    @classmethod
    def get_by_name(cls, name: str):
        """根据名称获取对象
        
        Args:
            name: 名称
            
        Returns:
            匹配的对象，不存在返回 None
        """
        return cls.query.filter_by(name=name).first()
    
    @classmethod
    def get_by_code(cls, code: str):
        """根据编码获取对象
        
        Args:
            code: 编码
            
        Returns:
            匹配的对象，不存在返回 None
        """
        return cls.query.filter_by(code=code).first()
