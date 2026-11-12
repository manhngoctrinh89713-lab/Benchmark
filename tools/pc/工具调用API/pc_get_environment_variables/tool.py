from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='pc_get_environment_variables', description='读取目标机器的用户或系统环境变量。', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))(store.pc_get_environment_variables)
