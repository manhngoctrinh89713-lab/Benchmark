from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='pc_set_environment_variable', description='设置环境变量，null 删除变量；修改影响后续新建进程。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.pc_set_environment_variable)
