"""画安全增强退出点与基线危险点的证据分数对照图。"""
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
DEFAULT_RESULT = ROOT / '审计/安全增强退出点/结果/20261110-enhanced-exit/汇总.json'
BASELINE = ROOT / '审计/事前风险证据/结果/20261110-full/完整数据汇总.json'
OUTPUT = HOME

plt.rcParams.update({
    'font.sans-serif': ['Microsoft YaHei', 'SimHei', 'Arial'],
    'axes.unicode_minus': False,
    'savefig.facecolor': 'white',
    'figure.facecolor': 'white',
})


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def summary(values):
    values = [v for v in values if v is not None]
    n = len(values)
    if not n:
        return dict(n=0, mean=None, sd=None, ci95=None)
    mean = statistics.fmean(values)
    sd = statistics.stdev(values) if n > 1 else 0.0
    return dict(n=n, mean=mean, sd=sd, ci95=1.96 * sd / n ** 0.5)


def values(rows, predicate):
    return [row['evidence_score'] for row in rows
            if row.get('status') == 'scored' and predicate(row)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--result', type=Path, default=DEFAULT_RESULT)
    parser.add_argument('--baseline', type=Path, default=BASELINE)
    args = parser.parse_args()
    data = load(args.result)
    baseline = load(args.baseline)
    enhanced = data['records']
    base = baseline['records']

    groups = [
        ('基线\n危险点前', values(base, lambda r: r['score'] == 0), '#C0504D'),
        ('AgentGuard\n退出点', values(enhanced, lambda r: r['mechanism'] == 'agentguard'), '#4F81BD'),
        ('Quit\n退出点', values(enhanced, lambda r: r['mechanism'] == 'specified_quit'), '#4E9A5E'),
        ('基线\n完整轨迹', values(base, lambda r: r['score'] == 1), '#7F7F8F'),
    ]
    stats = [dict(label=label.replace('\n', ' '), color=color, **summary(vals))
             for label, vals, color in groups]

    fig, ax = plt.subplots(figsize=(7.4, 4.5))
    x = list(range(len(stats)))
    bars = ax.bar(x, [s['mean'] or 0 for s in stats], width=0.58,
                  color=[s['color'] for s in stats], edgecolor='white', linewidth=0.9,
                  yerr=[s['ci95'] or 0 for s in stats], capsize=3,
                  error_kw=dict(ecolor='#555555', elinewidth=0.9, capthick=0.9))
    for bar, stat in zip(bars, stats):
        ax.text(bar.get_x() + bar.get_width() / 2,
                (stat['mean'] or 0) + (stat['ci95'] or 0) + 2.2,
                f"{stat['mean']:.1f}\nn={stat['n']}", ha='center', va='bottom',
                fontsize=9, color='#222222', linespacing=1.0)
    ax.set_xticks(x)
    ax.set_xticklabels([s['label'] for s in stats], fontsize=9.5)
    ax.set_ylim(0, 112)
    ax.set_yticks(range(0, 101, 20))
    ax.set_ylabel('事前风险证据分数（0–100）', fontsize=10)
    ax.grid(axis='y', color='#DDDDDD', linewidth=0.7)
    ax.set_axisbelow(True)
    for spine in ('top', 'right'):
        ax.spines[spine].set_visible(False)
    for spine in ('left', 'bottom'):
        ax.spines[spine].set_color('#777777')
    ax.tick_params(axis='both', colors='#333333')
    ax.set_title('安全增强机制退出点 vs 基线危险点：关键事实支持分数', fontsize=12,
                 fontweight='bold', pad=10)
    fig.legend(handles=[Patch(facecolor=s['color'], edgecolor='white', label=s['label'])
                        for s in stats],
               loc='lower center', ncol=4, frameon=False, fontsize=8.5,
               bbox_to_anchor=(0.5, -0.02))
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    for suffix in ('png', 'pdf', 'svg'):
        fig.savefig(OUTPUT / f'01_机制退出_对照.{suffix}', dpi=300, bbox_inches='tight')
    plt.close(fig)

    with (OUTPUT / '机制退出_分组汇总.csv').open('w', encoding='utf-8-sig', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(['分组', 'n', '均分', '标准差', '95%CI'])
        for stat in stats:
            writer.writerow([stat['label'], stat['n'],
                             '' if stat['mean'] is None else f"{stat['mean']:.2f}",
                             '' if stat['sd'] is None else f"{stat['sd']:.2f}",
                             '' if stat['ci95'] is None else f"{stat['ci95']:.2f}"])
    (OUTPUT / '机制退出_分组汇总.json').write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
