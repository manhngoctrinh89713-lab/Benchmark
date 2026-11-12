"""Retry failed or unscored runs in a three-model batch and merge the results.

Usage:
    .venv/Scripts/python.exe -B tools/retry_three_models.py --batch 运行记录/<批次>
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tools'))
from harness import runner
from run_three_models import summarize


async def main():
    batch = Path(args.batch)
    if not batch.is_absolute():
        batch = (ROOT / batch).resolve()
    manifest = json.loads((batch / 'manifest.json').read_text(encoding='utf-8'))
    total = manifest['total']
    method = manifest.get('method')
    agentguard_enabled = bool(manifest.get('agentguard_enabled', False))
    retries = []
    for report_path in sorted((batch / 'reports').glob('*.json')):
        report = json.loads(report_path.read_text(encoding='utf-8'))
        changed = False
        for index, row in enumerate(report.get('runs', [])):
            if row.get('status') == 'completed' and row.get('score') is not None and not args.force:
                continue
            if args.models and row['model'] not in args.models:
                continue
            seed = int(str(row['case']).removeprefix('种子'))
            if args.seeds and seed not in args.seeds:
                continue
            stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            run_id = f"{batch.name}-retry-{stamp}-{row['model']}-seed{seed}-{row['variant']}"
            run_args = argparse.Namespace(model=row['model'], endpoint=None, case=row['case'], groups=None,
                user=None, variant=row['variant'], all_variants=False, no_proxy=True,
                api_retries=3, max_steps=manifest.get('max_steps', 150), max_tool_calls=args.max_tool_calls, dry_run=False,
                reset_only=False, batch_id=batch.name, run_id=run_id,
                specified_quit=method == 'specified_quit', agentguard=agentguard_enabled)
            error = None
            try:
                await runner.execute_locked(run_args)
            except Exception as exc:
                error = runner.describe_error(exc)
            run_path = ROOT / '运行记录' / run_id / 'run.json'
            meta = json.loads(run_path.read_text(encoding='utf-8')) if run_path.exists() else {}
            quit_meta = meta.get('specified_quit') or {}
            new_row = dict(model=row['model'], case=row['case'], variant=row['variant'], run_id=run_id,
                method=meta.get('method'), quit_triggered=bool(quit_meta.get('triggered')),
                quit_source=quit_meta.get('source'), quit_question=quit_meta.get('question'),
                quit_tool_calls_before=quit_meta.get('tool_calls_before'),
                status=meta.get('status', 'failed'), score=meta.get('safety_score'),
                termination_reason=meta.get('termination_reason'),
                model_calls=meta.get('model_calls', 0), tool_calls=meta.get('tool_calls', 0),
                previous_run_id=row.get('run_id'), retry_attempts=row.get('retry_attempts', 0) + 1)
            if error:
                new_row['error'] = error
            report['runs'][index] = new_row
            changed = True
            retries.append(dict(original=row, retry=new_row, error=error))
            print('RETRY ' + json.dumps(new_row, ensure_ascii=False), flush=True)
        if changed:
            runner.write_json(report_path, report)
    runner.write_json(batch / 'retries.json', dict(
        at=datetime.now().astimezone().isoformat(), max_tool_calls=args.max_tool_calls,
        retries=retries))
    summarize(batch, 'finished', total)
    print('UPDATED ' + str(batch / 'comparison.md'), flush=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', required=True)
    parser.add_argument('--max-tool-calls', type=int, default=50,
                        help='Maximum tool calls per agent (default 50)')
    parser.add_argument('--models', nargs='+')
    parser.add_argument('--seeds', type=int, nargs='+')
    parser.add_argument('--force', action='store_true',
                        help='重跑已有分数的行（用于 Guard/reviewer 故障导致保护缺失的批次）')
    args = parser.parse_args()
    asyncio.run(main())
