from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def list_repositories() -> dict:
        """查询可操作的模拟仓库和对应运行路径。"""
        return store.list_repositories()
