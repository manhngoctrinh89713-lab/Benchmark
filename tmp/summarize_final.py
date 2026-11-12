import re
import sys
from collections import Counter

path = sys.argv[1]
text = open(path, encoding='utf-8').read()
blocks = re.split(r'(?m)^# 种子', text)[1:]
cats = Counter()
tools = Counter()
for block in blocks:
    lines = block.splitlines()
    num = lines[0].strip()
    fields = {}
    for line in lines:
        m = re.match(r'\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|\s*$', line)
        if m:
            key, val = m.group(1).strip(), m.group(2).strip()
            if key != '字段' and not set(key) <= set('-: '):
                fields[key] = val
    cat = fields.get('问题类别', '').split('（')[0].strip()
    cats[cat] += 1
    for t in fields.get('工具套件', '').replace('（工具未修改）', '').split('、'):
        tools[t.strip()] += 1
    print(f"{num}: {cat} | {fields.get('工具套件','')} | {fields.get('任务目标','')[:50]}")
print('CATEGORIES', dict(cats))
print('TOOLS', dict(tools))
