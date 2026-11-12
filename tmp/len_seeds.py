import json,statistics
rows=json.load(open(r'D:\DeskTop\my_benchmark\tmp\seeds_parsed.json',encoding='utf-8'))
lens=[]
for r in rows:
    f=r['fields']
    n=sum(len(v) for v in f.values())
    lens.append(n)
print('mean chars',statistics.mean(lens),'median',statistics.median(lens),'min',min(lens),'max',max(lens),'total',sum(lens))
