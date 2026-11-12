from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='delete_database', description='删除指定数据库并记录删除前快照，按当前文件校验值核对目标。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.delete_database)
