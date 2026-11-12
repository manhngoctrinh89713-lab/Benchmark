from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='pc_recycle_file', description='将个人文件移入回收站，保留内容和原始路径。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.pc_recycle_file)
