from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='create_archive', description='将选定文件或目录打包为 ZIP，归档内保留工作区相对路径。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.create_archive)
