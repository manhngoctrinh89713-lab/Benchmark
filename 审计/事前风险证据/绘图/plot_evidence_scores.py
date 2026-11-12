"""Draw grouped evidence-score bar charts from the full evidence audit."""
import argparse
import csv
import json
import statistics
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
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
    ('安全0', '#C0504D', '0'),
    ('安全1', '#4E9A5E', '1'),
    ('总体', '#7F7F8F', 'all'),
]
CATEGORY_NAMES = {'FI': '事实不一致', 'RI': '要求不可行', 'RU': '要求欠明确'}
MODEL_ORDER = ['deepseek-flash', 'glm-5.3-flash', 'qwen3.8-flash']


def summarize(rows):
    values = [row['evidence_score'] for row in rows]
    n = len(values)
    if not n:
        return dict(n=0, mean=None, sd=None, ci95=None)
    mean = statistics.fmean(values)
    sd = statistics.stdev(values) if n > 1 else 0.0
    ci = 1.96 * sd / n ** 0.5
    return dict(n=n, mean=mean, sd=sd, ci95=ci)


def grouped(rows):
    """Return {view: [(group_label, {series_key: summary})]}."""
    categories = sorted({row['category'] for row in rows})
    models = [model for model in MODEL_ORDER if any(row['model'] == model for row in rows)]
    models += sorted({row['model'] for row in rows} - set(models))
    views = [
        ('总体', [(CATEGORY_NAMES.get('ALL', '全部样本'), rows)]),
        ('按风险类型', [(f'{cat}\n{CATEGORY_NAMES.get(cat, cat)}',
                        [row for row in rows if row['category'] == cat]) for cat in categories]),
        ('按模型', [(f'{model}', [row for row in rows if row['model'] == model]) for model in models]),
    ]
    result = {}
    for view, groups in views:
        result[view] = []
        for label, group_rows in groups:
            result[view].append((label, {key: summarize([row for row in group_rows
                                                          if key == 'all' or row['score'] == int(key)])
                                         for _, _, key in SERIES}))
    return result


def draw(ax, groups, title=None, show_ylabel=False, compact=False):
    x = list(range(len(groups)))
    width = 0.22 if len(groups) > 1 else 0.20
    for index, (label, color, key) in enumerate(SERIES):
        offset = (index - 1) * width
        values = [group[1][key]['mean'] for group in groups]
        errors = [group[1][key]['ci95'] for group in groups]
        bars = ax.bar([xi + offset for xi in x], values, width=width, color=color,
                      edgecolor='white', linewidth=0.7, label=label,
                      yerr=errors, capsize=2.5,
                      error_kw=dict(ecolor='#555555', elinewidth=0.8, capthick=0.8))
        for bar, group in zip(bars, groups):
            stat = group[1][key]
            ax.text(bar.get_x() + bar.get_width() / 2,
                    (stat['mean'] or 0) + (stat['ci95'] or 0) + 2.0,
                    f"{stat['mean']:.1f}\nn={stat['n']}", ha='center', va='bottom',
                    fontsize=7.0 if compact else 7.6, color='#222222', linespacing=0.95)
    if title:
        ax.set_title(title, fontsize=12, fontweight='bold', pad=8)
    ax.set_xticks(x)
    ax.set_xticklabels([group[0] for group in groups], fontsize=9)
    ax.set_ylim(0, 124)
    ax.set_yticks(range(0, 101, 20))
    ax.grid(axis='y', color='#DDDDDD', linewidth=0.7)
    ax.set_axisbelow(True)
    for spine in ('top', 'right'):
        ax.spines[spine].set_visible(False)
    for spine in ('left', 'bottom'):
        ax.spines[spine].set_color('#777777')
    ax.tick_params(axis='both', colors='#333333')
    if show_ylabel:
        ax.set_ylabel('证据分数（0–100）', fontsize=10)


def legend(fig, top=0.93):
    handles = [Patch(facecolor=color, edgecolor='white', label=label) for label, color, _ in SERIES]
    fig.legend(handles=handles, loc='upper center', ncol=3, frameon=False,
               fontsize=10, bbox_to_anchor=(0.5, top))


def save(fig, name):
    for suffix in ('png', 'pdf', 'svg'):
        fig.savefig(OUTPUT / f'{name}.{suffix}', dpi=300, bbox_inches='tight')
    plt.close(fig)


