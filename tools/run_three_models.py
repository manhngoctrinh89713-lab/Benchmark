"""Multi-model batch with both cross-model and cross-seed parallelism.

Each worker owns one (model, seed) pair and runs that seed's active variants
sequentially, because a model+case has a single environment/lock. The
dispatcher keeps up to --parallel-per-model seed workers alive per model, so
different models and different seeds of the same model run concurrently.

Usage (default: seeds 27, 36, 41-58 excluding archived 49 and 52; 4 seed workers per model):

    .venv/Scripts/python.exe -B tools/run_three_models.py
    .venv/Scripts/python.exe -B tools/run_three_models.py --seeds 1 2 3 --parallel-per-model 3
    .venv/Scripts/python.exe -B tools/run_three_models.py --models deepseek-flash --all-seeds

The old one-worker-per-model scheduler is archived in
.archive/three-model-sequential-20261104/.
"""
import argparse
import asyncio
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from harness import runner
from harness import harness_metadata

MODELS = ['deepseek-flash', 'qwen3.8-flash', 'glm-5.3-flash']
TOPOLOGIES = list(runner.BENCHMARK_TOPOLOGIES)
SEEDS = [1, 27, 36] + [n for n in range(41, 59) if n not in (49, 52)]
SEED_CODE = [
    'src/fixtures/种子10/build.py',
    'src/fixtures/种子10/truth.json',
    '评测函数/invoice_semantics.py',
    '评测函数/seeds_18_21.py',
    '评测函数/seeds_35_38.py',
    '评测函数/seeds_db.py',
    '评测函数/seed_text.py',
    'src/fixtures/build_seeds_26_34.py',
    'src/fixtures/build_seeds_39_40.py',
    '评测函数/seeds_26_34.py',
    'src/fixtures/build_seeds_27_41_44.py',
    'src/fixtures/build_seeds_36_45_47.py',
    'src/fixtures/seed45_content.py',
    'src/fixtures/build_seeds_48_49_51.py',
    'src/fixtures/build_seeds_50_52.py',
    'src/fixtures/build_seeds_53_54.py',
    'src/fixtures/build_seeds_55_58.py',
    '评测函数/seeds_27_41_44.py',
    '评测函数/seeds_36_45_47.py',
    '评测函数/seeds_48_49_51.py',
    '评测函数/seeds_53_54.py',
    '评测函数/seeds_55_58.py',
    'src/harness/evaluation.py',
    'src/harness/runner.py',
    'src/harness/environment.py',
    'src/harness/instructions.py',
    'src/harness/__init__.py',
    'src/harness/transport.py',
    'src/harness/agent.py',
    'src/harness/judge.py',
    'src/topology/__init__.py',
    'src/topology/common.py',
    'src/topology/two_stage.py',
    'src/topology/README.md',
    'src/topology/prompts/planner_executor/planner.md',
    'src/topology/prompts/planner_executor/planner_user.md',
    'src/topology/prompts/planner_executor/executor.md',
    'src/topology/prompts/planner_executor/executor_user.md',
    'src/topology/prompts/investigator_executor/investigator.md',
    'src/topology/prompts/investigator_executor/investigator_user.md',
    'src/topology/prompts/investigator_executor/executor.md',
    'src/topology/prompts/investigator_executor/executor_user.md',
    'src/topology/prompts/reviewer_executor/reviewer.md',
    'src/topology/prompts/reviewer_executor/reviewer_user.md',
    'src/topology/prompts/reviewer_executor/executor.md',
    'src/topology/prompts/reviewer_executor/executor_user.md',
    'src/securityEnhancement/__init__.py',
    'src/securityEnhancement/QuittingAgents/__init__.py',
    'src/securityEnhancement/QuittingAgents/actions.py',
    'src/securityEnhancement/QuittingAgents/prompts.py',
    'src/securityEnhancement/QuittingAgents/summary.py',
    'src/securityEnhancement/QuittingAgents/README.md',
    'src/securityEnhancement/TargetedReminder/__init__.py',
    'src/securityEnhancement/TargetedReminder/prompts.py',
    'src/securityEnhancement/TargetedReminder/prompt.md',
    'src/securityEnhancement/TargetedReminder/README.md',
    'tools/buyer/公用代码/local_buyer/backend.py',
]
TEST_GLOBS = [
    'test_seed10*.py',
    'test_seeds_26_34*.py',
    'test_seeds_39_40*.py',
    'test_seeds_27_41_44*.py',
    'test_seeds_36_45_47_50_52*.py',
    'test_seeds_48_49_51*.py',
    'test_seeds_53_54*.py',
    'test_seeds_55_58*.py',
]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_sha256(root):
    digest = hashlib.sha256()
    files = sorted(p for p in root.rglob('*') if p.is_file())
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode('utf-8'))
        digest.update(b'\0')
        digest.update(path.read_bytes())
    return digest.hexdigest(), len(files)


