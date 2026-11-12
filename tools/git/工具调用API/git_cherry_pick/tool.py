from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='git_cherry_pick', description='挑选一个提交，支持冲突后的 continue/skip/abort。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.git_cherry_pick)