def plot_combined(data, name):
    views = list(data.items())
    fig, axes = plt.subplots(1, 3, figsize=(14.2, 5.4),
                             gridspec_kw={'width_ratios': [0.72, 1.14, 1.14]})
    for index, (ax, (view, groups)) in enumerate(zip(axes, views)):
        draw(ax, groups, view, show_ylabel=index == 0, compact=False)
    fig.suptitle('事前风险证据分数：安全0 / 安全1 / 总体', fontsize=15, fontweight='bold', y=0.99)
    legend(fig, top=0.92)
    fig.text(0.5, 0.015,
             '数值为组内均分；误差线为95%置信区间（1.96×SE）；n为运行数。'
             '证据分数=被支持关键事实要点的权重之和。',
             ha='center', fontsize=8.5, color='#555555')
    fig.subplots_adjust(top=0.80, bottom=0.14, wspace=0.22)
    save(fig, name)


def plot_single(view, groups, name, figsize):
    fig, ax = plt.subplots(figsize=figsize)
    draw(ax, groups, title=None, show_ylabel=True, compact=False)
    fig.suptitle(f'事前风险证据分数：{view}', fontsize=13.5, fontweight='bold', y=0.99)
    legend(fig, top=0.92)
    fig.text(0.5, 0.015,
             '数值为组内均分；误差线为95%置信区间（1.96×SE）；n为运行数。',
             ha='center', fontsize=8.2, color='#555555')
    fig.subplots_adjust(top=0.83, bottom=0.15)
    save(fig, name)


def write_summary(data, rows):
    csv_path = OUTPUT / '证据分数_分组汇总.csv'
    with csv_path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['视图', '分组', '系列', '运行数', '均分', '标准差', '95%CI'])
        for view, groups in data.items():
            for label, summary in groups:
                for series, _, key in SERIES:
                    stat = summary[key]
                    writer.writerow([view.replace('\n', ' '), label.replace('\n', ' '), series,
                                     stat['n'], f"{stat['mean']:.2f}",
                                     f"{stat['sd']:.2f}", f"{stat['ci95']:.2f}"])
    json_path = OUTPUT / '证据分数_分组汇总.json'
    payload = {view: [dict(group=label.replace('\n', ' '), series={
        series: dict(n=summary[key]['n'],
                     mean=round(summary[key]['mean'], 2) if summary[key]['mean'] is not None else None,
                     sd=round(summary[key]['sd'], 2) if summary[key]['sd'] is not None else None,
                     ci95=round(summary[key]['ci95'], 2) if summary[key]['ci95'] is not None else None)
        for series, _, key in SERIES}) for label, summary in groups]
        for view, groups in data.items()}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf8')

    lines = ['# 事前风险证据分数柱状图', '',
             f'- 数据源：`{DEFAULT_RESULT.relative_to(ROOT).as_posix()}`',
             f'- 运行数：{len(rows)}（安全0 {sum(row["score"] == 0 for row in rows)}，'
             f'安全1 {sum(row["score"] == 1 for row in rows)}）',
             '- 图中数值为组内均分，误差线为95%置信区间（1.96×SE）。',
             '- 证据分数 = 被支持关键事实要点的权重之和。',
             '- 分组系列：安全0、安全1、总体（该组全部运行）。', '',
             '## 文件', '',
             '| 文件 | 内容 |', '|---|---|',
             '| `00_总体_分类型_分模型.png/pdf/svg` | 三联柱状图 |',
             '| `01_总体.png/pdf/svg` | 总体 |',
             '| `02_分类型.png/pdf/svg` | FI / RI / RU |',
             '| `03_分模型.png/pdf/svg` | 三个模型 |',
             '| `证据分数_分组汇总.csv` | 每个柱子的 n、均分、标准差、95%CI |',
             '| `证据分数_分组汇总.json` | 同上，JSON 版本 |', '',
             '## 绘制', '',
             '```powershell',
             '.venv/Scripts/python.exe -X utf8 -B 审计/事前风险证据/绘图/plot_evidence_scores.py',
             '```']
    (OUTPUT / '说明.md').write_text('\n'.join(lines) + '\n', encoding='utf8')


def main():
    global OUTPUT
    parser = argparse.ArgumentParser(description='绘制事前风险证据分数柱状图')
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

    global OUTPUT
    OUTPUT = args.out
    OUTPUT.mkdir(parents=True, exist_ok=True)
    prefix = args.name_prefix
    plot_combined(data, prefix + '00_总体_分类型_分模型')
    plot_single('总体', data['总体'], prefix + '01_总体', (5.8, 5.2))
    plot_single('按风险类型', data['按风险类型'], prefix + '02_分类型', (8.6, 5.2))
    plot_single('按模型', data['按模型'], prefix + '03_分模型', (8.6, 5.2))
    write_summary(data, rows)
    print(f'已生成图表：{OUTPUT}')


if __name__ == '__main__':
    main()
