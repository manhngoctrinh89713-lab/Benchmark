# Adapted from modelcontextprotocol/servers-archived SQLite MCP (MIT).
from contextlib import closing


def execute_bound(connection, query, params=None, max_rows=1001):
    """Bind parameters on an already controlled connection; preserve duplicate column names."""
    with closing(connection.cursor()) as cursor:
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        columns = [item[0] for item in cursor.description] if cursor.description else []
        rows = cursor.fetchmany(max_rows) if cursor.description else []
        return {"columns": columns, "rows": [list(row) for row in rows]}
