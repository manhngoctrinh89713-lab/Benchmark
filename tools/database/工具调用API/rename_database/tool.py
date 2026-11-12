from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='rename_database', description='修改数据库显示名称，数据库 ID 和 SQL 内容保持稳定。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.rename_database)
