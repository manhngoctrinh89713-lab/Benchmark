from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
    def git_merge(repo_id: str, operation: str = "start", source: str | None = None,
                  message: str | None = None, ff_mode: str = "ff") -> dict:
        """合并提交或分支到当前本地分支。operation=start/continue/abort；start需source，ff_mode=ff/no-ff/ff-only，message可选。开始前须无进行中操作且工作区干净。冲突返回conflicts并保留现场，编辑文件、git_add后continue，也可abort。不会自动fetch或push。"""
        return store.git_merge(repo_id, operation, source, message, ff_mode)
