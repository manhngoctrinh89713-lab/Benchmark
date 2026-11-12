from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=False, openWorldHint=False))
    def create_pull_request(repo_id: str, title: str, head: str, base: str = "main", body: str = "", draft: bool = False) -> dict:
        """为本地head/base分支创建模拟PR，head须有超出base的提交，重复未关闭PR报错。"""
        return store.create_pull_request(repo_id, title, head, base, body, draft)
