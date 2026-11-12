from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='git_file_history', description='查询文件历史，跟踪单文件重命名。', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))(store.git_file_history)
