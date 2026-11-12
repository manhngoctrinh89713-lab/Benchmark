from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='server_save_scheduled_task', description='新增或修改计划任务。电脑支持 application.launch；服务器支持 service.start/stop/restart/reload。零间隔为一次性任务。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.server_save_scheduled_task)
