from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='server_move_file', description='移动常规文件，不覆盖目标；服务配置和日志通过各自入口管理。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.server_move_file)
