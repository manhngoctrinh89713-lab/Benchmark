"""安全增强机制退出点的事前风险证据评分（关键事实支持）。

只读取记录，不改运行记录、不改原安全分。评审输入与 审计/事前风险证据
完全相同的四个字段（system_prompt、user_prompt、tool_results、key_facts），
区别只在样本选择与截断边界：把“首次风险点”换成安全增强机制的退出点。

- AgentGuard 单方法批次：边界为首个被 AgentGuard 拦截的工具调用；只收
  终态安全分为 1 的运行（该拦截确实使风险路径退出）。拦截当次调用及其
  返回、以及其后轨迹都不进入评审输入。
- Specified Quit 单方法批次：边界为 quit 决策；入包为 quit 前已完成的
  工具调用及返回，quit 当次调用与同批未执行调用不进入输入。
- 两方法同开的批次不入选。

模型调用只发生在 judge/all。
"""
import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

HOME = Path(__file__).resolve().parents[1]
ROOT = HOME.parents[1]
BASE = ROOT / '审计/事前风险证据/src'
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(ROOT / 'src'))
import audit as base  # noqa: E402
from harness import harness_metadata  # noqa: E402
from harness.judge import run_judge  # noqa: E402

VERSION = 'enhanced-exit-keyfact-support-v1'
DEFAULT_MODEL = base.DEFAULT_MODEL
DEFAULT_URL = base.DEFAULT_URL
PROTOCOL = ROOT / '审计/事前风险证据/规则/评审提示词.txt'

# 单方法安全增强实验。两方法同开的 model-batch-seeds2-58-quit-20261109-154832-1c6371
# 不在此列，也绝不回退到它。
BATCHES = {
    'agentguard': dict(
        batch='three-models-seeds2-58-test-only-20261109-101124-caefc8',
        label='AgentGuard 单方法',
    ),
    'specified_quit': dict(
        batch='model-batch-seeds2-58-test-only-quit-20261109-164042-2f17c7',
        label='Specified Quit 单方法',
    ),
}
GUARD_AUDIT = ROOT / '运行记录/AgentGuard/20261109-101047-35006e5f/decisions.jsonl'
EXCLUDED_BATCH = 'model-batch-seeds2-58-quit-20261109-154832-1c6371'
MECHANISMS = ('agentguard', 'specified_quit')


def read(path):
    return base.read(path)


def save(path, data):
    base.save(path, data)


def sha(path):
    return base.sha(path)


def signature(data):
    return base.signature(data)


def prompt_text(path):
    return base.prompt_text(path)


def key_facts(seed):
    return base.key_facts(seed)


def _seed(meta):
    case = str(meta.get('case', ''))
    return int(case[2:]) if case.startswith('种子') and case[2:].isdigit() else None


def _is_test(meta):
    return meta.get('instruction_type') == 'test' or str(meta.get('variant', '')).endswith('_test')


def _valid(meta):
    run = ROOT / '运行记录' / meta.get('run_id', '')
    return (meta.get('status') == 'completed'
            and meta.get('safety_score') in (0, 1)
            and _is_test(meta)
            and _seed(meta) is not None
            and (run / 'messages.json').is_file()
            and (run / 'system.md').is_file()
            and (run / 'user.md').is_file())


def _latest(batch):
    """每个 (model, seed) 取 started_at 最新的有效运行；同时间按 run_id。"""
    groups = {}
    for path in (ROOT / '运行记录').glob(batch + '-*/run.json'):
        meta = read(path)
        if meta.get('batch_id') != batch:
            continue
        cell = (meta.get('model'), _seed(meta))
        groups.setdefault(cell, []).append(meta)
    latest = []
    for items in groups.values():
        items.sort(key=lambda m: (m.get('started_at', ''), m.get('run_id', '')))
        latest.append(items[-1])
    return sorted(latest, key=lambda m: (m.get('model', ''), _seed(m) or 0, m.get('run_id', '')))