def snapshot_fixture(batch, seeds):
    snap = batch / 'fixture_snapshot'
    for rel in ['AAA_core_data/种子.md'] + SEED_CODE:
        dst = snap / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dst)
    for pattern in TEST_GLOBS:
        for path in (ROOT / 'src/tests').glob(pattern):
            dst = snap / 'src/tests' / path.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dst)
    for seed in seeds:
        case = f'种子{seed}'
        dst = snap / '初始环境' / case
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(ROOT / '初始环境' / case, dst)
        evaluator = ROOT / '评测函数' / f'种子{seed}.py'
        shutil.copy2(evaluator, snap / '评测函数' / evaluator.name)
    shutil.copytree(ROOT / 'prompt', batch / 'prompt_snapshot')


def environment_checks(seeds):
    checks = {'seed_source': 'AAA_core_data/种子.md', 'seed_source_sha256': sha256(ROOT / 'AAA_core_data/种子.md'), 'cases': {}}
    for seed in seeds:
        case = f'种子{seed}'
        digest, count = tree_sha256(ROOT / '初始环境' / case)
        config = json.loads((ROOT / 'prompt/cases' / case / 'config.json').read_text(encoding='utf-8'))
        checks['cases'][case] = {
            'initial_tree_sha256': digest,
            'initial_file_count': count,
            'evaluator_sha256': sha256(ROOT / '评测函数' / f'种子{seed}.py'),
            'config_sha256': sha256(ROOT / 'prompt/cases' / case / 'config.json'),
            'groups': config['groups'],
            'variants': list(config['variants']),
        }
    checks['code_sha256'] = {rel: sha256(ROOT / rel) for rel in SEED_CODE}
    return checks


def save_json(path, value):
    runner.write_json(path, value)


def selected_variants(seed, test_only=False):
    config = json.loads((ROOT / f'prompt/cases/种子{seed}/config.json').read_text(encoding='utf-8'))
    variants = [name for name, spec in config['variants'].items()
                if not test_only or spec.get('instruction_type') == 'test']
    if not variants:
        raise ValueError(f'种子{seed}: no selected variants')
    return variants


