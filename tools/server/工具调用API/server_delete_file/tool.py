from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='server_delete_file', description='删除常规文件，核对当前内容并检查进程占用。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.server_delete_file)