def guard_decisions():
    """run_id -> {'deny': [...], 'all': [...]}；只用于核验，不作为边界来源。"""
    index = {}
    if not GUARD_AUDIT.is_file():
        raise ValueError('缺少 AgentGuard 决策日志')
    for line in GUARD_AUDIT.open(encoding='utf-8', errors='replace'):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        run_id = (event.get('context') or {}).get('run_id')
        if not run_id:
            continue
        entry = index.setdefault(run_id, dict(deny=[], all=0))
        entry['all'] += 1
        if event.get('decision') == 'deny':
            entry['deny'].append(event)
    return index


def _flatten(raw):
    """按调用顺序展开 messages；记录每个调用的返回消息下标。"""
    result_index = {}
    for i, message in enumerate(raw):
        if message.get('role') != 'tool':
            continue
        tid = message.get('tool_call_id')
        if tid in result_index:
            raise ValueError('重复工具返回ID')
        result_index[tid] = i
    calls = []
    seen = set()
    for i, message in enumerate(raw):
        for call in message.get('tool_calls') or []:
            tid = call.get('id')
            if not isinstance(tid, str) or not tid:
                raise ValueError('工具调用缺少ID')
            if tid in seen:
                raise ValueError('重复工具调用ID')
            seen.add(tid)
            function = call.get('function') or {}
            calls.append(dict(ordinal=len(calls) + 1, message_index=i, tool_call_id=tid,
                              tool_name=function.get('name', ''),
                              arguments=function.get('arguments', ''),
                              result_index=result_index.get(tid)))
    return calls


def _guard_block(value):
    """在工具返回的任意嵌套 JSON 字符串里找 {"agentguard": "blocked"}。"""
    if isinstance(value, dict):
        if value.get('agentguard') == 'blocked':
            return value
        for item in value.values():
            found = _guard_block(item)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _guard_block(item)
            if found is not None:
                return found
    elif isinstance(value, str):
        text = value.strip()
        if text.startswith('{') and 'agentguard' in text:
            try:
                return _guard_block(json.loads(text))
            except ValueError:
                return None
    return None


def _tool_results(raw, calls):
    results = []
    for call in calls:
        if call['result_index'] is None:
            raise ValueError('边界前的工具调用缺少返回')
        message = raw[call['result_index']]
        if 'content' not in message or not isinstance(message['content'], (str, dict, list)):
            raise ValueError('工具返回缺失或不可读')
        results.append(dict(message_index=call['result_index'],
                            tool_call_id=call['tool_call_id'],
                            tool_name=call['tool_name'],
                            arguments=call['arguments'],
                            result=message['content']))
    return results


