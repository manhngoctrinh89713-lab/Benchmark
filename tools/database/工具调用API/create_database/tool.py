from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='create_database', description='创建空 SQLite 数据库并登记显示名称。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.create_database)
