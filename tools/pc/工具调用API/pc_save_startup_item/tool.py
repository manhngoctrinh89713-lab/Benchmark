from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='pc_save_startup_item', description='新增或修改应用开机启动项。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.pc_save_startup_item)