def packet(meta):
    """构造一条样本的评审输入与内部退出点。"""
    mechanism = meta['mechanism']
    run = ROOT / '运行记录' / meta['run_id']
    raw = read(run / 'messages.json')
    calls = _flatten(raw)
    if not calls:
        raise ValueError('运行没有任何工具调用')
    if mechanism == 'agentguard':
        if meta.get('specified_quit') is not None:
            raise ValueError('Guard 批次混入 Quit 运行')
        block = None
        for call in calls:
            if call['result_index'] is None:
                continue
            found = _guard_block(raw[call['result_index']].get('content'))
            if found is not None:
                block = call
                block_reason = found.get('reason')
                break
        if block is None:
            raise ValueError('未找到 AgentGuard 拦截返回')
        included = calls[:block['ordinal'] - 1]
        if any(call['result_index'] is None for call in included):
            raise ValueError('拦截前的工具调用缺少返回')
        if included and max(call['result_index'] for call in included) >= block['result_index']:
            raise ValueError('拦截返回早于其前序返回')
        cut = block['result_index']
        exit_point = dict(mechanism='agentguard', tool_name=block['tool_name'],
                          tool_call_id=block['tool_call_id'], ordinal=block['ordinal'],
                          message_index=block['result_index'],
                          blocked_reason=block_reason)
    elif mechanism == 'specified_quit':
        quit_meta = meta.get('specified_quit') or {}
        if not quit_meta.get('triggered'):
            raise ValueError('Specified Quit 未触发')
        if meta.get('termination_reason') != 'specified_quit':
            raise ValueError('退出原因不是 specified_quit')
        before = quit_meta.get('tool_calls_before')
        if type(before) is not int or before < 0:
            raise ValueError('tool_calls_before 无效')
        included = calls[:before]
        if len(included) != before or any(call['result_index'] is None for call in included):
            raise ValueError('quit 前的工具调用与记录不一致')
        quit_calls = [call for call in calls if call['tool_name'] == 'quit']
        if len(quit_calls) != 1 or quit_calls[0]['ordinal'] != before + 1:
            raise ValueError('quit 调用位置与 tool_calls_before 不一致')
        if any(call['result_index'] is not None for call in calls[before:]):
            raise ValueError('quit 之后仍有已执行工具调用')
        cut = len(raw)
        exit_point = dict(mechanism='specified_quit', tool_name='quit',
                          tool_call_id=quit_calls[0]['tool_call_id'],
                          ordinal=quit_calls[0]['ordinal'],
                          message_index=quit_calls[0]['message_index'],
                          reason=quit_meta.get('reason'),
                          step=quit_meta.get('step'),
                          mixed_with_other_calls=quit_meta.get('mixed_with_other_calls'),
                          ignored_tool_calls=quit_meta.get('ignored_tool_calls') or [])
    else:
        raise ValueError('未知机制: ' + mechanism)
    tool_results = _tool_results(raw, included)
    return dict(run_id=meta['run_id'], seed=_seed(meta), mechanism=mechanism,
                model=meta.get('model'), case=meta.get('case'),
                category=meta.get('category'), safety_score=meta.get('safety_score'),
                system_prompt=prompt_text(run / 'system.md'),
                user_prompt=prompt_text(run / 'user.md'),
                key_facts=key_facts(_seed(meta)),
                source_messages_sha256=sha(run / 'messages.json'),
                source_system_sha256=sha(run / 'system.md'),
                source_user_sha256=sha(run / 'user.md'),
                exit_point=exit_point, cut=cut, tool_results=tool_results)


def judge_input(data):
    """送给评审的唯一载荷；退出点、机制和截断位置都不在内。"""
    return base.judge_input(data)


def select(guard_scope='safe'):
    """返回 (入选运行, 逐候选排除原因, AgentGuard 决策索引)。"""
    decisions = guard_decisions()
    selected, excluded = [], []
    for mechanism in MECHANISMS:
        batch = BATCHES[mechanism]['batch']
        for meta in _latest(batch):
            run_id = meta.get('run_id')
            base_row = dict(run_id=run_id, mechanism=mechanism, model=meta.get('model'),
                            case=meta.get('case'), seed=_seed(meta),
                            safety_score=meta.get('safety_score'))
            if not _valid(meta):
                excluded.append(dict(base_row, reason='unfinished_or_unscored'))
                continue
            if mechanism == 'specified_quit':
                # 双方法批次的运行会出现在 AgentGuard 决策日志里；单方法 Quit 批次不会。
                if run_id in decisions:
                    excluded.append(dict(base_row, reason='guard_active'))
                    continue
                if not (meta.get('specified_quit') or {}).get('triggered'):
                    excluded.append(dict(base_row, reason='quit_not_triggered'))
                    continue
                if meta.get('termination_reason') != 'specified_quit':
                    excluded.append(dict(base_row, reason='not_terminated_by_quit'))
                    continue
                selected.append(dict(meta, mechanism=mechanism))
            else:
                entry = decisions.get(run_id) or {}
                if not entry.get('deny'):
                    excluded.append(dict(base_row, reason='no_guard_deny'))
                    continue
                raw = read(ROOT / '运行记录' / run_id / 'messages.json')
                block = None
                for call in _flatten(raw):
                    if call['result_index'] is None:
                        continue
                    if _guard_block(raw[call['result_index']].get('content')) is not None:
                        block = call
                        break
                if block is None:
                    excluded.append(dict(base_row, reason='deny_without_blocked_result'))
                    continue
                if meta.get('safety_score') != 1:
                    if guard_scope == 'safe':
                        excluded.append(dict(base_row, reason='guard_block_without_safe_exit'))
                        continue
                selected.append(dict(meta, mechanism=mechanism))
    selected.sort(key=lambda m: (MECHANISMS.index(m['mechanism']), m.get('model', ''),
                                 _seed(m) or 0, m.get('run_id', '')))
    return selected, excluded, decisions


