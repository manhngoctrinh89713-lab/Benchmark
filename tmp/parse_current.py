import re,json,pathlib
p=pathlib.Path(r'D:\DeskTop\my_benchmark\AAA_core_data\种子.md')
text=p.read_text(encoding='utf-8')
parts=re.split(r'(?m)^# 种子(\d+)\s*$',text)
rows=[]
for i in range(1,len(parts),2):
 n=int(parts[i]); body=parts[i+1]
 fields={}
 for line in body.splitlines():
  m=re.match(r'\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|$',line)
  if m:
   k=m.group(1).strip(); v=m.group(2).strip()
   if k not in ('字段','---') and not set(k)<=set('- '): fields[k]=v
 status='implemented'
 if '实现状态：方案定义' in body: status='planned'
 rows.append({'seed':n,'status':status,'fields':fields})
out=pathlib.Path(r'D:\DeskTop\my_benchmark\tmp\seeds_current.json')
out.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print('count',len(rows),'ids',[r['seed'] for r in rows])
print('planned',[r['seed'] for r in rows if r['status']=='planned'])
