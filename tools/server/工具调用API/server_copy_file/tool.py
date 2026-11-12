from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='server_copy_file', description='复制常规文件到新路径，保留源文件且不覆盖目标。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.server_copy_file)
