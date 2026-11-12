from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='pc_delete_scheduled_task', description='删除计划任务，保留既有执行记录。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.pc_delete_scheduled_task)
