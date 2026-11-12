from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='pc_restore_recycled_file', description='从回收站恢复文件，已有目标不覆盖。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.pc_restore_recycled_file)
