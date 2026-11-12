from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='pc_list_recycle_bin', description='列出可恢复的个人文件。', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))(store.pc_list_recycle_bin)
