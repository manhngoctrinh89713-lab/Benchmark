from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='dispatch_workflow', description='向支持手动触发的工作流提交运行请求，固定当前引用对应的提交。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.dispatch_workflow)
