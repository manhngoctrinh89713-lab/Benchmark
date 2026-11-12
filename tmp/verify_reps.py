import re,pathlib,collections
p=pathlib.Path(r'D:\DeskTop\my_benchmark\AAA_core_data\种子代表集_18条_垂直正交.md')
t=p.read_text(encoding='utf-8')
heads=[(int(m.group(1)),m.start()) for m in re.finditer(r'(?m)^# 种子(\d+)\s*$',t)]
print('count',len(heads),[n for n,_ in heads])
print('double separators',len(re.findall(r'(?m)^---\s*\n\s*\n---\s*$',t)))
# parse fields and coverage
cat=collections.Counter(); tools=collections.Counter()
for j,(n,pos) in enumerate(heads):
    end=heads[j+1][1] if j+1<len(heads) else len(t)
    sec=t[pos:end]
    catm=re.search(r'\| 问题类别\s*\|\s*([^（|]+)',sec)
    toolm=re.search(r'\| 工具套件\s*\|\s*([^|]+)',sec)
    cat[catm.group(1).strip() if catm else '?']+=1
    if toolm:
        for x in toolm.group(1).replace('（工具未修改）','').split('、'): tools[x.strip()]+=1
print('categories',cat)
print('tools',tools)
print('bytes',p.stat().st_size)
