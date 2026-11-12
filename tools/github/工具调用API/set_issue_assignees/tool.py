from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='set_issue_assignees', description='替换 Issue 的指派人，空列表清除指派。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.set_issue_assignees)
