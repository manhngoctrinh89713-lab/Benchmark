from mcp.types import ToolAnnotations

def register(server, store):
    server.tool(name='read_spreadsheet', description='读取XLSX指定区域的原值、公式和按当前依赖计算的结果。支持跨表引用、四则运算、SUM/MIN/MAX、ROUND和精确VLOOKUP；不支持的公式明确返回错误，不使用缓存冒充重算。单次最多2000格。', annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))(store.read_spreadsheet)
