from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='pc_delete_recycled_file', description='永久删除回收站文件并释放空间。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.pc_delete_recycled_file)
