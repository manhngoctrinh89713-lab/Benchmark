from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='delete_release', description='删除发布记录，保留对应 Git 标签。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.delete_release)
