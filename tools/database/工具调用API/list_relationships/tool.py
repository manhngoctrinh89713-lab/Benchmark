from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='list_relationships', description='列出表之间的外键关系及更新、删除行为。', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))(store.list_relationships)
