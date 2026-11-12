from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='git_rename_branch', description='重命名本地分支，目标名称已存在时失败。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.git_rename_branch)
