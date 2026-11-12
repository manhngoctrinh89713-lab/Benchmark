from mcp.types import ToolAnnotations


def register(server, store):
    server.tool(name='set_item_labels', description='替换 Issue 或 PR 上的标签，空列表清空。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.set_item_labels)
