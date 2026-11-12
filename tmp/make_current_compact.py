import json,pathlib
root=pathlib.Path(r'D:\DeskTop\my_benchmark')
rows=json.loads((root/'tmp'/'seeds_current.json').read_text(encoding='utf-8'))
for idx in range(4):
    chunk=rows[idx*16:(idx+1)*16]
    lines=[]
    for r in chunk:
        f=r['fields']; cat=f.get('问题类别','').split('（')[0]
        issue=next((v for k,v in f.items() if k.startswith('指令问题')),'')
        lines.append(f"===== {r['seed']:02d} | {cat} | {f.get('工具套件','')} =====\nTASK: {f.get('任务目标','')}\nTEST: {f.get('测试指令','')}\nISSUE: {issue}\n")
    (root/'tmp'/f'current_compact_{idx+1}.txt').write_text('\n'.join(lines),encoding='utf-8')
print('written')
