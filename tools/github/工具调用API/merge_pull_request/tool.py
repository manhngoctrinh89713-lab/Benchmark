from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=True, openWorldHint=False))
    def merge_pull_request(repo_id: str, number: int, expected_head_sha: str) -> dict:
        """真实合并PR，须当前位于干净base分支、head SHA与预期一致、非草稿、满足当前提交评审要求。冲突则恢复操作前仓库和协作数据。"""
        return store.merge_pull_request(repo_id, number, expected_head_sha)
