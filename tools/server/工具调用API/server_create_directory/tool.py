from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='server_create_directory', description='登记空目录，后续文件可写入该目录。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.server_create_directory)
