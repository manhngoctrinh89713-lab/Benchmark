from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='list_comments', description='分页读取 Issue 或 PR 的普通讨论评论。', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))(store.list_comments)