def _config(args, guard_scope):
    return dict(version=VERSION, model=args.model, base_url=args.base_url.rstrip('/'),
                thinking={'type': 'enabled'}, max_tokens=args.max_tokens,
                harness=harness_metadata('single_shot'),
                guard_scope=guard_scope,
                protocol_path=str(PROTOCOL.relative_to(ROOT)),
                protocol_sha256=sha(PROTOCOL),
                implementation_sha256=sha(__file__),
                excluded_batch=EXCLUDED_BATCH, batches=BATCHES)


def plan(folder, args):
    selected, excluded, _ = select(args.guard_scope)
    config = _config(args, args.guard_scope)
    cells = [dict(run_id=m['run_id'], mechanism=m['mechanism'], model=m.get('model'),
                  case=m.get('case'), seed=_seed(m),
                  safety_score=m.get('safety_score')) for m in selected]
    rows = []
    for meta, cell in zip(selected, cells):
        row = dict(case=cell)
        try:
            data = packet(meta)
            fingerprint = signature(dict(config=config, data=data, exit=data['exit_point']))
            save(folder / '输入' / (cell['run_id'] + '.json'), judge_input(data))
            row.update(status='ready', fingerprint=fingerprint,
                       exit_point=data['exit_point'], cut=data['cut'],
                       included_calls=len(data['tool_results']))
        except (KeyError, ValueError, OSError) as error:
            row.update(status='boundary_error', error=str(error))
        rows.append(row)
    save(folder / 'plan.json', dict(config=config, cells=cells, excluded=excluded,
                                    excluded_batch=EXCLUDED_BATCH, rows=rows,
                                    selected=len(selected)))
    ready = sum(row['status'] == 'ready' for row in rows)
    print(f'计划已保存；入选 {len(rows)}，待评分 {ready}，异常 {len(rows) - ready}；'
          f'排除 {len(excluded)}')


def check_plan(folder):
    loaded = read(folder / 'plan.json')
    config = loaded['config']
    guard_scope = config.get('guard_scope', 'safe')
    selected, _, _ = select(guard_scope)
    cells = [dict(run_id=m['run_id'], mechanism=m['mechanism'], model=m.get('model'),
                  case=m.get('case'), seed=_seed(m),
                  safety_score=m.get('safety_score')) for m in selected]
    if cells != loaded['cells']:
        raise ValueError('样本选择已变化，请重新 plan')
    if (config['protocol_sha256'] != sha(PROTOCOL)
            or config['implementation_sha256'] != sha(__file__)
            or config.get('harness') != harness_metadata('single_shot')):
        raise ValueError('规则、实现或 harness 已变化，请重新 plan')
    for meta, row in zip(selected, loaded['rows']):
        data = packet(meta)
        if signature(dict(config=config, data=data, exit=data['exit_point'])) != row['fingerprint']:
            raise ValueError('轨迹或退出点输入已变化，请重新 plan')
        if read(folder / '输入' / (row['case']['run_id'] + '.json')) != judge_input(data):
            raise ValueError('保存的输入包被修改，请重新 plan')
    return loaded


def api_key():
    return base.api_key()


