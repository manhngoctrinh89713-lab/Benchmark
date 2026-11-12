from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='server_write_file', description='在登记挂载点创建或修改文本文件；服务配置沿用专用配置入口。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.server_write_file)
