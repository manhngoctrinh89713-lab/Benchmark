from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='restore_trash', description='恢复回收站项目到原路径或新路径，已有文件不覆盖。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.restore_trash)
