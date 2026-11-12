from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='get_project_info', description='读取项目文件数量、语言分布和配置文件位置。', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))(store.get_project_info)
