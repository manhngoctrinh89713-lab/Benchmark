from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='server_delete_scheduled_task', description='删除计划任务，保留既有执行记录。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.server_delete_scheduled_task)
