from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='git_tags', description='列出轻量和附注标签及其提交标识。', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))(store.git_tags)
