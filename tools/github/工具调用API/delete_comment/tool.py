from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='delete_comment', description='删除当前用户发表的普通讨论评论。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.delete_comment)
