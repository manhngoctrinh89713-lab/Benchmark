from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='server_list_directory', description='列出挂载点下的直接文件和目录，包括已登记的空目录。', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))(store.server_list_directory)