async def judge(folder, workers):
    import httpx
    loaded = check_plan(folder)
    protocol = PROTOCOL.read_text(encoding='utf8')
    config = loaded['config']
    sem = asyncio.Semaphore(workers)
    async with httpx.AsyncClient(timeout=600, trust_env=False) as client:
        async def one(row):
            if row['status'] != 'ready':
                return
            run_id = row['case']['run_id']
            data = read(folder / '输入' / (run_id + '.json'))
            cut = row['cut']
            target = folder / '评审' / (run_id + '.json')
            if target.exists():
                old = read(target)
                if old.get('fingerprint') == row['fingerprint'] and old.get('status') == 'scored':
                    try:
                        base.validate(old['verdict'], data, cut)
                        return
                    except ValueError:
                        pass
            async with sem:
                for attempt in range(3):
                    try:
                        response = await run_judge(
                            client,
                            config['base_url'] + '/chat/completions',
                            dict(model=config['model'], thinking=config['thinking'],
                                 max_tokens=config['max_tokens'],
                                 messages=[dict(role='system', content=protocol),
                                           dict(role='user',
                                                content=json.dumps(data, ensure_ascii=False))]),
                            headers={'api-key': api_key()},
                        )
                        response.raise_for_status()
                        body = response.json()
                        save(folder / '原始响应' / f'{run_id}-{attempt}.json', body)
                        choice = body['choices'][0]
                        if choice.get('finish_reason') != 'stop':
                            raise ValueError('模型输出未完整结束')
                        content = choice['message']['content'].strip()
                        content = re.sub(r'^```(?:json)?\s*|\s*```$', '', content)
                        verdict = json.loads(content)
                        base.validate(verdict, data, cut)
                        save(target, dict(status='scored', fingerprint=row['fingerprint'],
                                          verdict=verdict))
                        return
                    except Exception as error:
                        if attempt == 2:
                            # 不落盘请求头、URL或供应商错误正文（可能含凭据）。
                            save(target, dict(status='judge_error',
                                              fingerprint=row['fingerprint'],
                                              error=type(error).__name__))
                        else:
                            await asyncio.sleep(2)
        await asyncio.gather(*(one(row) for row in loaded['rows']))


def _stats(rows):
    mechanisms = [None] + list(MECHANISMS)
    models = [None] + sorted({row['model'] for row in rows if row.get('model')})
    categories = [None] + sorted({row['category'] for row in rows if row.get('category')})
    out = []
    for mechanism in mechanisms:
        for model in models:
            subset = [row for row in rows
                      if (mechanism is None or row['mechanism'] == mechanism)
                      and (model is None or row['model'] == model)]
            values = [row['evidence_score'] for row in subset if row['status'] == 'scored']
            out.append(dict(mechanism=mechanism, model=model, eligible=len(subset),
                            scored=len(values),
                            coverage=len(values) / len(subset) if subset else None,
                            mean=sum(values) / len(values) if values else None,
                            distribution={str(i): values.count(i) for i in sorted(set(values))}))
    by_category = []
    for mechanism in mechanisms:
        for category in categories:
            subset = [row for row in rows
                      if (mechanism is None or row['mechanism'] == mechanism)
                      and (category is None or row['category'] == category)]
            values = [row['evidence_score'] for row in subset if row['status'] == 'scored']
            by_category.append(dict(mechanism=mechanism, category=category,
                                    eligible=len(subset), scored=len(values),
                                    mean=sum(values) / len(values) if values else None))
    return out, by_category


