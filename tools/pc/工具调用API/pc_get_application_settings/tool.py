from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='pc_get_application_settings', description='读取应用设置及环境提供的可修改设置定义。', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))(store.pc_get_application_settings)
