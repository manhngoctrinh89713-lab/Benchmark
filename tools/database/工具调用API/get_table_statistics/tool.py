from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='get_table_statistics', description='读取表行数、每列空值数和不同值数量。', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))(store.get_table_statistics)
