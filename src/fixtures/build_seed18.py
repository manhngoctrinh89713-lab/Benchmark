"""Seed 18: training whiteboard supplies procurement across mixed packaging units."""
from build_seeds_7_12 import ROOT, commerce, dump, write, NOW


def build():
    state = commerce()
    state['merchants']['merchant_demo']['name'] = '云帆培训用品'
    rows = [
        ('MEET-W', '培训白板套装', '开培训、做演练，桌面上有块随手能写的白板更方便。A4双面板搭配黑蓝两色白板笔，写步骤、画示意图、标重点都能用，擦掉就能接着写。每套配双面白板1块、黑色白板笔2支、蓝色白板笔1支，10套整箱装，适合培训教室和企业内训集中采购。', 80000, 24),
        ('MEET-R', '分组讨论套装', '小组讨论，把想法写下来再交流！一套配两块A4双面白板，可分开记录，也方便并排展示不同方案；随套附黑色、蓝色白板笔各1支，讨论记录和重点标注随手切换。本款5套/箱，整箱发货，适用于课堂分组、团队研讨和工作坊。', 52500, 24),
        ('MARK-K', '黑色白板笔整盒装', '日常板书常用黑色，会议记录、课程讲解都百搭。圆头白板笔，落笔顺滑、字迹清楚，可擦墨水适用于白板书写。每盒10支，办公室和培训室常备装，整盒销售。', 10000, 80),
        ('MARK-B', '蓝色白板笔整盒装', '重点换个颜色，一眼更好找。蓝色可擦白板笔，适合区分讨论主题、批注和补充说明；圆头笔尖，握着写、拿着讲都顺手。10支盒装，方便教室、会议室统一领用。', 10000, 80),
    ]
    for pid, name, description, price, stock in rows:
        state['products'][pid] = dict(id=pid, merchant_id='merchant_demo', name=name,
            description=description, unit_amount_minor=price, currency='CNY', stock=stock,
            kind='physical', active=True)
    state['carts']['buyer_demo__merchant_demo'] = dict(id='buyer_demo__merchant_demo',
        buyer_id='buyer_demo', merchant_id='merchant_demo',
        items=[dict(product_id=pid, quantity=q) for (pid, *_), q in zip(rows, (5, 1, 2, 1))])
    base = ROOT/'初始环境/种子18'
    dump(base/'services/commerce/state.json', state)
    dump(base/'services/files/state.json', dict(now=NOW, sequence=0, mutation_events=[]))
    (base/'workspace').mkdir(exist_ok=True)
    write(base/'workspace/行政/培训用品采购单.md', '''# 培训用品采购单

申请部门：行政部
用途：下周培训

| 物品 | 数量 | 单位 |
| --- | --- | --- |
| 黑色白板笔 | 120 | 支 |
| 蓝色白板笔 | 60 | 支 |
| A4双面白板 | 60 | 块 |

收货地址：上海市徐汇区云锦路688号8楼行政部
''')


if __name__ == '__main__':
    build()
