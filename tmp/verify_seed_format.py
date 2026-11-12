import re
import sys

path = sys.argv[1]
text = open(path, encoding='utf-8').read()
blocks = re.split(r'(?m)^# ', text)
rows = []
for block in blocks[1:]:
    title, _, body = block.partition('\n')
    title = title.strip()
    if not title.startswith('种子'):
        continue
    fields = {}
    for line in body.splitlines():
        m = re.match(r'\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|\s*$', line)
        if not m:
            continue
        key, val = m.group(1).strip(), m.group(2).strip()
        if key in ('字段', '---') or set(key) <= set('-: '):
            continue
        fields[key] = val
    rows.append((title, fields))

errors = []
for title, f in rows:
    if len(f) != 7:
        errors.append(f'{title}: 字段数 {len(f)}，应为 7 -> {list(f)}')
    cat = f.get('问题类别', '')
    issue_keys = [k for k in f if k.startswith('指令问题')]
    if len(issue_keys) != 1:
        errors.append(f'{title}: 指令问题字段数量 {len(issue_keys)}')
        continue
    issue_key = issue_keys[0]
    if cat.startswith('Requirement Underspecification'):
        expected = '指令问题（缺失的要求）'
    elif cat.startswith('Requirement Infeasibility'):
        expected = '指令问题（不合理的要求）'
    elif cat.startswith('Factual Inconsistency'):
        expected = '指令问题（错误的事实描述）'
        alt = '指令问题（错误的事实推断）'
        if issue_key not in (expected, alt):
            errors.append(f'{title}: 指令问题标题 {issue_key}，期望 {expected} 或 {alt}')
    else:
        errors.append(f'{title}: 未知问题类别 {cat!r}')
        continue
    if cat.startswith(('Requirement Underspecification', 'Requirement Infeasibility')) and issue_key != expected:
        errors.append(f'{title}: 指令问题标题 {issue_key}，期望 {expected}')
    if any(k == '关键事实' for k in f):
        errors.append(f'{title}: 不应包含关键事实字段')
    for k in ('问题类别', '工具套件', '任务目标', '失败判据', '环境依据', '测试指令'):
        if not f.get(k):
            errors.append(f'{title}: 字段 {k} 为空')

print(f'seeds={len(rows)} errors={len(errors)}')
for e in errors:
    print(' -', e)
