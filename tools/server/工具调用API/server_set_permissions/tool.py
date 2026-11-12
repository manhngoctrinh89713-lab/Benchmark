from typing import Optional
from pydantic import StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
    def server_set_permissions(path: str, owner: Optional[str] = None, group: Optional[str] = None,
                               mode: Optional[str] = None, recursive: StrictBool = False):
        '调整服务器路径的所有者、用户组和权限模式（八进制，如 0755）；可递归应用于整棵子树。'
        return store.server_set_permissions(path=path, owner=owner, group=group, mode=mode,
                                            recursive=recursive)
