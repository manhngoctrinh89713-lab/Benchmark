import json,collections
rows=json.load(open(r'D:\DeskTop\my_benchmark\tmp\seeds_current.json',encoding='utf-8'))
cat=collections.Counter(); tools=collections.Counter(); planned=collections.Counter()
for r in rows:
 f=r['fields']; c=f.get('问题类别','').split('（')[0]; cat[c]+=1
 if r['status']=='planned': planned[c]+=1
 for t in f.get('工具套件','').replace('（工具未修改）','').split('、'): tools[t.strip()]+=1
print('total',len(rows)); print('categories',cat); print('planned',planned); print('tools',tools)
for r in rows:
 if r['status']=='planned': print(f"{r['seed']:02d} | {r['fields'].get('问题类别','').split('（')[0]} | {r['fields'].get('工具套件','')} | {r['fields'].get('任务目标','')}")
