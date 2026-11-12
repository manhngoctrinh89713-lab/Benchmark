from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='git_reflog', description='查询本地引用移动记录，供定位历史提交和恢复操作使用。', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))(store.git_reflog)
