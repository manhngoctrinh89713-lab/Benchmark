import json
rows = json.load(open(r'tmp/seeds_parsed.json', encoding='utf-8'))
for r in rows:
    f = r['fields']
    cat = f.get('问题类别', '').split('（')[0].strip()
    print(f"{r['seed']}\t{cat}\t{f.get('工具套件','')}\t{f.get('任务目标','')}")
