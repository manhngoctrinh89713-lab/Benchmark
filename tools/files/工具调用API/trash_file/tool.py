from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='trash_file', description='将文件或目录移入服务回收站，保存原始路径以便恢复。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.trash_file)
