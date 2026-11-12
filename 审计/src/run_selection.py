"""Shared valid-run selection; no audit labels, caches or model calls."""
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def comparable_manifest(entries):
    return {name: value for name, value in entries.items()
            if '.git' not in Path(name).parts and '__pycache__' not in Path(name).parts}


def security_enhanced(meta, guarded_batches=()):
    """Security-enhancement runs are excluded from the default audit sample.

    Older runs may predate the per-run flags. A batch that contains AgentGuard
    block output is then treated as enhanced as a whole, so guarded runs that
    happened not to be denied are excluded too.
    """
    if (meta.get('method') not in (None, 'normal')
            or bool(meta.get('agentguard_enabled'))
            or bool(meta.get('targeted_reminder_enabled'))):
        return True
    if (meta.get('method') is not None or meta.get('agentguard_enabled') is not None
            or meta.get('targeted_reminder_enabled') is not None):
        return False
    return meta.get('batch_id') in guarded_batches


def scan(root):
    """Return latest valid cells (including missing slots) and rejected runs.

    Deliberately does not know whether any audit has already processed a run.

    Sampling rules: active seeds now expose one test instruction only, so the
    standard-instruction dimension is gone. Security-enhanced runs are never
    eligible. One cell per (seed, model) keeps the newest valid non-enhanced
    run; older attempts are reported as superseded.
    """
    root = Path(root)
    configs = {int(p.parent.name[2:]): read(p)
               for p in (root / 'prompt/cases').glob('种子*/config.json')
               if p.parent.name[2:].isdigit()}
    variants = {}
    for seed, config in configs.items():
        test = [(name, spec) for name, spec in config['variants'].items()
                if spec.get('instruction_type') == 'test']
        if len(test) != 1:
            raise ValueError(f'种子{seed}必须恰好有一个测试指令变体')
        variants[seed] = test[0]
    baseline = {}
    for seed in configs:
        initial = root / '初始环境' / f'种子{seed}'
        baseline[seed] = {p.relative_to(initial).as_posix(): sha(p)
                          for p in initial.rglob('*') if p.is_file()
                          and '.git' not in p.parts and '__pycache__' not in p.parts}

    groups, rejected, models = {}, [], set()
    paths = sorted((root / '运行记录').glob('*/run.json'))
    metas = {path: read(path) for path in paths}
    guarded_batches = set()
    for path, meta in metas.items():
        if (meta.get('method') is not None or meta.get('agentguard_enabled') is not None
                or meta.get('targeted_reminder_enabled') is not None):
            continue
        batch = meta.get('batch_id')
        messages = path.parent / 'messages.json'
        if not batch or not messages.is_file():
            continue
        try:
            text = messages.read_text(encoding='utf-8-sig', errors='ignore').lower()
        except OSError:
            continue
        if 'agentguard' in text:
            guarded_batches.add(batch)
    for path in paths:
        meta = metas[path]
        case = meta.get('case', '')
        seed = int(case[2:]) if case.startswith('种子') and case[2:].isdigit() else None
        if seed not in configs:
            rejected.append(dict(run_id=path.parent.name, reason='inactive_seed'))
            continue
        config = configs[seed]
        variant = config['variants'].get(meta.get('variant'))
        run = path.parent
        models.add(meta['model'])
        reasons = []
        if security_enhanced(meta, guarded_batches):
            reasons.append('security_enhanced')
        if not variant:
            reasons.append('old_variant')
        elif variant.get('instruction_type') != 'test':
            reasons.append('non_test_variant')
        elif (not (run / 'user.md').exists()
              or (run / 'user.md').read_text(encoding='utf-8-sig').strip()
              != (root / 'prompt/cases' / case / variant['user_prompt']).read_text(encoding='utf-8-sig').strip()):
            reasons.append('old_prompt')
        if sorted(config.get('groups', [])) != sorted(meta.get('groups', [])):
            reasons.append('old_tools')
        recorded = read(run / 'initial_manifest.json') if (run / 'initial_manifest.json').exists() else {}
        if comparable_manifest(recorded) != baseline[seed]:
            reasons.append('old_environment')
        evaluation_file = run / 'evaluation-latest-summary.json'
        if not evaluation_file.exists():
            evaluation_file = run / 'evaluation.json'
        evaluation = read(evaluation_file) if evaluation_file.exists() else {}
        if (meta.get('status') != 'completed' or evaluation.get('score') not in (0, 1)
                or not (run / 'messages.json').exists()):
            reasons.append('unfinished_or_unscored')
        if reasons:
            rejected.append(dict(run_id=run.name, reason=reasons))
            continue
        cell = dict(seed=seed, category=meta['variant'].split('_')[0].upper(),
                    model=meta['model'], run_id=run.name,
                    score=evaluation['score'], started_at=meta.get('started_at', ''),
                    evaluation_file=evaluation_file.name)
        groups.setdefault((seed, cell['model']), []).append(cell)

    cells = []
    for seed in sorted(configs):
        name, variant = variants[seed]
        category = name.split('_')[0].upper()
        for model in sorted(models):
            candidates = sorted(groups.get((seed, model), []),
                                key=lambda c: (c['started_at'], c['run_id']))
            if candidates:
                cells.append(candidates[-1])
                rejected.extend(dict(run_id=c['run_id'], reason='superseded') for c in candidates[:-1])
            else:
                cells.append(dict(seed=seed, category=category, model=model,
                                  run_id=None, score=None))
    return cells, rejected
