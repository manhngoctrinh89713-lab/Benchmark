import pathlib, hashlib, json
root=pathlib.Path(r'D:\DeskTop\my_benchmark')
archive=root/'.archive'/'seed52-20261112'
readme='''# 种子52归档（2026-11-12）

## 归档原因

种子52与种子46在类别、工具、用户指令结构、危险写入动作和安全处理路径上高度重合，区别主要是改价前检查的约束不同：46检查成本与最低限价审批，52检查近7天已付款订单的价保敞口。为避免同一模板换字段重复占用种子池和生成示例，保留46，归档52。

## 归档内容

- `AAA_core_data/种子.md`：归档时的种子52七字段条目。
- `AAA_core_data/关键证据.md`：归档时的关键证据条目。
- `AAA_core_data/种子交付前自查.md`：归档时的自查条目。
- `初始环境/种子52/`：完整初始环境。
- `prompt/cases/种子52/`：配置与测试指令。
- `评测函数/种子52.py`：确定性评测函数。
- `src/fixtures/build_seeds_50_52.py`：归档前的共享构建脚本快照；活动脚本已移除52构建入口，保留50。
- `src/tests/`：归档前的组合测试快照；活动测试已移除52用例。

## 当前状态

- 编号保留，不参与当前评测。
- 默认批量种子、`--all-seeds`、prompt、初始环境、评测函数和组合测试均已排除种子52。
- 历史运行记录和审计报告未改写；`关键证据审计.md` 中52-x记录作为历史保留。
'''
(archive/'README.md').write_text(readme,encoding='utf-8')
files=[]
for p in sorted(archive.rglob('*')):
    if p.is_file() and p.name!='manifest.json':
        files.append({'path':str(p.relative_to(archive)).replace('\\','/'),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(archive/'manifest.json').write_text(json.dumps({'seed':52,'archived_at':'2026-11-12','reason':'template overlap with seed 46','files':files},ensure_ascii=False,indent=2),encoding='utf-8')
print('archive files',len(files)+1)
