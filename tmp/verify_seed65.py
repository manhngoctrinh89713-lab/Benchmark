import re,pathlib
root=pathlib.Path(r'D:\DeskTop\my_benchmark\AAA_core_data')
for name in ['种子.md','种子交付前自查.md']:
 t=(root/name).read_text(encoding='utf-8')
 m=re.search(r'(?ms)^# 种子65\s*$.*?(?=^# 种子\d+\s*$|\Z)',t)
 assert m, name
 sec=m.group(0)
 print(name, 'chars', len(sec))
 for key in ['问题类别','工具套件','任务目标','失败判据','环境依据','测试指令']:
  assert key in sec, (name,key)
 print('  category FI:', 'Factual Inconsistency' in sec)
 print('  explicit negative:', '还是无法上传' in sec)
 print('  old phone claim gone:', '电话里确认' not in sec)
