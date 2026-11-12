from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='pc_move_personal_file', description='移动或重命名个人文件，核对源文件且不覆盖目标。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.pc_move_personal_file)
