from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='delete_label', description='删除仓库标签，同时移除 Issue 和 PR 上的该标签。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.delete_label)
