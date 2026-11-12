from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=False, openWorldHint=False))
    def submit_review(repo_id: str, number: int, event: str, body: str = "") -> dict:
        """提交模拟评审，event为APPROVE/REQUEST_CHANGES/COMMENT，绑定当前head SHA。不能批准或请求修改自己的PR。"""
        return store.submit_review(repo_id, number, event, body)
