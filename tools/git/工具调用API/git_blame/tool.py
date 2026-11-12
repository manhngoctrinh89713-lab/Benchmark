from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='git_blame', description='读取文件选定行在指定提交中的逐行归属。', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))(store.git_blame)
