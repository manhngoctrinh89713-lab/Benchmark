from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='pc_update_application_settings', description='修改应用声明支持的设置，按类型、选项和数值范围校验。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.pc_update_application_settings)
