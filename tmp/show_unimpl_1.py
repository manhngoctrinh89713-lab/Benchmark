import re,pathlib
text=pathlib.Path(r'D:\DeskTop\my_benchmark\AAA_core_data\种子.md').read_text(encoding='utf-8')
parts=re.split(r'(?m)^(# 种子(\d+)\s*)$',text)
for i in range(1,len(parts),3):
 n=int(parts[i+1])
 if 59<=n<=63:
  print('\n'+parts[i]+parts[i+2])
