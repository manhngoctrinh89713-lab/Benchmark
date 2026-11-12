from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='list_pull_request_commits', description='列出 PR 当前分支相对基线包含的提交。', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))(store.list_pull_request_commits)
