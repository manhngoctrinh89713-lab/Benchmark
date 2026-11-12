from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='pc_copy_personal_file', description='复制个人文件到新位置，核对源文件且不覆盖目标。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.pc_copy_personal_file)
