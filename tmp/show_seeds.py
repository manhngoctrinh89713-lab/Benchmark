import json,sys
rows=json.load(open(r'D:\DeskTop\my_benchmark\tmp\seeds_parsed.json',encoding='utf-8'))
lo,hi=map(int,sys.argv[1:3])
for r in rows:
    if not (lo<=r['seed']<=hi): continue
    f=r['fields']
    print(f"\n===== SEED {r['seed']} =====")
    for k in ('问题类别','工具套件','任务目标','失败判据','环境依据','测试指令'):
        print(f"{k}: {f.get(k,'')}")
    for k,v in f.items():
        if k.startswith('指令问题'): print(f"{k}: {v}")
