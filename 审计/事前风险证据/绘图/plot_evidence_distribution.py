"""Draw 10-point-binned distributions of evidence scores (no mean aggregation)."""
import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

HOME = Path(__file__).resolve().parent
ROOT = HOME.parents[2]
DEFAULT_RESULT = ROOT / '审计/事前风险证据/结果/20261110-full/完整数据汇总.json'
OUTPUT = HOME

plt.rcParams.update({
    'font.sans-serif': ['Microsoft YaHei', 'SimHei', 'Arial'],
    'axes.unicode_minus': False,
    'savefig.facecolor': 'white',
    'figure.facecolor': 'white',
})

SERIES = [
    ('安全0', '0'),
    ('安全1', '1'),
    ('总体', 'all'),
]
CATEGORY_NAMES = {'FI': '事实不一致', 'RI': '要求不可行', 'RU': '要求欠明确'}
MODEL_ORDER = ['deepseek-flash', 'glm-5.3-flash', 'qwen3.8-flash']
BIN_LABELS = ['0–10', '10–20', '20–30', '30–40', '40–50',
              '50–60', '60–70', '70–80', '80–90', '90–100']
COLORS = plt.cm.RdYlGn(np.linspace(0.05, 0.95, 10))


def bucket(score):
    return min(int(score) // 10, 9)


def distribution(rows):
    counts = [0] * 10
    for row in rows:
        counts[bucket(row['evidence_score'])] += 1
    return counts


def grouped(rows):
    """Return {view: [(group_label, {series_key: (counts, n)})]}."""
    categories = sorted({row['category'] for row in rows})
    models = [model for model in MODEL_ORDER if any(row['model'] == model for row in rows)]
    models += sorted({row['model'] for row in rows} - set(models))
    views = [
        ('总体', [('全部样本', rows)]),
        ('按风险类型', [(f'{cat} {CATEGORY_NAMES.get(cat, cat)}',
                        [row for row in rows if row['category'] == cat]) for cat in categories]),
        ('按模型', [(model, [row for row in rows if row['model'] == model]) for model in models]),
    ]
    result = {}
    for view, groups in views:
        result[view] = []
        for label, group_rows in groups:
            summary = {}
            for _, key in SERIES:
                selected = [row for row in group_rows if key == 'all' or row['score'] == int(key)]
                summary[key] = (distribution(selected), len(selected))
            result[view].append((label, summary))
    return result


def draw(ax, groups, title=None, show_ylabel=False):
    width = 0.24
    positions, labels, group_centers = [], [], []
    for group_index, (group_label, summary) in enumerate(groups):
        base = group_index * 3
        group_centers.append(base + 1)
        for series_index, (series_label, key) in enumerate(SERIES):
            x = base + series_index
            positions.append(x)
            labels.append(series_label)
            counts, n = summary[key]
            bottom = 0.0
            for bin_index, count in enumerate(counts):
                share = 100 * count / n if n else 0
                ax.bar(x, share, width=width, bottom=bottom, color=COLORS[bin_index],
                       edgecolor='white', linewidth=0.45,
                       label=BIN_LABELS[bin_index] if group_index == 0 and series_index == 0 else None)
                bottom += share
            ax.text(x, 101.5, f'n={n}', ha='center', va='bottom', fontsize=7.6, color='#333333')
        ax.text(base + 1, 112, group_label, ha='center', va='bottom',
                fontsize=9.0, fontweight='bold', color='#222222')
        if group_index:
            ax.axvline(base - 0.5, color='#C8C8C8', linewidth=0.7, linestyle=(0, (2, 3)))
    if title:
        ax.set_title(title, fontsize=12, fontweight='bold', pad=8)
    ax.set_xlim(-0.7, len(groups) * 3 - 0.3)
    ax.set_ylim(0, 120)
    ax.set_yticks(range(0, 101, 20))
    ax.set_xticks(positions)
    ax.set_xticklabels(labels, fontsize=7.6)
    ax.grid(axis='y', color='#DDDDDD', linewidth=0.7)
    ax.set_axisbelow(True)
    for spine in ('top', 'right'):
        ax.spines[spine].set_visible(False)
    for spine in ('left', 'bottom'):
        ax.spines[spine].set_color('#777777')
    ax.tick_params(axis='both', colors='#333333')
    if show_ylabel:
        ax.set_ylabel('占比（%）', fontsize=10)


def legend(fig, top):
    handles = [Patch(facecolor=COLORS[i], edgecolor='white', label=BIN_LABELS[i]) for i in range(10)]
    fig.legend(handles=handles, loc='upper center', ncol=10, frameon=False,
               fontsize=7.4, handlelength=1.1, columnspacing=1.0, bbox_to_anchor=(0.5, top))


def save(fig, name):
    for suffix in ('png', 'pdf', 'svg'):
        fig.savefig(OUTPUT / f'{name}.{suffix}', dpi=300, bbox_inches='tight')
    plt.close(fig)


def plot_combined(data, name):
    views = list(data.items())
    fig, axes = plt.subplots(1, 3, figsize=(14.6, 5.9),
                             gridspec_kw={'width_ratios': [0.8, 1.1, 1.1]})
    for index, (ax, (view, groups)) in enumerate(zip(axes, views)):
        draw(ax, groups, title=view, show_ylabel=index == 0)
    fig.suptitle('事前风险证据分数分布（每 10 分一段，100% 堆叠）', fontsize=15,
                 fontweight='bold', y=0.99)
    legend(fig, top=0.91)
    fig.text(0.5, 0.015,
             '柱内为该组运行的分数分布；n为运行数。区间左闭右开，100 计入 90–100。',
             ha='center', fontsize=8.5, color='#555555')
    fig.subplots_adjust(top=0.80, bottom=0.13, wspace=0.18)
    save(fig, name)


def plot_single(view, groups, name, figsize):
    fig, ax = plt.subplots(figsize=figsize)
    draw(ax, groups, title=None, show_ylabel=True)
    fig.suptitle(f'事前风险证据分数分布：{view}', fontsize=13.5, fontweight='bold', y=0.99)
    legend(fig, top=0.91)
    fig.text(0.5, 0.015,
             '柱内为该组运行的分数分布；n为运行数。区间左闭右开，100 计入 90–100。',
             ha='center', fontsize=8.2, color='#555555')
    fig.subplots_adjust(top=0.82, bottom=0.15)
    save(fig, name)


def write_tables(data, rows):
    csv_path = OUTPUT / '证据分数_10分段分布.csv'
    with csv_path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['视图', '分组', '系列', '运行数', '分数段', '运行数_段', '占该柱比例'])
        for view, groups in data.items():
            for label, summary in groups:
                for series, key in SERIES:
                    counts, n = summary[key]
                    for bin_label, count in zip(BIN_LABELS, counts):
                        writer.writerow([view, label, series, n, bin_label, count,
                                         f'{100 * count / n:.1f}' if n else '0.0'])
    json_path = OUTPUT / '证据分数_10分段分布.json'
    payload = {view: [dict(group=label, series={
        series: dict(n=summary[key][1],
                     distribution={bin_label: count for bin_label, count in zip(BIN_LABELS, summary[key][0])})
        for series, key in SERIES}) for label, summary in groups]
        for view, groups in data.items()}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf8')

    lines = ['# 事前风险证据分数分段分布图', '',
             f'- 数据源：`{DEFAULT_RESULT.relative_to(ROOT).as_posix()}`',
             f'- 运行数：{len(rows)}（安全0 {sum(row["score"] == 0 for row in rows)}，'
             f'安全1 {sum(row["score"] == 1 for row in rows)}）',
             '- 每 10 分一段；柱高为该组内各分数段的占比（100% 堆叠），柱顶标注 n。',
             '- 区间为左闭右开，100 计入 90–100。',
             '- 系列：安全0、安全1、总体（该组全部运行）。', '',
             '## 文件', '',
             '| 文件 | 内容 |', '|---|---|',
             '| `10_分段分布_总体_分类型_分模型.png/pdf/svg` | 三联分段分布图 |',
             '| `11_分段分布_总体.png/pdf/svg` | 总体 |',
             '| `12_分段分布_分类型.png/pdf/svg` | FI / RI / RU |',
             '| `13_分段分布_分模型.png/pdf/svg` | 三个模型 |',
             '| `证据分数_10分段分布.csv` | 每个柱子每个分数段的计数与占比 |',
             '| `证据分数_10分段分布.json` | 同上，JSON 版本 |', '',
             '## 绘制', '',
             '```powershell',
             '.venv/Scripts/python.exe -X utf8 -B 审计/事前风险证据/绘图/plot_evidence_distribution.py',
             '```']
    (OUTPUT / '说明_分段分布.md').write_text('\n'.join(lines) + '\n', encoding='utf8')


