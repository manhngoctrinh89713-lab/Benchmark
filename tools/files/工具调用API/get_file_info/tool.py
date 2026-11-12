from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def get_file_info(path: str) -> dict:
        """读取文件或目录元数据；文件返回原字节SHA-256。文件最大25 MiB。"""
        return store.get_file_info(path)
