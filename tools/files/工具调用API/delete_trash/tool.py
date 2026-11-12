from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='delete_trash', description='永久删除一个回收站项目。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.delete_trash)