def main():
    global OUTPUT
    parser = argparse.ArgumentParser(description='绘制事前风险证据分数 10 分一段的分段分布图')
    parser.add_argument('--result', type=Path, default=DEFAULT_RESULT)
    parser.add_argument('--out', type=Path, default=HOME)
    parser.add_argument('--name-prefix', default='')
    args = parser.parse_args()
    data = json.loads(args.result.read_text(encoding='utf-8'))
    rows = [row for row in data['records'] if row.get('status') == 'scored'
            and isinstance(row.get('evidence_score'), int)]
    if not rows:
        raise SystemExit('没有可绘制的已评分记录')
    data = grouped(rows)

    OUTPUT = args.out
    OUTPUT.mkdir(parents=True, exist_ok=True)
    prefix = args.name_prefix
    plot_combined(data, prefix + '10_分段分布_总体_分类型_分模型')
    plot_single('总体', data['总体'], prefix + '11_分段分布_总体', (6.2, 5.8))
    plot_single('按风险类型', data['按风险类型'], prefix + '12_分段分布_分类型', (9.2, 5.8))
    plot_single('按模型', data['按模型'], prefix + '13_分段分布_分模型', (9.2, 5.8))
    write_tables(data, rows)
    print(f'已生成分段分布图：{OUTPUT}')


if __name__ == '__main__':
    main()
