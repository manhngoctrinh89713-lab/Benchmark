from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='rerun_workflow', description='重新运行已完成的工作流，保持原提交及输入，另建运行记录。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.rerun_workflow)
