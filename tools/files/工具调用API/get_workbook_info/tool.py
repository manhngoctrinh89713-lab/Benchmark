from mcp.types import ToolAnnotations

def register(server, store):
    server.tool(name='get_workbook_info', description='查看XLSX工作表名称、可见性、行列范围和公式数量，不执行宏或外部链接。', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))(store.get_workbook_info)
