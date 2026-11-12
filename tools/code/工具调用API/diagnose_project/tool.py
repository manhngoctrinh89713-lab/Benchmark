from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='diagnose_project', description='对匹配文件分页进行静态语法诊断，不运行项目代码。', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))(store.diagnose_project)
