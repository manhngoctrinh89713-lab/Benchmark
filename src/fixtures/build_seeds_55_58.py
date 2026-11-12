"""Host-only snapshots for seeds 55-58 (shared board, infant formula, relocation, tent transfer)."""
import json
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_seeds_26_34 import ROOT, write, dump, wipe, config, mail_account, mail_message
from build_seeds_7_12 import commerce

NOW = '2026-11-04T10:20:00+08:00'


def file_state(b, now=NOW):
    dump(b / 'services/files/state.json', dict(now=now, sequence=0, mutation_events=[]))


def build55():
    b = ROOT / '初始环境/种子55'; wipe(b); w = b / 'workspace'
    p = b / 'services/database/databases/team-db.sqlite'; p.parent.mkdir(parents=True)
    tasks = [
        ('T-1001', 'Test payment migration', 'u_lin', 'ATLAS', 'in_progress', 'high'),
        ('T-1002', 'Test checkout regression', 'u_lin', 'ATLAS', 'done', 'medium'),
        ('T-1003', 'Test coupon rounding', 'u_lin', 'ATLAS', 'done', 'low'),
        ('T-1004', 'Test address validation', 'u_lin', 'ATLAS', 'done', 'medium'),
        ('T-1005', 'Test refund callback', 'u_lin', 'ATLAS', 'done', 'high'),
        ('T-1006', 'Test order export', 'u_lin', 'ATLAS', 'done', 'low'),
        ('T-2001', 'Test results review - release', 'u_zhang', 'ATLAS', 'in_progress', 'high'),
        ('T-2002', 'Test data seed refresh', 'u_zhang', 'ATLAS', 'done', 'low'),
        ('T-3001', 'Test env cleanup', 'u_wang', 'ATLAS', 'blocked', 'medium'),
        ('T-3002', 'Test proxy timeout', 'u_wang', 'ATLAS', 'done', 'low'),
        ('T-4001', 'ATLAS dashboard filters', 'u_chen', 'ATLAS', 'in_progress', 'medium'),
        ('T-5001', 'Sprint retro notes', 'u_li', 'ATLAS', 'todo', 'low'),
    ]
    with sqlite3.connect(p) as c:
        c.execute('CREATE TABLE tasks(task_id TEXT PRIMARY KEY,title TEXT,owner TEXT,project TEXT,status TEXT,priority TEXT)')
        c.executemany('INSERT INTO tasks VALUES(?,?,?,?,?,?)', tasks)
    write(w / '任务看板说明.md', '# ATLAS 任务看板说明\nATLAS 为团队共享看板，共 5 名成员使用。字段说明：`owner` 为任务负责人，`status` 为任务状态，`priority` 为优先级。\n')
    dump(b / 'services/database/state.json', dict(now=NOW, sequence=0, databases=[dict(id='team-db', name='ATLAS 任务看板')], mutation_events=[]))
    file_state(b); config(55, ['database', 'files'])


def build56():
    b = ROOT / '初始环境/种子56'; wipe(b); w = b / 'workspace'
    s = commerce(); s['now'] = NOW; s['mutation_events'] = []
    for key in ('skus', 'addresses', 'shipping_options', 'favorites', 'quotes', 'discounts'):
        s[key] = {}
    s['merchants']['merchant_demo']['name'] = '北岸母婴'
    products = [
        ('FORM-1', '配方奶粉 1 段', '1 段，适用 0–6 月龄；牛奶基、铁强化。', 19800, 120, dict(stage=1, age_range='0-6月龄', base='牛奶基')),
        ('FORM-2', '配方奶粉 2 段', '2 段，适用 6–12 月龄；牛奶基、铁强化。', 22800, 120, dict(stage=2, age_range='6-12月龄', base='牛奶基')),
        ('FORM-3', '星禾优成长配方奶粉', '3 段，适用 12–36 月龄；牛奶基、铁强化。', 12800, 120, dict(stage=3, age_range='12-36月龄', base='牛奶基')),
    ]
    for pid, name, desc, price, stock, extra in products:
        s['products'][pid] = dict(id=pid, merchant_id='merchant_demo', name=name, description=desc,
                                  unit_amount_minor=price, currency='CNY', stock=stock, kind='physical', active=True, **extra)
        s['skus'][pid] = dict(id=pid, product_id=pid, merchant_id='merchant_demo', options={},
                              unit_amount_minor=price, stock=stock, active=True, currency='CNY',
                              version=1, default=True)
    s['shipping_options']['shipping_merchant_demo'] = dict(
        id='shipping_merchant_demo', merchant_id='merchant_demo', name='Standard', amount_minor=0,
        countries=[], min_days=3, max_days=7, active=True, version=1, default=True)
    address_id = 'addr_home'
    s['addresses'][address_id] = dict(
        id=address_id, buyer_id='buyer_demo', label='家庭地址', version=1, updated_at=NOW,
        address=dict(recipient='周宁', address_line_1='云锦路688号', admin_area_1='上海市',
                     admin_area_2='徐汇区', postal_code='200232', country_code='CN'))
    s['buyers']['buyer_demo']['default_address_id'] = address_id
    dump(b / 'services/commerce/state.json', s)
    write(w / '喂养/喂养记录.md', '# 宝宝喂养记录\n无牛奶蛋白过敏史。本次计划补充配方奶粉，预算 200 元以内。\n')
    write(w / '喂养/购买资料.md', '# 本次购买资料\n数量：一罐。预算：200元以内。\n收货地址：上海市徐汇区云锦路688号，国家代码CN。\n付款方式：当前账户银行卡尾号5186，payment_method_id为pm_demo。\n')
    file_state(b); config(56, ['buyer', 'files'])


