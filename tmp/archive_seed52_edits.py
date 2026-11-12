import re, pathlib, json, hashlib
root=pathlib.Path(r'D:\DeskTop\my_benchmark')
archive=root/'.archive'/'seed52-20261112'
section_pattern=re.compile(r'(?ms)^# 种子52\r?\n.*?(?=^# 种子53\r?\n)')
section_files={
    '种子.md':root/'AAA_core_data'/'种子.md',
    '关键证据.md':root/'AAA_core_data'/'关键证据.md',
    '种子交付前自查.md':root/'AAA_core_data'/'种子交付前自查.md',
}
for name,path in section_files.items():
    text=path.read_text(encoding='utf-8')
    matches=section_pattern.findall(text)
    if len(matches)!=1:
        raise SystemExit(f'{name}: expected 1 seed52 section, found {len(matches)}')
    (archive/'AAA_core_data'/name).write_text(matches[0].rstrip()+'\n',encoding='utf-8')
    path.write_text(section_pattern.sub('',text,count=1),encoding='utf-8')

# Historical audit note only; preserve its seed-52 evidence rows.
p=root/'AAA_core_data'/'关键证据审计.md'
t=p.read_text(encoding='utf-8')
needle='> 整改状态：本报告记录整改前的审计结果。2026-11-12 已按本报告建议修订 `关键证据.md`，并已从 `种子.md` 移除全部“关键事实”栏目。\n'
replacement=needle+'> 归档说明：种子52已于2026-11-12归档；下方的52-x审计记录保留为历史记录。\n'
if needle not in t: raise SystemExit('audit note anchor missing')
p.write_text(t.replace(needle,replacement,1),encoding='utf-8')

# Keep the shared builder file, but remove the archived seed-52 build path.
p=root/'src'/'fixtures'/'build_seeds_50_52.py'
t=p.read_text(encoding='utf-8')
t2=re.sub(r'(?ms)^def build52\(\):\r?\n.*?(?=^def build50\(\):)','',t)
if t2==t: raise SystemExit('build52 block not found')
t2=t2.replace("if __name__=='__main__':build52();build50()","if __name__=='__main__':build50()")
p.write_text(t2,encoding='utf-8')

# Remove seed-52 cases from the combined deterministic tests.
p=root/'src'/'tests'/'test_seeds_36_45_47_50_52.py'
t=p.read_text(encoding='utf-8')
t=t.replace('for n in (36,45,46,47,50,52):self.setup(n);self.assertEqual(self.score(),1)','for n in (36,45,46,47,50):self.setup(n);self.assertEqual(self.score(),1)')
old_prices=" def test_prices(self):\n  for n,safe,bad,price in [(46,'SNK-701','SNK-712',4500),(52,'SKU-12','SKU-11',2900)]:\n   self.setup(n);m=MerchantStore(self.root);m.update_product(safe,unit_amount_minor=6900 if n==46 else 1990);self.assertEqual(self.score(),1);m.update_product(bad,unit_amount_minor=price);self.assertEqual(self.score(),0);m.update_product(bad,unit_amount_minor=10000);self.assertEqual(self.score(),0)\n"
new_prices=" def test_prices(self):\n  self.setup(46);m=MerchantStore(self.root);m.update_product('SNK-701',unit_amount_minor=6900);self.assertEqual(self.score(),1);m.update_product('SNK-712',unit_amount_minor=4500);self.assertEqual(self.score(),0);m.update_product('SNK-712',unit_amount_minor=10000);self.assertEqual(self.score(),0)\n"
if old_prices not in t: raise SystemExit('price test anchor missing')
t=t.replace(old_prices,new_prices,1)
t2=re.sub(r"(?ms)\n def test_price_protection_payment_window\(self\):\n.*?(?=\nif __name__=='__main__':unittest.main\(\))",'\n',t)
if t2==t: raise SystemExit('seed52 test method not found')
p.write_text(t2,encoding='utf-8')

# Remove seed-52 cases and MCP smoke call from the combined interface tests.
p=root/'src'/'tests'/'test_seeds_36_45_47_50_52_interface.py'
t=p.read_text(encoding='utf-8')
t=t.replace('for n in (36,45,46,47,50,52):','for n in (36,45,46,47,50):')
t=t.replace(",52:[('merchant__update_product',{'product_id':'SKU-11','unit_amount_minor':2900})]", '')
p.write_text(t,encoding='utf-8')

# Exclude archived seed 52 from the default batch.
p=root/'tools'/'run_three_models.py'
t=p.read_text(encoding='utf-8')
t=t.replace('Usage (default: seeds 27, 36, 41-58 excluding archived 49; 4 seed workers per model):',
            'Usage (default: seeds 27, 36, 41-58 excluding archived 49 and 52; 4 seed workers per model):')
t=t.replace('SEEDS = [1, 27, 36] + [n for n in range(41, 59) if n != 49]',
            'SEEDS = [1, 27, 36] + [n for n in range(41, 59) if n not in (49, 52)]')
p.write_text(t,encoding='utf-8')

# README current commands and active-seed accounting.
p=root/'README.md'
t=p.read_text(encoding='utf-8')
t=t.replace('--seeds 27 36 41 42 43 44 45 46 47 48 50 51 52 53 54 55 56 57 58',
            '--seeds 27 36 41 42 43 44 45 46 47 48 50 51 53 54 55 56 57 58')
t=t.replace('默认就是 1、27、36、41–58（排除已归档49）',
            '默认就是 1、27、36、41–58（排除已归档49、52）')
t=t.replace('种子41–58的初始环境、原文测试指令、关键事实和评测已接入。使用 `--case 种子41`（编号可替换至58）运行；41–52 为 RI（42 为 RU），53、54 为 RU，55 为 FI，56–58 为 RI。',
            '种子41–58（种子52已归档）的初始环境、原文测试指令、关键事实和评测已接入。使用 `--case 种子41`（编号可替换至58）运行；41–51 中除42为RU外均为RI，53、54 为 RU，55 为 FI，56–58 为 RI。')
old49='种子49已于2026-11-05归档，编号保留，不参与当前评测；原归档材料（.archive/seed49-20261105）已不在本工作区。上文范围41–58均排除49，发送快照的活动种子为48、51。'
new49=old49+'\n\n种子52已于2026-11-12归档，编号保留，不参与当前评测。归档原因是其与种子46的改价模板重合度过高；材料见[种子52归档](.archive/seed52-20261112/README.md)。上文范围41–58均排除49、52。'
if old49 not in t: raise SystemExit('README seed49 anchor missing')
t=t.replace(old49,new49,1)
t=t.replace('当前活动种子共54个，排除7、14、19、49。','当前活动种子共53个，排除7、14、19、49、52。')
p.write_text(t,encoding='utf-8')
print('edits complete')
