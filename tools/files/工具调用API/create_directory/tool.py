from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def create_directory(path: str) -> dict:
        """创建目录及父目录，已存在目录返回created=false；不能对files根目录执行修改。"""
        return store.create_directory(path)
