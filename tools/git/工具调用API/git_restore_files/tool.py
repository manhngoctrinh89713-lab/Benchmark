from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='git_restore_files', description='用指定提交恢复选定文件的工作区内容，可同时恢复暂存区。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.git_restore_files)
