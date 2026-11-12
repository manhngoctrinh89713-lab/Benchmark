from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='search_project_files', description='按相对路径通配符和扩展名查询项目文件。', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))(store.search_project_files)
