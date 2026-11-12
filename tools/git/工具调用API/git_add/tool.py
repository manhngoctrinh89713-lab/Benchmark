from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=False, openWorldHint=False))
    def git_add(repo_id: str, paths: list[str]) -> dict:
        """暂存指定路径；传["."]暂存全部。路径相对仓库，按字面匹配。"""
        return store.git_add(repo_id, paths)
