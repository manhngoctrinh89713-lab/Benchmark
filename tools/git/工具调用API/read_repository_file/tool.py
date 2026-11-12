from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def read_repository_file(repo_id: str, path: str, revision: str | None = None) -> dict:
        """读取UTF-8代码文件，省略revision读取工作区，否则读取指定提交版本；不允许访问.git。"""
        return store.read_repository_file(repo_id, path, revision)
