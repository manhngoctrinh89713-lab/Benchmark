import json
def format_json(rows):
    return json.dumps(rows, ensure_ascii=False)
