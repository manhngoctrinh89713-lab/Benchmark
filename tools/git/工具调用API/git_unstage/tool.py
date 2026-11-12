from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='git_unstage', description='撤销指定路径的暂存，保留工作区修改。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.git_unstage)
