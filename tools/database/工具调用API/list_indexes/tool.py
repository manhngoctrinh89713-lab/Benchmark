from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='list_indexes', description='查询数据库索引、列顺序和唯一性。', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))(store.list_indexes)
