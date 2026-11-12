import re
from pathlib import Path
p=Path(r'D:\DeskTop\my_benchmark\AAA_core_data\种子.md')
t=p.read_text(encoding='utf-8')
heads=re.findall(r'(?m)^# 种子(\d+)\s*$',t)
print('count',len(heads),'last',heads[-5:])
print('59 sections',len(re.findall(r'(?m)^# 种子59\s*$',t)))
print('double separators',len(re.findall(r'(?m)^---\s*\n\s*\n---\s*$',t)))
# 验证四个文件的59字段数
base=Path(r'D:\DeskTop\my_benchmark\AAA_core_data')
for name in ['种子.md','种子代表集_18条_垂直正交.md','种子交付前自查.md']:
    s=(base/name).read_text(encoding='utf-8')
    m=re.search(r'(?ms)^# 种子59\s*$.*?(?=^# 种子\d+$|\Z)',s)
    sec=m.group(0)
    print(name,'fields',len(re.findall(r'(?m)^\| (?:问题类别|工具套件|任务目标|失败判据|环境依据|测试指令|指令问题|关键事实)',sec)))
