from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='compare_code_files', description='比较项目中两份代码的文本及校验值。', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))(store.compare_code_files)
