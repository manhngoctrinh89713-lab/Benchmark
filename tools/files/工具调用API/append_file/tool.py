from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='append_file', description='在现有 UTF-8 文件末尾追加文本，并核对修改前的校验值。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.append_file)
