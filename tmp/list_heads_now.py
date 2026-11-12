import re
from pathlib import Path
t=Path(r'D:\DeskTop\my_benchmark\AAA_core_data\种子.md').read_text(encoding='utf-8')
heads=re.findall(r'(?m)^# 种子(\d+)\s*$',t)
print(heads)
