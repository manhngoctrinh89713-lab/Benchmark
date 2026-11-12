from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='git_stash', description='保存、列出、查看、应用、弹出或删除 stash。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.git_stash)
