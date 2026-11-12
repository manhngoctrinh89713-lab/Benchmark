from mcp.types import ToolAnnotations

def register(server, store):
    server.tool(name='write_spreadsheet', description='按校验值批量修改XLSX单元格，保留其他内容和格式。updates每项为cell和value，支持数值、文本、布尔、null及以=开头的公式；最多2000格。公式由读取接口按支持范围计算，Excel打开后重新计算。', annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))(store.write_spreadsheet)
