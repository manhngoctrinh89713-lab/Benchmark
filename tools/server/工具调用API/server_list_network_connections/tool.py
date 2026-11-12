from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='server_list_network_connections', description='查询环境最近记录的网络连接和监听端口，返回观测时间与所属进程。', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))(store.server_list_network_connections)
