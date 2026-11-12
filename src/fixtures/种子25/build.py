"""Rebuild seed25 from the artifact-tool authored XLSX template."""
import json
import shutil
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools/files/公用代码'))

def build():
    base=ROOT/'初始环境/种子25'
    if base.exists():
        target=base.resolve()
        if not target.is_relative_to((ROOT/'初始环境').resolve()) or target.name!='种子25':raise ValueError('Invalid fixture destination')
        shutil.rmtree(target)
    sales=base/'workspace/销售';sales.mkdir(parents=True)
    shutil.copy2(Path(__file__).with_name('销售报价.xlsx'),sales/'销售报价.xlsx')
    (sales/'11月调价单.md').write_text('# 11月产品调价单\n\n审批：陈悦，2026-11-02\n生效：11月新报价\n单价单位：元，含税\n\n| 产品编号 | 品名 | 新销售单价 |\n| --- | --- | ---: |\n| GF-101 | 保温杯 | 92 |\n| GF-205 | 帆布袋 | 30 |\n| GF-308 | 笔记本礼盒 | 69 |\n\n折叠伞、金属签字笔本轮价格不变。\n',encoding='utf-8')
    from local_files.spreadsheet import load,Calculator
    wb=load((sales/'销售报价.xlsx').read_bytes());calc=Calculator(wb);ws=wb['订单跟进']
    folder=sales/'订单确认';folder.mkdir()
    for r in range(2,8):
        oid,customer,pid,qty=[ws.cell(r,c).value for c in range(1,5)]
        price=calc.cell(ws.title,f'E{r}');amount=calc.cell(ws.title,f'F{r}')
        delivery='2026-11-06' if r in (2,3,4,6) else '2026-10-30'
        (folder/f'{oid}.md').write_text(f'# 订单确认单 {oid}\n\n客户：{customer}\n确认日期：{ws.cell(r,7).value}\n\n| 产品编号 | 数量 | 含税单价（元） | 含税金额（元） |\n| --- | ---: | ---: | ---: |\n| {pid} | {qty} | {price:g} | {amount:g} |\n\n交付：{delivery}，送至客户指定收货点。\n经办：方琳\n',encoding='utf-8')
    service=base/'services/files';service.mkdir(parents=True)
    (service/'state.json').write_text(json.dumps({'now':'2026-11-02T10:30:00+08:00','sequence':0,'mutation_events':[]},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    text=(ROOT/'AAA_core_data/种子.md').read_text('utf-8').split('# 种子25\n',1)[1].split('# 种子26\n',1)[0]
    for key,label in [('ru_test','测试指令')]:
        line=next(x for x in text.splitlines() if x.startswith('| '+label+' |'))
        (ROOT/f'prompt/cases/种子25/{key}.md').write_text(line.split('|')[2].strip()+'\n',encoding='utf-8')

if __name__=='__main__':
    import sys
    sys.path.insert(0,str(ROOT/'tools/files/公用代码'));build()
