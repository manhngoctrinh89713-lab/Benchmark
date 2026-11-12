from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='list_trash', description='列出可恢复的回收站项目。', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))(store.list_trash)
