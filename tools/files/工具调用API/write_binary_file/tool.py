from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='write_binary_file', description='将 Base64 内容写入文件，支持按已有文件校验值覆盖。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.write_binary_file)
