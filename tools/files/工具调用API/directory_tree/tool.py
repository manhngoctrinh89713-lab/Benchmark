from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
    def directory_tree(path: str = ".", max_depth: int = 4, exclude_patterns: list[str] | None = None) -> dict:
        """读取目录树，max_depth为1..20，默认4层；深度边界以depth_limited标记。可排除模式匹配的条目及其子树。最多遍历10000项。"""
        return store.directory_tree(path, max_depth, exclude_patterns)
