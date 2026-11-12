from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='move_code_file', description='在项目内移动代码文件，保留文本内容；返回删除与新增的统一预览。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.move_code_file)
