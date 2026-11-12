from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=True, openWorldHint=False))
    def delete_file(path: str, recursive: bool = False) -> dict:
        """删除文件或空目录；非空目录须recursive=true。操作限files内部；不存在的路径按空操作处理。"""
        return store.delete_file(path, recursive)