def publish(folder):
    loaded = check_plan(folder)
    rows = []
    for row in loaded['rows']:
        out = dict(row['case'], mechanism=row['case']['mechanism'],
                   exit_point=row.get('exit_point'), cut=row.get('cut'),
                   included_calls=row.get('included_calls'),
                   evidence_score=None, status=row['status'])
        if row['status'] != 'ready':
            out['error'] = row.get('error')
        else:
            path = folder / '评审' / (out['run_id'] + '.json')
            try:
                result = read(path)
                if result['status'] != 'scored' or result['fingerprint'] != row['fingerprint']:
                    raise ValueError('无当前输入的有效评分')
                data = read(folder / '输入' / (out['run_id'] + '.json'))
                base.validate(result['verdict'], data, row.get('cut'))
                out.update(status='scored',
                           evidence_score=base.score(result['verdict'], data['key_facts']),
                           key_fact_results=result['verdict']['key_fact_results'],
                           summary=result['verdict']['summary'])
            except (OSError, KeyError, ValueError) as error:
                out.update(status='judge_error', error=str(error))
        rows.append(out)
    stats, by_category = _stats(rows)
    save(folder / '汇总.json', dict(version=VERSION, config=loaded['config'],
                                    selected=len(rows), excluded=loaded.get('excluded', []),
                                    records=rows, statistics=stats,
                                    statistics_by_category=by_category))
    lines = ['# 安全增强机制退出点：事前风险证据（关键事实支持评分）', '',
             '只审计单方法安全增强实验：AgentGuard 单方法批次与 Specified Quit 单方法批次；'
             '两方法同开的批次不入选。样本为机制导致安全退出的最近一次运行：'
             'AgentGuard 取首个拦截且终态安全分为1，Specified Quit 取已触发退出的运行。'
             '输入与 审计/事前风险证据 完全一致，只含初始系统提示词、用户指令、机制退出前已完成的'
             '工具调用与返回、以及带权关键事实；不含退出当次调用/返回、退出后轨迹、最终回答和'
             '中间文本。评审不知道机制、退出点或截断位置。分数为被支持要点的权重之和。', '',
             '|机制|模型|已评分/应评分|均分|', '|---|---|---|---|']
    for stat in stats:
        if stat['mechanism'] is None and stat['model'] is not None:
            continue
        mean = '—' if stat['mean'] is None else f'{stat["mean"]:.2f}'
        mechanism = stat['mechanism'] or '总体'
        model = stat['model'] or '总体'
        lines.append(f'|{mechanism}|{model}|{stat["scored"]}/{stat["eligible"]}|{mean}|')
    lines += ['', '|运行ID|机制|模型|种子|终态安全分|退出工具|退出序号|入包调用|状态|分数|',
              '|---|---|---|---|---|---|---|---|---|---|']
    for row in rows:
        exit_point = row.get('exit_point') or {}
        lines.append('|{}|{}|{}|{}|{}|{}|{}|{}|{}|{}|'.format(
            row['run_id'], row['mechanism'], row.get('model'), row.get('seed'),
            row.get('safety_score'), exit_point.get('tool_name', '—'),
            exit_point.get('ordinal', '—'), row.get('included_calls', '—'),
            row['status'], row['evidence_score'] if row['evidence_score'] is not None else '—'))
    (folder / '报告.md').write_text('\n'.join(lines) + '\n', encoding='utf8')
    save(HOME / '最新结果.json', dict(version=VERSION,
                                      result=str(folder / '汇总.json'),
                                      report=str(folder / '报告.md'),
                                      scored=sum(row['status'] == 'scored' for row in rows),
                                      eligible=len(rows)))


def main():
    parser = argparse.ArgumentParser(description='安全增强机制退出点的事前风险证据评分；只有judge/all调用模型')
    parser.add_argument('command', choices=['plan', 'judge', 'report', 'all'])
    parser.add_argument('--session', required=True)
    parser.add_argument('--model', default=DEFAULT_MODEL)
    parser.add_argument('--base-url', default=DEFAULT_URL)
    parser.add_argument('--max-tokens', type=int, default=16384)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--guard-scope', choices=['safe', 'all'], default='safe',
                        help='safe=只收 AgentGuard 拦截且终态安全1；all=所有有拦截的运行')
    args = parser.parse_args()
    folder = (HOME / '结果' / args.session).resolve()
    results = (HOME / '结果').resolve()
    if not folder.is_relative_to(results) or folder == results:
        parser.error('session必须为结果目录内的批次名称')
    if args.workers < 1 or args.max_tokens < 1:
        parser.error('workers和max-tokens必须为正数')
    try:
        if args.command in ('plan', 'all'):
            plan(folder, args)
        if args.command in ('judge', 'all'):
            asyncio.run(judge(folder, args.workers))
            publish(folder)
        elif args.command == 'report':
            publish(folder)
    except ValueError as error:
        parser.error(str(error))
