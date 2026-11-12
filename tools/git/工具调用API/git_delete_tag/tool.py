from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='git_delete_tag', description='删除本地标签。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.git_delete_tag)
