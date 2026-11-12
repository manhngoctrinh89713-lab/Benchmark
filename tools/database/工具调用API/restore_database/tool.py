from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='restore_database', description='用工作区内的 SQLite 备份替换已登记数据库，核对当前校验值及备份完整性。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.restore_database)
