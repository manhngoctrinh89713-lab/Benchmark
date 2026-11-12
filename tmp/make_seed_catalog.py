import json

rows = json.load(open(r'tmp/seeds_parsed.json', encoding='utf-8'))
with open(r'tmp/seed_catalog.md', 'w', encoding='utf-8') as out:
    out.write('# 现有种子目录（用于查重，不要照抄场景）\n\n')
    out.write('| 编号 | 类别 | 工具套件 | 任务目标 | 失败判据要点 |\n')
    out.write('| --- | --- | --- | --- | --- |\n')
    for r in rows:
        f = r['fields']
        cat = f.get('问题类别', '').split('（')[0].strip()
        goal = f.get('任务目标', '').replace('|', '／').replace('\n', ' ')
        fail = f.get('失败判据', '').replace('|', '／').replace('\n', ' ')
        if len(fail) > 180:
            fail = fail[:180] + '…'
        out.write(f"| {r['seed']} | {cat} | {f.get('工具套件','')} | {goal} | {fail} |\n")
