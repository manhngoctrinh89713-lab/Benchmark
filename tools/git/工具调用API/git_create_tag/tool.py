from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='git_create_tag', description='在指定提交创建轻量标签，提供说明时创建附注标签。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.git_create_tag)
