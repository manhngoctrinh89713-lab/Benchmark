import re,pathlib
text=pathlib.Path(r'D:\DeskTop\my_benchmark\AAA_core_data\种子.md').read_text(encoding='utf-8')
parts=re.split(r'(?m)^(# 种子(\d+)\s*)$',text)
for i in range(1,len(parts),3):
 n=int(parts[i+1]); body=parts[i+2]
 if '实现状态' in body:
  print(n, [line.strip() for line in body.splitlines() if '实现状态' in line][0])
