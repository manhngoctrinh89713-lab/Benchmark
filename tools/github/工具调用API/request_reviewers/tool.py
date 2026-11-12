from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=False, openWorldHint=False))
    def request_reviewers(repo_id: str, number: int, reviewers: list[str]) -> dict:
        """为打开的PR追加评审者；不能请求作者本人评审；只记录本地请求，不发送通知。"""
        return store.request_reviewers(repo_id, number, reviewers)
