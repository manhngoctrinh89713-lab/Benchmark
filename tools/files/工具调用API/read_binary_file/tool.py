from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='read_binary_file', description='分段读取文件二进制内容，以 Base64 返回，并提供完整文件校验值。', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))(store.read_binary_file)
