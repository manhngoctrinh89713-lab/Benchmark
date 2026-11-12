from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='delete_milestone', description='删除里程碑并清除 Issue 和 PR 的关联。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.delete_milestone)
