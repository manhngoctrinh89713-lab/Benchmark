from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='list_archive', description='列出 ZIP 归档中的文件、目录和解压大小。', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))(store.list_archive)
