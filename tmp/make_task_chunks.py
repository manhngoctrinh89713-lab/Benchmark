import json
rows=json.load(open(r'D:\DeskTop\my_benchmark\tmp\seeds_parsed.json',encoding='utf-8'))
for idx in range(3):
    chunk=rows[idx*21:(idx+1)*21]
    with open(rf'D:\DeskTop\my_benchmark\tmp\seed_tasks_{idx+1}.txt','w',encoding='utf-8') as out:
        for r in chunk:
            f=r['fields']; cat=f.get('问题类别','').split('（')[0]
            out.write(f"{r['seed']:02d} | {cat:<30} | {f.get('工具套件',''):<16} | {f.get('任务目标','')}\n")
