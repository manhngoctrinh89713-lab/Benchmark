from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=True, openWorldHint=False))
    def edit_file(path: str, edits: list[dict[str, str]], dry_run: bool = False, expected_sha256: str | None = None) -> dict:
        """顺序应用oldText/newText精确替换；每次oldText必须恰好出现一次，不做模糊匹配。UTF-8文本，比较时规范化CRLF，写回保留原首个换行样式。dry_run只返回diff不修改文件或事件；可传expected_sha256。"""
        return store.edit_file(path, edits, dry_run, expected_sha256)
