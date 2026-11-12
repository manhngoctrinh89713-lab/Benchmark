from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=True, openWorldHint=False))
    def move_file(source: str, destination: str) -> dict:
        """移动或重命名文件/目录，目标必须不存在，自动创建目标父目录。拒绝源目标嵌套、链接及files根目录。"""
        return store.move_file(source, destination)
