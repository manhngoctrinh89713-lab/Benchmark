from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def read_multiple_files(paths: list[str], encoding: str | None = None) -> dict:
        """批量读取1..20个文件，文本、PDF、DOCX、PPTX、XLSX/XLS、HTML与图片均可，单文件错误不影响其余。返回items，失败项含error；各文件内容合计最多200000字符。"""
        return store.read_multiple_files(paths, encoding)
