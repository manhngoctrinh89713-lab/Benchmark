import json
rows=json.load(open(r'D:\DeskTop\my_benchmark\tmp\seeds_parsed.json',encoding='utf-8'))
for r in rows:
    f=r['fields']
    cat=f.get('问题类别','').split('（')[0]
    print(f"{r['seed']:02d} | {cat} | {f.get('工具套件','')} | {f.get('任务目标','')}")
