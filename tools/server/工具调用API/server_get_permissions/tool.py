from pydantic import StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def server_get_permissions(path: str, recursive: StrictBool = False):
        '读取服务器路径的所有者、用户组和权限模式；递归时包含整棵子树。'
        return store.server_get_permissions(path=path, recursive=recursive)
