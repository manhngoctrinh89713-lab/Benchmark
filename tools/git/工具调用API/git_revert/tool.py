from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='git_revert', description='以新提交撤销历史提交，支持 continue/skip/abort。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.git_revert)
