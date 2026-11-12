from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='update_release', description='修改发布版本说明以及草稿、预发布状态。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.update_release)
