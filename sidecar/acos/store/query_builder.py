"""SQL 查询构建器，支持软删除过滤。"""

from __future__ import annotations


class QueryBuilder:
    """SQL 查询构建器，支持 include_deleted 参数。

    默认过滤已删除记录（deleted_at IS NULL），
    设置 include_deleted=True 后返回所有记录。
    """

    def __init__(self, table: str, include_deleted: bool = False) -> None:
        self._table = table
        self._include_deleted = include_deleted
        self._conditions: list[str] = []
        self._params: list[object] = []

    def where(self, condition: str, *params: object) -> QueryBuilder:
        self._conditions.append(condition)
        self._params.extend(params)
        return self

    def order_by(self, column: str, desc: bool = False) -> QueryBuilder:
        direction = "DESC" if desc else "ASC"
        self._conditions.append(f"ORDER BY {column} {direction}")
        return self

    def limit(self, n: int) -> QueryBuilder:
        self._conditions.append(f"LIMIT {n}")
        return self

    def build_select(self, columns: list[str] | None = None) -> str:
        """构建 SELECT 语句，自动过滤 deleted_at。"""
        cols = ", ".join(columns) if columns else "*"
        sql = f"SELECT {cols} FROM {self._table}"

        where_clauses: list[str] = []
        if not self._include_deleted:
            where_clauses.append("deleted_at IS NULL")

        for cond in self._conditions:
            if cond.startswith("ORDER BY") or cond.startswith("LIMIT"):
                continue
            where_clauses.append(cond)

        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)

        for cond in self._conditions:
            if cond.startswith("ORDER BY") or cond.startswith("LIMIT"):
                sql += " " + cond

        return sql

    def get_params(self) -> list[object]:
        return list(self._params)
