from typing import Literal
from pydantic import StrictInt, StrictBool
from mcp.types import ToolAnnotations


def register(server, store):
    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    def server_query_logs(service_id: str | None = None, max_priority: StrictInt = 7, since: str | None = None, until: str | None = None, query: str = '', offset: StrictInt = 0, limit: StrictInt = 20):
        '查询真实场景JSONL日志；优先级0最严重，筛选0..max_priority，结果按时间倒序。'
        return store.server_query_logs(service_id=service_id, max_priority=max_priority, since=since, until=until, query=query, offset=offset, limit=limit)
