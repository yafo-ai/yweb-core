"""SQL查询重写器 - 软删除过滤"""

from __future__ import annotations

from typing import TypeVar, Union, List

from sqlalchemy import Table
from sqlalchemy.orm import FromStatement
from sqlalchemy.orm.util import _ORMJoin
from sqlalchemy.sql import Alias, CompoundSelect, Executable, Join, Delete, Update, Select, Subquery, TableClause
from sqlalchemy.sql.elements import TextClause

from .soft_delete_ignored_table import IgnoredTable

Statement = TypeVar('Statement', bound=Union[Select, FromStatement, CompoundSelect, Executable])


class SoftDeleteRewriter:
    """SQL查询重写器
    
    自动为查询添加软删除过滤条件，实现：
    - SELECT查询自动过滤已删除记录
    - 支持子查询、JOIN等复杂查询
    - 可通过execution_options禁用软删除过滤
    
    使用示例:
        from yweb.orm.orm_extensions import SoftDeleteRewriter
        
        # 创建重写器
        rewriter = SoftDeleteRewriter(
            deleted_field_name="deleted_at",
            disable_soft_delete_option_name="include_deleted",
            ignored_tables=[]
        )
        
        # 禁用软删除过滤（查询包括已删除记录）
        User.query.execution_options(include_deleted=True).all()
    """

    def __init__(
            self,
            deleted_field_name: str = "deleted_at",
            disable_soft_delete_option_name: str = "include_deleted",
            ignored_tables: List[IgnoredTable] = None,
    ):
        """初始化查询重写器
        
        Args:
            deleted_field_name: 软删除字段名
            disable_soft_delete_option_name: 禁用软删除过滤的execution_option名称
            ignored_tables: 忽略软删除的表列表
        """
        self.ignored_tables = ignored_tables or []
        self.deleted_field_name = deleted_field_name
        self.disable_soft_delete_option_name = disable_soft_delete_option_name

    def rewrite_statement(self, stmt: Statement) -> Statement:
        """重写SQL语句
        
        支持的语句类型：
        - Select
        - Delete（转换为软删除）
        - Update
        - CompoundSelect（UNION等）
        - FromStatement
        """
        if isinstance(stmt, Select):
            return self.rewrite_select(stmt)

        if isinstance(stmt, Delete):
            return self.rewrite_delete(stmt)

        if isinstance(stmt, Update):
            return self.rewrite_update(stmt)

        if isinstance(stmt, CompoundSelect):
            return self.rewrite_compound_select(stmt)

        if isinstance(stmt, FromStatement):
            if not isinstance(stmt.element, Select):
                return stmt
            stmt.element = self.rewrite_select(stmt.element)
            return stmt

        raise NotImplementedError(f"不支持的语句类型: {type(stmt)}")

    def rewrite_select(self, stmt: Select) -> Select:
        """重写SELECT语句"""
        # 检查是否禁用软删除过滤
        if stmt.get_execution_options().get(self.disable_soft_delete_option_name):
            return stmt

        for from_obj in stmt.get_final_froms():
            stmt = self._analyze_from(stmt, from_obj)

        return stmt

    def rewrite_compound_select(self, stmt: CompoundSelect) -> CompoundSelect:
        """重写复合SELECT语句（UNION等）"""
        for i in range(len(stmt.selects)):
            stmt.selects[i] = self.rewrite_select(stmt.selects[i])
        return stmt

    def rewrite_delete(self, stmt: Delete) -> Delete:
        """重写DELETE语句"""
        if stmt.get_execution_options().get(self.disable_soft_delete_option_name):
            return stmt
        
        table = stmt.table
        column_obj = table.columns.get(self.deleted_field_name)
        
        if column_obj is None:
            return stmt
        
        # 添加软删除过滤条件
        stmt = stmt.filter(column_obj.is_(None))
        return stmt

    def rewrite_update(self, stmt: Update) -> Update:
        """重写UPDATE语句"""
        if stmt.get_execution_options().get(self.disable_soft_delete_option_name):
            return stmt
        
        table = stmt.table
        column_obj = table.columns.get(self.deleted_field_name)
        
        if column_obj is None:
            return stmt
        
        # 添加软删除过滤条件
        stmt = stmt.filter(column_obj.is_(None))
        return stmt

    def _rewrite_element(self, subquery: Subquery) -> Subquery:
        """重写子查询"""
        if isinstance(subquery.element, CompoundSelect):
            subquery.element = self.rewrite_compound_select(subquery.element)
            return subquery

        if isinstance(subquery.element, Select):
            subquery.element = self.rewrite_select(subquery.element)
            return subquery

        raise NotImplementedError(f"不支持的子查询类型: {type(subquery.element)}")

    def _rewrite_from_orm_join(self, stmt: Select, join_obj: Union[_ORMJoin, Join]) -> Select:
        """处理JOIN查询"""
        # 递归处理多重JOIN
        if isinstance(join_obj.left, (_ORMJoin, Join)):
            stmt = self._rewrite_from_orm_join(stmt, join_obj.left)

        if isinstance(join_obj.right, (_ORMJoin, Join)):
            stmt = self._rewrite_from_orm_join(stmt, join_obj.right)

        # 处理普通表
        if isinstance(join_obj.left, Table):
            stmt = self._rewrite_from_table(stmt, join_obj.left)

        if isinstance(join_obj.right, Table):
            stmt = self._rewrite_from_table(stmt, join_obj.right)

        return stmt

    def _analyze_from(self, stmt: Select, from_obj) -> Select:
        """分析FROM子句"""
        if isinstance(from_obj, Table):
            return self._rewrite_from_table(stmt, from_obj)

        if isinstance(from_obj, (_ORMJoin, Join)):
            return self._rewrite_from_orm_join(stmt, from_obj)

        if isinstance(from_obj, Subquery):
            self._rewrite_element(from_obj)
            return stmt

        if isinstance(from_obj, (TableClause, TextClause)):
            # 原始SQL文本，无法处理
            return stmt

        if isinstance(from_obj, Alias):
            if isinstance(from_obj.element, Subquery):
                self._rewrite_element(from_obj.element)
                return stmt

            raise NotImplementedError(f"不支持的Alias内部类型: {type(from_obj.element)}")

        raise NotImplementedError(f"不支持的FROM类型: {type(from_obj)}")

    def _rewrite_from_table(self, stmt: Select, table: Table) -> Select:
        """为表添加软删除过滤条件"""
        # 检查是否在忽略列表中
        if any(ignored.match_name(table) for ignored in self.ignored_tables):
            return stmt

        # 获取软删除字段
        column_obj = table.columns.get(self.deleted_field_name)

        if column_obj is None:
            return stmt

        # 添加过滤条件：deleted_at IS NULL
        return stmt.filter(column_obj.is_(None))

