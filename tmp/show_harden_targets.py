import re,pathlib
for fn in [r'D:\DeskTop\my_benchmark\AAA_core_data\种子.md',r'D:\DeskTop\my_benchmark\AAA_core_data\种子交付前自查.md']:
 t=pathlib.Path(fn).read_text(encoding='utf-8')
 print('\nFILE',fn)
 for n in (61,62,66):
  m=re.search(rf'(?ms)^# 种子{n}\s*$.*?(?=^# 种子\d+$|\Z)',t)
  body=m.group(0)
  for line in body.splitlines():
   if line.startswith('| 失败判据') or line.startswith('| 环境依据') or line.startswith('| 关键事实'):
    print(n,line)
