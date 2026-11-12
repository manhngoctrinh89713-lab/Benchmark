import json,sys
rows=json.load(open(r'D:\DeskTop\my_benchmark\tmp\seeds_parsed.json',encoding='utf-8'))
ids=set(map(int,sys.argv[1:]))
for r in rows:
    if r['seed'] not in ids: continue
    f=r['fields']
    print(f"\n{r['seed']} [{f.get('问题类别','').split('（')[0]}] [{f.get('工具套件','')}]")
    print('TASK:',f.get('任务目标',''))
    print('TEST:',f.get('测试指令',''))
    print('ISSUE:',next((v for k,v in f.items() if k.startswith('指令问题')),''))
