import json,sys
rows=json.load(open(r'D:\DeskTop\my_benchmark\tmp\seeds_current.json',encoding='utf-8'))
ids=set(map(int,sys.argv[1:]))
for r in rows:
 if r['seed'] not in ids: continue
 f=r['fields']
 print(f"\n===== SEED {r['seed']} [{r['status']}] =====")
 for k,v in f.items(): print(f'{k}: {v}')
