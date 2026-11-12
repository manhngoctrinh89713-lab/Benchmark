from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=True, openWorldHint=False))
    def write_repository_file(repo_id: str, path: str, content: str, overwrite: bool = False) -> dict:
        """写入UTF-8工作文件，不自动暂存。默认不覆盖，最大1 MiB，不允许修改.git。"""
        return store.write_repository_file(repo_id, path, content, overwrite)
