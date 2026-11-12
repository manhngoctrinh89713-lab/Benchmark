from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=True, destructiveHint=True, openWorldHint=False))
    def write_file(path: str, content: str, overwrite: bool = False, expected_sha256: str | None = None) -> dict:
        """以UTF-8创建或写入文本，自动创建父目录。默认不覆盖；覆盖须overwrite=true，可用expected_sha256防止覆盖读取后已变化的文件。"""
        return store.write_file(path, content, overwrite, expected_sha256)
