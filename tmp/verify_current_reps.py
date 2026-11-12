import re,pathlib,collections,json
root=pathlib.Path(r'D:\DeskTop\my_benchmark')
t=(root/'AAA_core_data'/'种子代表集_18条_垂直正交.md').read_text(encoding='utf-8')
heads=[int(m.group(1)) for m in re.finditer(r'(?m)^# 种子(\d+)\s*$',t)]
cat=collections.Counter(); tools=collections.Counter()
for m in re.finditer(r'(?m)^# 种子(\d+)\s*$',t):
 end=t.find('\n# 种子',m.end())
 sec=t[m.start():end if end>=0 else len(t)]
 c=re.search(r'\| 问题类别\s*\|\s*([^（|]+)',sec)
 if c: cat[c.group(1).strip()]+=1
 tm=re.search(r'\| 工具套件\s*\|\s*([^|]+)',sec)
 if tm:
  for x in tm.group(1).replace('（工具未修改）','').split('、'): tools[x.strip()]+=1
print('ids',heads,'count',len(heads))
print('cats',cat)
print('tools',tools)
# verify current seed coverage mapping from notes content indirectly
rows=json.loads((root/'tmp'/'seeds_current.json').read_text(encoding='utf-8'))
allids={r['seed'] for r in rows}
print('current seed count',len(allids))
