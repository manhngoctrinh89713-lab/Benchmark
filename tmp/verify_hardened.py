import re,pathlib
for fn in [r'D:\DeskTop\my_benchmark\AAA_core_data\种子.md',r'D:\DeskTop\my_benchmark\AAA_core_data\种子交付前自查.md']:
 t=pathlib.Path(fn).read_text(encoding='utf-8')
 print('\nFILE',fn)
 for n in (61,62,66):
  sec=re.search(rf'(?ms)^# 种子{n}\s*$.*?(?=^# 种子\d+$|\Z)',t).group(0)
  line=next(x for x in sec.splitlines() if x.startswith('| 失败判据'))
  print(n, line)
