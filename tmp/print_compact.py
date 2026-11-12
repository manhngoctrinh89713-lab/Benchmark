import json,sys
rows=json.load(open(r'D:\DeskTop\my_benchmark\tmp\seeds_parsed.json',encoding='utf-8'))
for r in rows:
    f=r['fields']; print(f"{r['seed']:02d}|{f.get('问题类别','').split('（')[0]}|{f.get('工具套件','')}|{f.get('测试指令','')}|{next((v for k,v in f.items() if k.startswith('指令问题')),'')}")
