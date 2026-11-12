from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='delete_code_file', description='按当前校验值删除代码文件，可先预览差异。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.delete_code_file)
