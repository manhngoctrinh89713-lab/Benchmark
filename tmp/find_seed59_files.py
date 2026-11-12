from pathlib import Path
root=Path(r'D:\DeskTop\my_benchmark')
for p in root.rglob('*.md'):
    try: t=p.read_text(encoding='utf-8')
    except Exception: continue
    if '# 种子59' in t:
        print(p)
