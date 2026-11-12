from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=False, openWorldHint=False))
    def create_release(repo_id: str, tag: str, name: str, body: str = "", target: str | None = None, draft: bool = False, prerelease: bool = False) -> dict:
        """创建本地Release，并在真实本地Git中创建缺失的轻量tag；不会推送；已有tag不可移动。"""
        return store.create_release(repo_id, tag, name, body, target, draft, prerelease)
