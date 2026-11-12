from typing import Any
from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=False, openWorldHint=False))
    def export_query(db_id: str, sql: str, save_path: str, parameters: list[Any] | dict[str, Any] | None = None, format: str = "csv") -> dict:
        """将只读查询完整导出为运行files内新CSV或JSON，不覆盖。format为csv/json，最多10000行、25 MiB，超限报错而非截断。CSV使用UTF-8 BOM，NULL为空字段。"""
        return store.export_query(db_id, sql, save_path, parameters, format)
