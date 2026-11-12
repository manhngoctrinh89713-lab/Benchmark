import re,pathlib
text=pathlib.Path(r'D:\DeskTop\my_benchmark\AAA_core_data\种子.md').read_text(encoding='utf-8')
parts=re.split(r'(?m)^(# 种子(\d+)\s*)$',text)
print('parts',len(parts))
for i in range(1,min(len(parts),19),3):
 print(parts[i],len(parts[i+2]))
print('total chars',len(text))
