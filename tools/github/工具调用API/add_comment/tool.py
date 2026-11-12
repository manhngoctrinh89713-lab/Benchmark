from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=False, openWorldHint=False))
    def add_comment(repo_id: str, kind: str, number: int, body: str) -> dict:
        """为Issue或PR添加本地评论。kind为issue/pull_request；不向外部平台发送。"""
        return store.add_comment(repo_id, kind, number, body)
