from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='server_list_task_runs', description='查询计划任务的真实模型执行结果和失败信息。', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))(store.server_list_task_runs)
