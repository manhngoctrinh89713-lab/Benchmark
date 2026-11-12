from mcp.types import ToolAnnotations


def register(mcp, store):
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, destructiveHint=False, openWorldHint=False))
    def mark_notification_read(notification_id: int) -> dict:
        """将属于当前用户的本地通知标记为已读。"""
        return store.mark_notification_read(notification_id)
