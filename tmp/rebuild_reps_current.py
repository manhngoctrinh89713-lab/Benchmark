import re,pathlib
root=pathlib.Path(r'D:\DeskTop\my_benchmark')
text=(root/'AAA_core_data'/'种子.md').read_text(encoding='utf-8')
parts=re.split(r'(?m)^(# 种子(\d+)\s*)$',text)
sections={}
for i in range(1,len(parts),3):
    heading=parts[i].strip(); num=int(parts[i+1]); body=parts[i+2]
    body=re.sub(r'(?m)^> 实现状态：.*\n\s*','',body)
    body=re.sub(r'\n---\s*$','',body).strip()
    sections[num]=(heading+'\n\n'+body).strip()
selected=[2,3,4,5,8,9,12,22,24,26,28,34,36,59,64,66,67,69]
missing=[n for n in selected if n not in sections]
assert not missing, missing
header='''# 种子代表集（18 条，垂直正交｜当前 62 条版本）

> 用途：作为生成新种子时的 few-shot 示例，而不是完整种子清单。以下只保留不同风险机制的代表；具体业务名、金额、对象和场景应重新构思，避免复刻示例。

'''
out=root/'AAA_core_data'/'种子代表集_18条_垂直正交.md'
out.write_text(header + '\n\n---\n\n'.join(sections[n] for n in selected) + '\n',encoding='utf-8')
print('selected',selected)
print('chars',len(out.read_text(encoding='utf-8')))
