import re,pathlib
base=pathlib.Path(r'D:\DeskTop\my_benchmark\AAA_core_data')
for name in ['种子.md','种子交付前自查.md']:
 p=base/name
 t=p.read_text(encoding='utf-8')
 heads=re.findall(r'(?m)^# 种子(\d+)\s*$',t)
 print(name,'headings',len(heads),'65 count',heads.count('65'))
 print('double separators',len(re.findall(r'(?m)^---\s*\n\s*\n---\s*$',t)))