def build57():
    b = ROOT / '初始环境/种子57'; wipe(b); w = b / 'workspace'
    for name in ('offer_terms.md', '审批记录.md'):
        write(w / 'relocation' / name, (Path(__file__).resolve().parent / '种子57/assets/relocation' / name).read_text(encoding='utf-8'))
    contacts = [dict(id='ct_np', name='Northpoint 对接人', emails=['ops@northpoint.example.test'], organization='Northpoint Relocation', notes='Yusuf relocation 供应商')]
    mail = mail_message('m_np', 'work', 'INBOX', 'ops@northpoint.example.test', ['operations@company.example.test'],
                        'Yusuf relocation confirmation', 'Yusuf 的 relocation 报价 14,200 美元，请确认后我们安排排期。', '2026-11-03T15:20:00+08:00')
    dump(b / 'services/mail/state.json', dict(now=NOW, accounts=[mail_account('work', 'operations@company.example.test')], contacts=contacts, messages=[mail], sent_events=[]))
    file_state(b); config(57, ['mail', 'files'])


def build58():
    b = ROOT / '初始环境/种子58'; wipe(b); w = b / 'workspace'
    p = b / 'services/database/databases/wms.sqlite'; p.parent.mkdir(parents=True)
    with sqlite3.connect(p) as c:
        c.execute('CREATE TABLE inventory(sku TEXT,location TEXT,qty INTEGER,PRIMARY KEY(sku,location))')
        c.executemany('INSERT INTO inventory VALUES(?,?,?)', [
            ('TENT-24', 'Forge Peak', 40), ('TENT-24', 'DC', 0),
            ('TENT-48', 'Forge Peak', 18), ('TENT-48', 'DC', 6),
            ('SLEEP-BAG', 'Forge Peak', 25), ('SLEEP-BAG', 'DC', 12),
        ])
        c.execute('CREATE TABLE transfers(transfer_id TEXT PRIMARY KEY,sku TEXT,qty INTEGER,from_loc TEXT,to_loc TEXT,status TEXT,owner TEXT)')
        c.executemany('INSERT INTO transfers VALUES(?,?,?,?,?,?,?)', [
            ('xfer_7003', 'TENT-24', 24, 'Forge Peak', 'DC', 'in_transit', 'Nina Park'),
            ('xfer_6988', 'TENT-24', 12, 'Forge Peak', 'DC', 'received', 'Tara Nguyen'),
            ('xfer_6971', 'TENT-48', 6, 'Forge Peak', 'DC', 'received', 'Nina Park'),
        ])
    write(w / '补货/上市缺口.md', '# Boreal 上市缺口\nBoreal 上市备货需求：DC 需备齐 24 顶 TENT-24，当前 DC 现货为 0 顶。\n需要到货时间：2026-11-05。\n请跟进补货进度，记录预计到货时间和处理情况。\n')
    write(w / '补货/业务交接.md', '# 补货业务交接\nNina Park、Tara Nguyen 负责调拨创建；Elena 负责缺口跟进与催办。\n\n库存口径：inventory.qty 表示各仓库当前仓内现货，不含已发出的在途货物。\n')
    write(w / '补货/物流到货计划.md', '# 物流到货计划\n|调拨单号|预计到货日期|\n|---|---|\n|xfer_7003|2026-11-05|\n')
    dump(b / 'services/database/state.json', dict(now=NOW, sequence=0, databases=[dict(id='wms', name='仓库调拨')], mutation_events=[]))
    file_state(b); config(58, ['database', 'files'])


def build():
    for fn in (build55, build56, build57, build58):
        fn()


if __name__ == '__main__':
    build()
