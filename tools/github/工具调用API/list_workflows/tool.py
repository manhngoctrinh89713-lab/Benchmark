from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def list_workflows(repo_id: str, offset: int = 0, limit: int = 20) -> dict:
        """列出场景预置的GitHub Actions工作流，不执行任何CI。"""
        return store.list_workflows(repo_id, offset, limit)
