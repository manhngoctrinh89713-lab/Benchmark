import json, sys
rows=json.load(open(r'tmp/seeds_current.json',encoding='utf-8'))
ids=[int(x) for x in sys.argv[1:]]
for r in rows:
    if r['seed'] not in ids: continue
    f=r['fields']
    issue=next((v for k,v in f.items() if k.startswith('指令问题')), '')
    print(f"### {r['seed']} {f.get('问题类别','')}\n目标: {f.get('任务目标','')}\n环境: {f.get('环境依据','')}\n指令: {f.get('测试指令','')}\n问题: {issue}\n")