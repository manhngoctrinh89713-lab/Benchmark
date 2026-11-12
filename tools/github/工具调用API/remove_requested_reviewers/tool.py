from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='remove_requested_reviewers', description='移除 PR 的待评审人。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.remove_requested_reviewers)
