from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=False, openWorldHint=False))
    def copy_file(source: str, destination: str) -> dict:
        """复制文件或整个目录，保留文件原始字节；目标必须不存在，自动创建父目录。单文件25 MiB、总内容100 MiB、目录10000项以内。"""
        return store.copy_file(source, destination)
