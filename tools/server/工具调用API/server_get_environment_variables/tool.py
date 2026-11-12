from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='server_get_environment_variables', description='读取目标机器的用户或系统环境变量。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.server_get_environment_variables)
