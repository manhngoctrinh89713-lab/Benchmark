from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def pull_request_read(repo_id: str, number: int) -> dict:
        """读取PR、当前分支SHA、三点diff、评论和绑定提交的评审。"""
        return store.pull_request_read(repo_id, number)
