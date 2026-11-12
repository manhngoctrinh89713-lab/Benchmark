from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def list_allowed_directories() -> dict:
        """返回本次运行唯一允许操作的files根目录及相对路径基准。"""
        return store.list_allowed_directories()