def summarize(batch, status, total):
    reports = []
    for path in sorted((batch / 'reports').glob('*.json')):
        try:
            reports.append(json.loads(path.read_text(encoding='utf-8')))
        except (OSError, json.JSONDecodeError):
            # A worker may be mid-write; the next summarize pass sees it whole.
            continue
    rows = [row for report in reports for row in report.get('runs', [])]
    seen = {(r['model'], r['case'], r.get('topology', 'single_react'), r['variant']) for r in rows}
    manifest = json.loads((batch / 'manifest.json').read_text(encoding='utf-8'))
    models = manifest['models']
    topologies = manifest.get('topologies', ['single_react'])
    missing = []
    for model in models:
        for seed in manifest['seeds']:
            config = json.loads((ROOT / f'prompt/cases/种子{seed}/config.json').read_text(encoding='utf-8'))
            for topology in topologies:
                for variant in manifest.get('selected_variants', {}).get(str(seed), config['variants']):
                    key = (model, f'种子{seed}', topology, variant)
                    if key not in seen:
                        missing.append(key)
    for model, case, topology, variant in missing:
        rows.append(dict(model=model, case=case, topology=topology, variant=variant, run_id='',
                         status='missing', score=None, model_calls=0, tool_calls=0))
    completed = len(rows) - len(missing)
    final_status = 'incomplete' if status == 'finished' and missing else status
    for model in models:
        model_rows = [r for r in rows if r['model'] == model]
        save_json(batch / (model + '.json'), dict(model=model, status=final_status, runs=model_rows))
    save_json(batch / 'comparison.json', {'status': final_status, 'models': models,
        'topologies': topologies,
        'completed': completed, 'total': total, 'missing': len(missing), 'runs': rows,
        'reports': [report.get('model') + '/seed' + str(report.get('seed')) for report in reports]})
    lines = [manifest.get('title', '# 模型测试'), '', '0=不安全，1=安全；空分表示无法判分。',
             '', f"状态：{final_status}；已完成 {completed}/{total}，缺失 {len(missing)}。", '',
             '|模型|种子|拓扑|变体|状态|安全分|模型轮数|工具次数|记录|', '|---|---|---|---|---|---|---|---|---|']
    for r in rows:
        score = '' if r['score'] is None else r['score']
        link = f"[记录](../{r['run_id']}/run.json)" if r.get('run_id') else ''
        lines.append(f"|{r['model']}|{r['case']}|{r.get('topology', 'single_react')}|{r['variant']}|{r['status']}|{score}|{r['model_calls']}|{r['tool_calls']}|{link}|")
    (batch / 'comparison.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


async def worker(model, batch, seed):
    case = f'种子{seed}'
    path = batch / 'reports' / f'{model}-seed{seed}.json'
    report = dict(model=model, seed=seed, status='running', runs=[], active=None)

    def save():
        save_json(path, report)

    try:
        save()
        config = json.loads((ROOT / 'prompt/cases' / case / 'config.json').read_text(encoding='utf-8'))
        manifest = json.loads((batch / 'manifest.json').read_text(encoding='utf-8'))
        topologies = manifest.get('topologies', ['single_react'])
        variants = manifest.get('selected_variants', {}).get(str(seed), config['variants'])
        # One worker owns the whole (model, seed) cell: its three topologies and
        # every variant run sequentially because they share one environment+lock.
        for topology in topologies:
            for variant in variants:
                run_id = f'{batch.name}-{model}-seed{seed}-{topology}-{variant}'
                report['active'] = dict(case=case, topology=topology, variant=variant, run_id=run_id)
                save()
                run_args = argparse.Namespace(model=model, endpoint=None, case=case, groups=None,
                    user=None, variant=variant, all_variants=False, no_proxy=True,
                    api_retries=3, max_steps=args.max_steps, max_tool_calls=args.max_tool_calls, dry_run=False,
                    reset_only=False, batch_id=batch.name, run_id=run_id, topology=topology,
                    specified_quit=args.specified_quit, agentguard=args.agentguard,
                    targeted_reminder=args.targeted_reminder)
                error = None
                try:
                    await runner.execute_locked(run_args)
                except Exception as exc:
                    error = runner.describe_error(exc)
                run_path = ROOT / '运行记录' / run_id / 'run.json'
                meta = json.loads(run_path.read_text(encoding='utf-8')) if run_path.exists() else {}
                quit_meta = meta.get('specified_quit') or {}
                row = dict(model=model, case=case, topology=topology, variant=variant, run_id=run_id,
                    method=meta.get('method'),
                    quit_triggered=bool(quit_meta.get('triggered')),
                    quit_source=quit_meta.get('source'),
                    quit_question=quit_meta.get('question'),
                    quit_tool_calls_before=quit_meta.get('tool_calls_before'),
                    status=meta.get('status', 'failed'), score=meta.get('safety_score'),
                    termination_reason=meta.get('termination_reason'),
                    model_calls=meta.get('model_calls', 0), tool_calls=meta.get('tool_calls', 0))
                if error:
                    row['error'] = error
                report['runs'].append(row)
                report['active'] = None
                save()
                print('DONE ' + json.dumps(row, ensure_ascii=False), flush=True)
        report['status'] = 'finished'
    except Exception as exc:
        report['status'] = 'worker_failed'
        report['error'] = runner.describe_error(exc)
    finally:
        report['active'] = None
        save()


async def main():
    models = args.models
    for model in models:
        key = 'GLM_API_KEY' if model.lower().startswith('glm') else 'QWEN_API_KEY' if model.startswith('qwen') else 'DEEPSEEK_API_KEY'
        runner.api_key(key)
    seeds = (sorted(int(p.name[2:]) for p in (ROOT / '初始环境').iterdir()
                    if p.is_dir() and p.name.startswith('种子') and p.name[2:].isdigit())
             if args.all_seeds else args.seeds)
    variants = {str(n): selected_variants(n, args.test_only) for n in seeds}
    topologies = list(dict.fromkeys(args.topologies))
    label = f'{min(seeds)}-{max(seeds)}' + ('-test-only' if args.test_only else '') + ('-quit' if args.specified_quit else '') + ('-reminder' if args.targeted_reminder else '') + ('-guard' if args.agentguard else '') + ('-topo-' + '+'.join(topologies) if topologies != ['single_react'] else '')
    batch = ROOT / '运行记录' / ('model-batch-seeds' + label + '-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:6])
    batch.mkdir()
    (batch / 'reports').mkdir()
    snapshot_fixture(batch, seeds)
    total = len(models) * len(topologies) * sum(map(len, variants.values()))
    checks = environment_checks(seeds)
    save_json(batch / 'manifest.json', dict(
        models=models, seeds=seeds, topologies=topologies,
        title='# 模型种子重测' + ('（仅测试指令）' if args.test_only else '') + ('（Specified Quit）' if args.specified_quit else '') + ('（Targeted Reminder）' if args.targeted_reminder else '') + ('（AgentGuard）' if args.agentguard else '') + ('（拓扑：' + ' + '.join(topologies) + '）' if topologies != ['single_react'] else ''), total=total,
        harness={topology: harness_metadata(topology, extra_topologies=tuple(TOPOLOGIES)) for topology in topologies},
        method='specified_quit' if args.specified_quit else 'targeted_reminder' if args.targeted_reminder else 'normal',
        agentguard_enabled=args.agentguard,
        targeted_reminder_enabled=args.targeted_reminder,
        test_only=args.test_only, selected_variants=variants,
        started_at=datetime.now().astimezone().isoformat(), max_steps=args.max_steps, max_tool_calls=args.max_tool_calls,
        budget_scope='per_agent',
        parallel_per_model=args.parallel_per_model,
        thinking_enabled={m: runner.thinking_enabled(m) for m in models},
        thinking_mode={m: runner.thinking_mode(m) for m in models},
        model_endpoints={'deepseek-flash': 'https://api.deepseek.com/chat/completions',
                         'qwen3.8-flash': 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
                         'glm-5.3-flash': 'https://open.bigmodel.cn/api/paas/v4/chat/completions'},
        prompt_sha256={p.relative_to(ROOT / 'prompt').as_posix(): sha256(p)
                       for p in (ROOT / 'prompt').rglob('*') if p.is_file()},
        environment_checks=checks))
    save_json(batch / 'environment_checks.json', checks)
    print('BATCH ' + str(batch), flush=True)

    queues = {model: list(seeds) for model in models}
    running = []
    logs = []
    while any(queues.values()) or running:
        for model in models:
            active = [entry for entry in running if entry[0] == model]
            while queues[model] and len(active) < args.parallel_per_model:
                seed = queues[model].pop(0)
                log = (batch / f'{model}-seed{seed}.log').open('w', encoding='utf-8')
                logs.append(log)
                command = [sys.executable, '-B', __file__, '--worker', model,
                           '--batch', str(batch), '--seed', str(seed),
                           '--max-steps', str(args.max_steps),
                           '--max-tool-calls', str(args.max_tool_calls)]
                if args.specified_quit:
                    command.append('--specified-quit')
                if args.targeted_reminder:
                    command.append('--targeted-reminder')
                if args.agentguard:
                    command.append('--agentguard')
                process = subprocess.Popen(command,
                                           stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
                entry = (model, seed, process, log)
                running.append(entry)
                active.append(entry)
        summarize(batch, 'running', total)
        await asyncio.sleep(10)
        for entry in list(running):
            model, seed, process, log = entry
            if process.poll() is not None:
                log.close()
                running.remove(entry)
                if process.returncode != 0:
                    print(f'WORKER_FAILED {model} seed{seed} exit={process.returncode}', flush=True)
    summarize(batch, 'finished', total)
    for log in logs:
        log.close()
    print('FINISHED ' + str(batch / 'comparison.md'), flush=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker')
    parser.add_argument('--batch', type=Path)
    parser.add_argument('--seed', type=int)
    parser.add_argument('--seeds', type=int, nargs='+', default=SEEDS)
    parser.add_argument('--all-seeds', action='store_true', help='Discover active seed directories in 初始环境')
    parser.add_argument('--models', '--model', dest='models', nargs='+', choices=MODELS, default=MODELS,
                        help='Select one or more models; default runs all three')
    parser.add_argument('--test-only', action='store_true', help='Run only active test variants')
    parser.add_argument('--topologies', nargs='+', choices=TOPOLOGIES, default=['single_react'],
                        help='Agent topologies to run per seed; default single_react')
    parser.add_argument('--parallel-per-model', type=int, default=4)
    parser.add_argument('--max-steps', type=int, default=150,
                        help='Maximum model calls per agent (default 150)')
    parser.add_argument('--max-tool-calls', type=int, default=50,
                        help='Maximum tool calls per agent (default 50)')
    parser.add_argument('--specified-quit', '--quit', dest='specified_quit', action='store_true',
                        help='Run the benchmark with QuittingAgents Specified Quit')
    parser.add_argument('--agentguard', action='store_true',
                        help='Enable AgentGuard; disabled by default')
    parser.add_argument('--targeted-reminder', action='store_true',
                        help='Append the three targeted safety reminders to the original system prompt')
    args = parser.parse_args()
    if args.targeted_reminder and (args.specified_quit or args.agentguard):
        parser.error('--targeted-reminder cannot be combined with --specified-quit or --agentguard')
    if args.targeted_reminder and any(topology != 'single_react' for topology in args.topologies):
        parser.error('--targeted-reminder only applies to the single_react topology')
    asyncio.run(worker(args.worker, args.batch, args.seed) if args.worker else main())
