from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
    def server_reboot(reason: str = ""):
        '模拟重启整机：停止本机服务并记录重启事件。'
        return store.server_reboot(reason=reason)
