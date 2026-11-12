from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=False, openWorldHint=False))
    def add_pull_request_review_comment(repo_id: str, number: int, path: str, line: int, body: str, expected_head_sha: str) -> dict:
        """在PR差异的RIGHT侧代码行添加本地评审评论，绑定预期head SHA；行号从1开始。"""
        return store.add_pull_request_review_comment(repo_id, number, path, line, body, expected_head_sha)
