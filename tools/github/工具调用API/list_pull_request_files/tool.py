from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='list_pull_request_files', description='基于 PR 当前基线和提交列出变更路径、状态及增删行数。', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))(store.list_pull_request_files)
