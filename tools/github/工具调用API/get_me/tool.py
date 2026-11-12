from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def get_me() -> dict:
        """读取场景当前用户的本地GitHub资料。"""
        return store.get_me()
