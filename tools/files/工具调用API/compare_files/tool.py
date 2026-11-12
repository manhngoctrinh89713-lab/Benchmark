from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='compare_files', description='比较两份文件的字节内容，可返回 UTF-8 文本差异。', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))(store.compare_files)
