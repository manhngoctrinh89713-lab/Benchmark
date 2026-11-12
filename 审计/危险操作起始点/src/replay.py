"""Replay recorded local tools, fail on divergence, evaluate every prefix."""
import argparse
import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
from uuid import uuid4
HOME = Path(__file__).resolve().parents[1]
ROOT = HOME.parent.parent
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / '审计/src'))
from run_selection import scan as scan_valid_runs


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


@contextmanager
def work_directory(parent, prefix='replay-'):
    """Create a normal-mode temp directory.

    tempfile.mkdtemp creates 0o700 directories, whose ACL is unusable for
    nested copies under the Windows sandbox used for these audits.
    """
    parent = Path(parent)
    parent.mkdir(parents=True, exist_ok=True)
    while True:
        path = parent / (prefix + uuid4().hex[:8])
        try:
            os.makedirs(path)
            break
        except FileExistsError:
            continue
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def manifest(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()}


def canonical(value):
    """Ignore JSON formatting/key order, but never discard IDs or times."""
    if isinstance(value, dict):
        return {k: canonical(v) for k, v in value.items()}
    if isinstance(value, list):
        return [canonical(v) for v in value]
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except ValueError:
            return value
        if isinstance(decoded, (dict, list)):
            return canonical(decoded)
    return value


def environment_diff(expected, actual):
    """Require the same files and contents; JSON whitespace/order may differ."""
    old, new = manifest(expected), manifest(actual)
    different = []
    for name in sorted(old.keys() | new.keys()):
        if old.get(name) == new.get(name):
            continue
        if name in old and name in new and name.endswith('.json'):
            try:
                if read(expected / name) == read(actual / name):
                    continue
            except (ValueError, UnicodeError):
                pass
        different.append(name)
    return different


def score(evaluation):
    value = evaluation.get('score')
    if type(value) is not int or value not in (0, 1):
        raise ValueError('评测函数未返回整数安全分0或1')
    return value


def first_unsafe(timeline):
    if not timeline or timeline[0]['score'] != 1:
        raise ValueError('初始状态必须为安全1，不能定义首次1→0')
    return next((dict(ordinal=t['ordinal'], tool_call_id=t['tool_call_id'], name=t['name'])
                 for t in timeline[1:] if t['score'] == 0), None)


def preflight(run):
    from harness.sandbox import validate_tree
    meta = read(run / 'run.json')
    if meta.get('status') != 'completed':
        raise ValueError('运行未完成，不以部分轨迹发布危险点')
    case = meta.get('case', '')
    if not re.fullmatch(r'种子\d+', case):
        raise ValueError('不支持的种子名称')
    initial = ROOT / '初始环境' / case
    validate_tree(initial)
    if manifest(initial) != read(run / 'initial_manifest.json'):
        raise ValueError('初始环境版本不匹配')
    config = read(ROOT / 'prompt/cases' / case / 'config.json')
    if sorted(config['groups']) != sorted(meta.get('groups', [])):
        raise ValueError('工具组版本不匹配')
    if not config.get('evaluator'):
        raise ValueError('种子没有安全评测函数')
    files = sorted(run.glob('tool-*.json'))
    expected = [f'tool-{i:03d}.json' for i in range(1, len(files) + 1)]
    if [p.name for p in files] != expected or len(files) != meta.get('tool_calls'):
        raise ValueError('工具记录缺失或序号不连续')
    calls = [read(p) for p in files]
    ids = [c['id'] for c in calls]
    if len(set(ids)) != len(ids) or any('result' not in c for c in calls):
        raise ValueError('工具记录不完整或调用ID重复')
    # Cross-check against the messages used by the original model.
    messages = read(run / 'messages.json')
    declared = [c for m in messages if m.get('role') == 'assistant' for c in m.get('tool_calls', [])]
    returned = [m for m in messages if m.get('role') == 'tool']
    if [c['id'] for c in declared] != ids or [m['tool_call_id'] for m in returned] != ids:
        raise ValueError('工具记录与messages调用序列不一致')
    for call, declaration, result in zip(calls, declared, returned):
        if (call['name'] != declaration['function']['name']
                or canonical(call['arguments']) != canonical(declaration['function']['arguments'])
                or canonical(call['result']) != canonical(json.loads(result['content']))):
            raise ValueError('工具记录与messages内容不一致')
    return meta, initial, config, calls


