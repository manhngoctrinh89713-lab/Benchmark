from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='pc_delete_startup_item', description='删除一个非系统保护的开机启动项。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.pc_delete_startup_item)
