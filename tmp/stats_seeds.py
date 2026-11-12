import json,collections
rows=json.load(open(r'D:\DeskTop\my_benchmark\tmp\seeds_parsed.json',encoding='utf-8'))
cs=collections.Counter(); ts=collections.Counter(); combos=collections.Counter()
for r in rows:
    f=r['fields']; cs[f.get('问题类别','').split('（')[0]]+=1
    suites=[x.strip() for x in f.get('工具套件','').replace('（工具未修改）','').split('、')]
    combos['+'.join(suites)]+=1
    for s in suites: ts[s]+=1
print('CATEGORIES',cs)
print('TOOLS',ts)
print('COMBOS')
for k,v in combos.most_common(): print(v,k)
