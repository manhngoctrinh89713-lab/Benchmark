import re
from pathlib import Path
root=Path(r'D:\DeskTop\my_benchmark\AAA_core_data')
checks=[
 ('种子.md', ['# 种子59','# 种子60']),
 ('种子代表集_18条_垂直正交.md', ['# 种子59','# 种子63']),
 ('关键证据.md', ['# 种子59','# 种子60']),
 ('种子交付前自查.md', ['# 种子59','# 种子60']),
]
for name, markers in checks:
    p=root/name
    with p.open('r', encoding='utf-8', newline='') as f: t=f.read()
    start=t.index(markers[0]); end=t.index(markers[1],start)
    sec=t[start:end]
    print('='*20,name,'='*20)
    print('CRLF',t.count('\r\n'),'LF',t.count('\n'))
    print(sec[:1800])
    print('...')
    print(sec[-300:])
