"""
组织管理模块 - 组织抽象模型

定义组织（Organization）的抽象基类
"""

from sqlalchemy import String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from yweb.orm import BaseModel
from ..enums import ExternalSource


class AbstractOrganization(BaseModel):
    """组织抽象模型
    
    组织是最顶层的实体，代表一个企业、公司或独立组织单元。
    一个组织下可以有多个部门和员工。
    
    字段说明:
        - name: 组织名称
        - code: 组织编码（建议唯一）
        - note: 备注
        - caption: 介绍
        - external_source: 外部系统来源（企微/飞书/钉钉等）
        - external_corp_id: 外部企业ID
        - external_config: 外部系统配置（JSON，用于存储各平台特有字段）
    
    使用示例:
        from yweb.organization import AbstractOrganization
        
        class Organization(AbstractOrganization):
            __tablename__ = "sys_organization"
            
            # 可添加自定义字段
            license_no = mapped_column(String(50), comment="营业执照号")
    """
    __abstract__ = True
    
    # ==================== 基础字段 ====================
    # name, code, note, caption 继承自 BaseModel
    
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        comment="是否启用"
    )
    
    # ==================== 外部系统字段 ====================
    
    external_source: Mapped[str] = mapped_column(
        String(50),
        nullable=True,
        default=ExternalSource.NONE.value,
        comment="外部系统来源（none/wechat_work/feishu/dingtalk/custom）"
    )
    
    external_corp_id: Mapped[str] = mapped_column(
        String(255),
        nullable=True,
        comment="外部企业ID（如企微的corpid、飞书的tenant_key、钉钉的corp_id）"
    )
    
    external_config: Mapped[str] = mapped_column(
        Text,
        nullable=True,
        comment="外部系统配置（JSON格式，存储各平台特有字段）"
    )
    
    # ==================== 验证方法 ====================
    
    @classmethod
    def validate_code_unique(cls, code: str, exclude_id: int = None) -> None:
        """验证组织编码唯一性
        
        Args:
            code: 要验证的编码
            exclude_id: 排除的ID（更新时使用，排除自身）
            
        Raises:
            ValueError: 如果编码已存在
        """
        if not code:
            return
            
        query = cls.query.filter_by(code=code)
        if exclude_id:
            query = query.filter(cls.id != exclude_id)
        
        if query.first() is not None:
            raise ValueError(f"组织编码已存在: {code}")
    
    # ==================== 便捷方法 ====================
    
    def is_external(self) -> bool:
        """判断是否为外部系统同步的组织"""
        return self.external_source and self.external_source != ExternalSource.NONE.value
    
    def get_external_config_dict(self) -> dict:
        """获取外部配置字典
        
        Returns:
            外部配置字典，如果为空或无效则返回空字典
        """
        if not self.external_config:
            return {}
        
        import json
        try:
            return json.loads(self.external_config)
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_external_config_dict(self, config: dict):
        """设置外部配置字典
        
        Args:
            config: 配置字典
        """
        import json
        self.external_config = json.dumps(config, ensure_ascii=False)


__all__ = ["AbstractOrganization"]
