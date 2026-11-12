from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='server_list_scheduled_tasks', description='列出目标机器的计划任务和下次执行时间。', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))(store.server_list_scheduled_tasks)
