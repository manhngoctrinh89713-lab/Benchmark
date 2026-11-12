from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='extract_archive', description='将 ZIP 解压到指定目录；预先检查全部目标、重复项和大小后统一提交。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.extract_archive)
