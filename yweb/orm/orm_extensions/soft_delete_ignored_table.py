"""软删除忽略表配置"""

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import Table


@dataclass
class IgnoredTable:
    """定义需要忽略软删除的表
    
    使用示例:
        from yweb.orm.orm_extensions import IgnoredTable
        
        # 忽略特定表的软删除
        ignored_tables = [
            IgnoredTable(name='audit_log'),  # 审计日志表
            IgnoredTable(name='system_config'),  # 系统配置表
        ]
    """
    name: str
    table_schema: Optional[str] = None

    def match_name(self, table: Table) -> bool:
        """检查表是否匹配
        
        表匹配条件：表名和schema都匹配
        """
        return self.name == table.name and self.table_schema == table.schema

