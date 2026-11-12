from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='cancel_workflow_run', description='请求取消正在排队或运行的工作流；最终结果由执行器回报。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.cancel_workflow_run)
