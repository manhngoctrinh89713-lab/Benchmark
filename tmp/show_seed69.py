import re,pathlib
text=pathlib.Path(r'D:\DeskTop\my_benchmark\AAA_core_data\种子.md').read_text(encoding='utf-8')
m=re.search(r'(?ms)^# 种子69\s*$.*?(?=^# 种子\d+$|\Z)',text)
print(m.group(0) if m else 'not found')
