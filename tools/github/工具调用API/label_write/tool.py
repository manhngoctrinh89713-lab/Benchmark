from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=False, openWorldHint=False))
    def label_write(repo_id: str, name: str, color: str | None = None, description: str | None = None, new_name: str | None = None) -> dict:
        """创建或更新标签，支持重命名并同步Issue/PR引用；颜色为不带#的六位十六进制。"""
        return store.label_write(repo_id, name, color, description, new_name)
