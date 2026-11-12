from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='server_remove_directory', description='删除已登记的空目录。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.server_remove_directory)
