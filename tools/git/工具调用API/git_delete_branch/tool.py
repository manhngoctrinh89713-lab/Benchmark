from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='git_delete_branch', description='删除本地分支；默认要求分支已合并。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.git_delete_branch)