async def replay(run, output, snapshots=False, strict=False):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from harness.evaluation import evaluate_case
    from harness.environment import apply_private_directories
    from harness.sandbox import validate_tree

    result = dict(run_id=run.name, status='error', first_unsafe=None, timeline=[],
                  comparison_profile='strict-v1' if strict else 'semantic-v5',
                  definition='首次按当前安全评测函数从1变为0的工具调用',
                  historical_tool_source_version='not_recorded; checked via catalog and replay outputs')
    comparison = None
    try:
        meta, initial, config, calls = preflight(run)
        evaluator = config['evaluator']
        result['evaluator'] = evaluator
        stored_path = run / 'evaluation-latest-summary.json'
        if not stored_path.exists():
            stored_path = run / 'evaluation.json'
        result['initial_manifest_sha256'] = hashlib.sha256((run / 'initial_manifest.json').read_bytes()).hexdigest()
        result['evaluator_sha256'] = hashlib.sha256((ROOT / '评测函数' / (meta['case'] + '.py')).read_bytes()).hexdigest()
        work = HOME / '工作区'
        work.mkdir(exist_ok=True)
        with work_directory(work) as temp:
            temp = Path(temp)
            env = temp / 'final_environment'
            shutil.copytree(initial, env)
            initial_copy = temp / 'initial_environment'
            shutil.copytree(initial, initial_copy)
            reference_env = temp / 'reference/final_environment'
            validate_tree(run / 'final_environment')
            shutil.copytree(run / 'final_environment', reference_env)
            # Some evaluators (e.g. seed35) read logs alongside final_environment.
            for log in run.glob('tool-*.json'):
                shutil.copy2(log, reference_env.parent / log.name)
            if (run / 'tools.jsonl').exists():
                shutil.copy2(run / 'tools.jsonl', reference_env.parent / 'tools.jsonl')
            reference = evaluate_case(evaluator, reference_env, initial_copy)
            if score(reference) != score(read(stored_path)):
                raise ValueError('当前评测与已保存安全分不一致，请先核验评测版本')
            result['reference_final_score'] = score(reference)
            if not strict:
                from semantic import Comparison
                comparison = Comparison(meta['run_root'], env, reference_env)
                result['comparison_profile'] = comparison.profile
            apply_private_directories(env)

            def evaluate_step(ordinal, call=None):
                validate_tree(env)
                before = manifest(env)
                evaluation = evaluate_case(evaluator, env, initial_copy)
                if manifest(env) != before:
                    raise ValueError('评测函数改动了重放环境，停止审计')
                item = dict(ordinal=ordinal, tool_call_id=call['id'] if call else None,
                            name=call['name'] if call else None, score=score(evaluation), evaluation=evaluation)
                result['timeline'].append(item)
                if snapshots:
                    target = output / 'snapshots' / f'{ordinal:03d}'
                    shutil.copytree(env, target / 'final_environment')
                    for log in temp.glob('tool-*.json'):
                        shutil.copy2(log, target / log.name)
                    save(target / 'evaluation.json', evaluation)

            evaluate_step(0)
            if result['timeline'][0]['score'] != 1:
                raise ValueError('初始状态已为安全0，无法定义首次1→0')
            worker_env = {k: v for k, v in os.environ.items() if k.upper() in {
                'SYSTEMROOT', 'WINDIR', 'PATH', 'PATHEXT', 'COMSPEC', 'TEMP', 'TMP', 'USERPROFILE'}}
            worker_env.update(PYTHONPATH=str(ROOT / 'src'), PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')
            params = StdioServerParameters(command=sys.executable,
                args=['-B', '-m', 'harness.worker', '--run-root', str(env), '--groups', *meta['groups']],
                cwd=str(ROOT), env=worker_env)
            output.mkdir(parents=True, exist_ok=True)
            with (output / 'worker.log').open('w', encoding='utf8') as stderr:
                async with stdio_client(params, errlog=stderr) as (reader, writer):
                    async with ClientSession(reader, writer) as session:
                        await session.initialize()
                        catalog = (await session.list_tools()).tools
                        current_tools = [{'type': 'function', 'function': {'name': t.name,
                            'description': t.description or '', 'parameters': t.inputSchema}} for t in catalog]
                        by_name = lambda arr: {t['function']['name']: t for t in arr}
                        if canonical(by_name(current_tools)) != canonical(by_name(read(run / 'tools.json'))):
                            raise ValueError('当前工具定义与运行保存的tools.json不匹配')
                        known = {t.name for t in catalog}
                        for ordinal, call in enumerate(calls, 1):
                            result['attempted_ordinal'] = ordinal
                            executed_arguments = call['arguments']
                            try:
                                if call['name'] not in known:
                                    raise ValueError('工具未启用')
                                args = json.loads(call['arguments'])
                                if not isinstance(args, dict):
                                    raise ValueError('工具参数必须是 JSON 对象')
                                if comparison:
                                    args = comparison.arguments(args)
                                    comparison.prepare_call(call['name'], args)
                                executed_arguments = json.dumps(args, ensure_ascii=False)
                                response = await session.call_tool(call['name'], args,
                                    read_timeout_seconds=timedelta(seconds=90))
                                actual = response.model_dump(mode='json', exclude_none=True)
                            except (ValueError, TypeError) as error:
                                actual = {'isError': True, 'content': [{'type': 'text', 'text': str(error)}]}
                            apply_private_directories(env, create=False)
                            equal = comparison.tool_equal(call['name'], call['result'], actual) if comparison else canonical(actual) == canonical(call['result'])
                            if not equal:
                                save(output / 'divergence.json', dict(ordinal=ordinal, tool_call_id=call['id'],
                                     expected=call['result'], actual=actual))
                                raise ValueError(f'第{ordinal}次工具返回与原记录不一致')
                            event = dict(call, result=actual, arguments=executed_arguments)
                            save(temp / f'tool-{ordinal:03d}.json', event)
                            with (temp / 'tools.jsonl').open('a', encoding='utf8') as stream:
                                stream.write(json.dumps(event, ensure_ascii=False) + '\n')
                            evaluate_step(ordinal, call)
                            print(f'{run.name}: {ordinal}/{len(calls)} score={result["timeline"][-1]["score"]}', flush=True)
            if result['timeline'][-1]['score'] != score(reference):
                raise ValueError('重放最终安全分与原终态重新评测不一致')
            details = {}
            if comparison:
                differences, details = comparison.environment_diff(run / 'final_environment', env)
            else:
                differences = environment_diff(run / 'final_environment', env)
            if differences:
                save(output / 'environment_divergence.json', dict(different_files=differences, field_differences=details))
                raise ValueError('重放终态与原环境不一致，可能存在工具版本或动态行为差异：' + ', '.join(differences[:5]))
            result['final_environment_verified'] = True
            result['first_unsafe'] = first_unsafe(result['timeline'])
            result['status'] = 'verified' if result['first_unsafe'] else 'no_unsafe_action'
    except Exception as error:
        from harness.transport import describe_error
        result['error'] = describe_error(error)
        # A failed replay must never expose a candidate as a confirmed danger point.
        result['first_unsafe'] = None
    if comparison:
        result['normalizations'] = sorted(comparison.notes)
        result['replay_to_recorded_aliases'] = comparison.aliases
    save(output / 'result.json', result)
    lines = ['# 逐步安全分', '', f'状态：{result["status"]}', '',
             '安全分序列：' + ' → '.join(str(t['score']) for t in result['timeline']), '',
             '|工具调用序号|调用ID|工具|安全分|', '|---:|---|---|---:|']
    for item in result['timeline']:
        lines.append(f'|{item["ordinal"]}|{item["tool_call_id"] or "—"}|{item["name"] or "初始状态"}|{item["score"]}|')
    if result.get('error'):
        lines += ['', '核验未通过，以上仅为已执行部分，不发布危险点。', '', result['error']]
    elif result['first_unsafe']:
        lines += ['', f'已核验首次危险调用：第{result["first_unsafe"]["ordinal"]}次，'
                      f'{result["first_unsafe"]["name"]}，ID={result["first_unsafe"]["tool_call_id"]}。']
    (output / '逐步评分.md').write_text('\n'.join(lines) + '\n', encoding='utf8')
    return result


def latest_index(folder, results):
    """Index the newest full-batch boundary run for the evidence audit default source."""
    return dict(batch=str(folder), report=str(folder / '报告.md'), summary=str(folder / '汇总.json'),
                status='completed' if not any(r['status'] == 'error' for r in results) else 'partial',
                total=len(results),
                counts={name: sum(r['status'] == name for r in results)
                        for name in sorted({r['status'] for r in results})})


def select_runs(args, selection=None):
    parent = ROOT / '运行记录'
    cells, rejected = selection if selection is not None else scan_valid_runs(ROOT)
    selected = {c['run_id']: c for c in cells if c['run_id']}
    if args.run_id:
        result = []
        for name in dict.fromkeys(args.run_id):
            path = (parent / name).resolve()
            if path.parent != parent.resolve() or not (path / 'run.json').is_file():
                raise ValueError(f'无效运行ID：{name}')
            if name not in selected:
                reason = next((r['reason'] for r in rejected if r['run_id'] == name), '未通过有效运行筛选')
                raise ValueError(f'运行未入选：{name}；原因：{reason}')
            if selected[name]['score'] != 0:
                raise ValueError(f'安全分为1的运行不进行危险操作起始点审计：{name}')
            result.append(path)
        return result
    return [parent / c['run_id'] for c in cells if c['run_id'] and c['score'] == 0
            and (not args.seeds or c['seed'] in args.seeds)]


def main():
    parser = argparse.ArgumentParser(description='独立副本重放，每次工具调用后计算安全分；不调用模型API')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--run-id', nargs='+', help='指定运行记录目录名')
    group.add_argument('--seeds', type=int, nargs='+', help='所选种子的最新有效运行')
    group.add_argument('--all', action='store_true', help='全部最新有效运行（共用筛选器）')
    parser.add_argument('--workers', type=int, default=4, help='独立重放并发数，默认4')
    parser.add_argument('--strict', action='store_true', help='使用原始严格逐字节核验；默认采用可追溯语义核验')
    parser.add_argument('--save-snapshots', action='store_true', help='额外保留每一步完整环境及截至该步的工具日志')
    args = parser.parse_args()
    if args.workers < 1:
        parser.error('workers必须大于0')
    try:
        selection = scan_valid_runs(ROOT)
        runs = select_runs(args, selection)
    except ValueError as error:
        parser.error(str(error))
    if not runs:
        parser.error('没有匹配运行')
    folder = HOME / '结果' / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:6])
    folder.mkdir(parents=True)
    save(folder / '筛选清单.json', dict(cells=selection[0], ignored_runs=selection[1],
         selected_run_ids=[r.name for r in runs]))
    print(f'入选{len(runs)}条；批次：{folder}', flush=True)
    results = []
    async def run_batch():
        sem = asyncio.Semaphore(args.workers)
        async def one(run):
            async with sem:
                result = await replay(run, folder / run.name, args.save_snapshots, args.strict)
                results.append(result)
                save(folder / '汇总.json', sorted(results, key=lambda r: r['run_id']))
                print(f'[{len(results)}/{len(runs)}]', run.name, result['status'], result.get('error', ''), flush=True)
        await asyncio.gather(*(one(run) for run in runs))
    asyncio.run(run_batch())
    results.sort(key=lambda r: r['run_id'])
    lines = ['# 危险操作起始点', '', '|运行ID|状态|首次危险调用序号|错误|', '|---|---|---:|---|']
    for result in results:
        point = result['first_unsafe'] or {}
        error = result.get('error', '').replace('|', '/').replace('\n', ' ')
        lines.append(f'|{result["run_id"]}|{result["status"]}|{point.get("ordinal", "—")}|{error}|')
    (folder / '报告.md').write_text('\n'.join(lines) + '\n', encoding='utf8')
    if args.all:
        # Partial --seeds batches must not replace the full-batch index.
        save(HOME / '最新结果.json', latest_index(folder, results))
    print('结果：', folder)
    return int(any(r['status'] == 'error' for r in results))
