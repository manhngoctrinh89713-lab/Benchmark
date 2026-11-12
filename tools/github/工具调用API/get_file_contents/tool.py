from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def get_file_contents(repo_id: str, path: str = "", ref: str | None = None) -> dict:
        """浏览已提交的文件或目录；默认读取默认分支，忽略工作区未提交修改。"""
        return store.get_file_contents(repo_id, path, ref)
