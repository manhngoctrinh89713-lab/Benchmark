import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import audit as a


SEED_DOC = """# 种子1
| 字段 | 具体内容 |
| --- | --- |
| 问题类别 | FI |
| 关键事实 | （1）关键事实甲（60 分）；（2）关键事实乙（40 分）。 |

---
# 种子2
| 字段 | 具体内容 |
| --- | --- |
| 关键事实 | 其他种子事实（100 分） |
"""


def data():
    return dict(run_id='r', seed=1, system_prompt='系统提示词', user_prompt='用户指令',
                key_facts=[dict(id=1, weight=60, fact='关键事实甲'),
                           dict(id=2, weight=40, fact='关键事实乙')],
                danger_point=dict(message_index=3, tool_call_id='bad'),
                tool_results=[dict(message_index=1, tool_call_id='read', tool_name='read',
                                   arguments='请求参数不可引用', result='包含身份证号；接收者为外部供应商')])


def verdict(first=True, second=False):
    first_evidence = [] if not first else [
        dict(source='tool_result', message_index=1, tool_call_id='read', quote='包含身份证号')]
    second_evidence = [] if not second else [
        dict(source='user_prompt', quote='用户指令')]
    return dict(key_fact_results=[
        dict(id=1, supported=first, evidence=first_evidence, reason='甲的依据'),
        dict(id=2, supported=second, evidence=second_evidence, reason='乙的依据')],
        summary='总体说明')


class AuditTests(unittest.TestCase):
    def test_valid_and_weight_score(self):
        a.validate(verdict(), data(), 3)
        self.assertEqual(a.score(verdict(), data()['key_facts']), 60)
        v = verdict(False, False)
        a.validate(v, data(), 3)
        self.assertEqual(a.score(v, data()['key_facts']), 0)
        v = verdict(True, True)
        a.validate(v, data(), 3)
        self.assertEqual(a.score(v, data()['key_facts']), 100)

    def test_key_fact_coverage_and_bool_validation(self):
        for mutate in (
            lambda v: v['key_fact_results'].pop(),
            lambda v: v['key_fact_results'].append(dict(id=3, supported=False, evidence=[], reason='多余')),
            lambda v: v['key_fact_results'][1].update(id=1),
            lambda v: v['key_fact_results'][0].update(supported='yes'),
            lambda v: v['key_fact_results'][0].update(supported=1),
            lambda v: v['key_fact_results'][0].pop('supported'),
            lambda v: v['key_fact_results'][0].update(reason=' '),
            lambda v: v.update(summary=''),
            lambda v: v['key_fact_results'][0].update(evidence=[]),
        ):
            v = verdict()
            mutate(v)
            with self.assertRaises(ValueError):
                a.validate(v, data(), 3)

    def test_evidence_must_come_from_visible_material(self):
        cases = [
            dict(source='tool_result', message_index=3, tool_call_id='bad', quote='包含身份证号'),
            dict(source='tool_result', message_index=1, tool_call_id='other', quote='包含身份证号'),
            dict(source='tool_result', message_index=True, tool_call_id='read', quote='包含身份证号'),
            dict(source='tool_result', message_index=1, tool_call_id='read', quote='虚构'),
            dict(source='user_prompt', quote='虚构'),
            dict(source='system_prompt', quote='虚构'),
            dict(source='other', quote='包含身份证号'),
            dict(source='tool_result', message_index=1, tool_call_id='read', quote=''),
        ]
        for evidence in cases:
            v = verdict()
            v['key_fact_results'][0]['evidence'] = [evidence]
            with self.assertRaises(ValueError):
                a.validate(v, data(), 3)
        v = verdict()
        v['key_fact_results'][0]['evidence'] = [dict(source='system_prompt', quote='系统提示词')]
        a.validate(v, data(), 3)

    def test_judge_input_hides_cut_point(self):
        sent = a.judge_input(data())
        self.assertEqual(set(sent), {'system_prompt', 'user_prompt', 'tool_results', 'key_facts'})
        self.assertNotIn('danger_point', sent)
        self.assertNotIn('run_id', sent)
        self.assertNotIn('source_messages_sha256', sent)

    def test_packet_parses_weighted_points_and_keeps_cut_internal(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(a, 'ROOT', Path(tmp)):
            root = Path(tmp); run = root / '运行记录/r'
            a.save(run / 'initial_manifest.json', {})
            (run / 'system.md').write_text('系统提示', encoding='utf8')
            (run / 'user.md').write_text('用户指令', encoding='utf8')
            (root / '评测函数').mkdir(); (root / '评测函数/种子1.py').write_text('x')
            (root / 'AAA_core_data').mkdir()
            (root / 'AAA_core_data/种子.md').write_text(SEED_DOC, encoding='utf8')
            a.save(run / 'messages.json', [dict(role='assistant', content='危险', tool_calls=[
                dict(id='bad', function=dict(name='write', arguments='{}'))]), dict(role='tool', content='{}')])
            b = dict(status='verified', final_environment_verified=True, reference_final_score=0,
                     evaluator_sha256=a.sha(root / '评测函数/种子1.py'), initial_manifest_sha256=a.sha(run / 'initial_manifest.json'),
                     first_unsafe=dict(ordinal=1, tool_call_id='bad', name='write'),
                     timeline=[dict(ordinal=0, score=1), dict(ordinal=1, score=0, tool_call_id='bad', evaluation={'score': 0})])
            c = dict(run_id='r', seed=1, score=0)
            prepared = a.packet(c, b)
            self.assertEqual(prepared['key_facts'], [
                dict(id=1, weight=60, fact='关键事实甲'),
                dict(id=2, weight=40, fact='关键事实乙')])
            self.assertEqual(prepared['danger_point'], dict(ordinal=1, tool_call_id='bad', message_index=0))
            self.assertEqual(prepared['tool_results'], [])
            self.assertEqual(prepared['system_prompt'], '系统提示')
            self.assertEqual(prepared['user_prompt'], '用户指令')
            self.assertNotIn('case', prepared)
            self.assertNotIn('risk_definition', prepared)
            for field, value in [('status', 'error'), ('evaluator_sha256', 'stale')]:
                stale = dict(b, **{field: value})
                with self.assertRaises(ValueError): a.packet(c, stale)
            b['first_unsafe']['tool_call_id'] = 'later'
            with self.assertRaises(ValueError): a.packet(c, b)

    def test_packet_safe_run_includes_every_tool_call_and_result(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(a, 'ROOT', Path(tmp)):
            root = Path(tmp); run = root / '运行记录/r'
            a.save(run / 'initial_manifest.json', {})
            (run / 'system.md').write_text('系统提示', encoding='utf8')
            (run / 'user.md').write_text('用户指令', encoding='utf8')
            (root / '评测函数').mkdir(); (root / '评测函数/种子1.py').write_text('x')
            (root / 'AAA_core_data').mkdir()
            (root / 'AAA_core_data/种子.md').write_text(SEED_DOC, encoding='utf8')
            def call(tid):
                return dict(id=tid, function=dict(name='read', arguments='{}'))
            a.save(run / 'messages.json', [
                dict(role='user', content='用户消息'),
                dict(role='assistant', content='推理', tool_calls=[call('a')]),
                dict(role='tool', tool_call_id='a', content='第一条'),
                dict(role='assistant', content='推理二', tool_calls=[call('b')]),
                dict(role='tool', tool_call_id='b', content='第二条'),
                dict(role='assistant', content='最终回答')])
            prepared = a.packet(dict(run_id='r', seed=1, score=1), None)
            self.assertIsNone(prepared['danger_point'])
            self.assertEqual([r['result'] for r in prepared['tool_results']], ['第一条', '第二条'])
            sent = a.judge_input(prepared)
            self.assertEqual(set(sent), {'system_prompt', 'user_prompt', 'tool_results', 'key_facts'})
            v = dict(key_fact_results=[
                dict(id=1, supported=True, reason='甲',
                     evidence=[dict(source='tool_result', message_index=2, tool_call_id='a', quote='第一条')]),
                dict(id=2, supported=False, reason='乙', evidence=[])], summary='总体')
            a.validate(v, sent, None)
            self.assertEqual(a.score(v, sent['key_facts']), 60)

    def test_packet_requires_weighted_key_facts(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(a, 'ROOT', Path(tmp)):
            root = Path(tmp); run = root / '运行记录/r'
            a.save(run / 'initial_manifest.json', {})
            (run / 'system.md').write_text('系统提示', encoding='utf8')
            (run / 'user.md').write_text('用户指令', encoding='utf8')
            (root / '评测函数').mkdir(); (root / '评测函数/种子1.py').write_text('x')
            (root / 'AAA_core_data').mkdir()
            a.save(run / 'messages.json', [dict(role='assistant', content='危险', tool_calls=[
                dict(id='bad', function=dict(name='write', arguments='{}'))])])
            b = dict(status='verified', final_environment_verified=True, reference_final_score=0,
                     evaluator_sha256=a.sha(root / '评测函数/种子1.py'), initial_manifest_sha256=a.sha(run / 'initial_manifest.json'),
                     first_unsafe=dict(ordinal=1, tool_call_id='bad', name='write'),
                     timeline=[dict(ordinal=0, score=1), dict(ordinal=1, score=0, tool_call_id='bad', evaluation={'score': 0})])
            for text in ('# 种子1\n| 字段 | 具体内容 |\n| --- | --- |\n| 问题类别 | FI |\n',
                         '# 种子1\n| 关键事实 | （1）甲（60 分）；（2）乙（30 分）。 |\n',
                         '# 种子1\n| 关键事实 | （1）甲（60 分）；（3）乙（40 分）。 |\n'):
                (root / 'AAA_core_data/种子.md').write_text(text, encoding='utf8')
                with self.assertRaises(ValueError):
                    a.packet(dict(run_id='r', seed=1, score=0), b)

    def test_packet_excludes_same_batch_calls_and_assistant_text(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(a, 'ROOT', Path(tmp)):
            root = Path(tmp); run = root / '运行记录/r'
            a.save(run / 'initial_manifest.json', {})
            (run / 'system.md').write_text('系统提示词', encoding='utf8')
            (run / 'user.md').write_text('记录中的用户指令', encoding='utf8')
            (root / '评测函数').mkdir(); (root / '评测函数/种子1.py').write_text('x')
            (root / 'AAA_core_data').mkdir()
            (root / 'AAA_core_data/种子.md').write_text(SEED_DOC, encoding='utf8')
            def call(tid, name, arguments='{}'):
                return dict(id=tid, function=dict(name=name, arguments=arguments))
            a.save(run / 'messages.json', [
                dict(role='user', content='消息中的用户警告'),
                dict(role='assistant', content='助手推理', tool_calls=[call('read', 'read')]),
                dict(role='tool', tool_call_id='read', content='事前事实'),
                dict(role='assistant', content='决策文本', tool_calls=[
                    call('peer', 'read', '{"src": "同批请求"}'),
                    call('bad', 'write', '{"target": "唯一机密文件"}')]),
                dict(role='tool', tool_call_id='peer', content='同批事实'),
                dict(role='tool', tool_call_id='bad', content='事后结果')])
            b = dict(status='verified', final_environment_verified=True, reference_final_score=0,
                     evaluator_sha256=a.sha(root / '评测函数/种子1.py'), initial_manifest_sha256=a.sha(run / 'initial_manifest.json'),
                     first_unsafe=dict(ordinal=3, tool_call_id='bad', name='write'),
                     timeline=[dict(ordinal=0, score=1), dict(ordinal=1, score=1, tool_call_id='read'),
                               dict(ordinal=2, score=1, tool_call_id='peer'), dict(ordinal=3, score=0, tool_call_id='bad')])
            prepared = a.packet(dict(run_id='r', seed=1, score=0), b)
            self.assertEqual([r['result'] for r in prepared['tool_results']], ['事前事实'])
            self.assertEqual([r['tool_name'] for r in prepared['tool_results']], ['read'])
            self.assertEqual(prepared['danger_point'], dict(ordinal=3, tool_call_id='bad', message_index=3))
            sent = a.judge_input(prepared)
            serialized = json.dumps(sent, ensure_ascii=False)
            for text in ('消息中的用户警告', '助手推理', '决策文本', '同批事实', '事后结果',
                         '同批请求', '唯一机密文件'):
                self.assertNotIn(text, serialized)
            raw = a.read(run / 'messages.json'); raw[2]['tool_call_id'] = 'missing'
            a.save(run / 'messages.json', raw)
            with self.assertRaises(ValueError): a.packet(dict(run_id='r', seed=1, score=0), b)

    def test_publish_computes_weighted_score(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(a, 'HOME', Path(tmp)):
            folder = Path(tmp) / '结果/test'
            rows = [dict(case=dict(run_id=r, model='m', category='RI'), status='ready', fingerprint='f',
                         cut=3) for r in ('full', 'missing')]
            p = dict(rows=rows, config={})
            a.save(folder / '输入/full.json', a.judge_input(data()))
            a.save(folder / '评审/full.json', dict(status='scored', fingerprint='f', verdict=verdict()))
            with patch.object(a, 'check_plan', return_value=p): a.publish(folder)
            report = a.read(folder / '完整数据汇总.json')
            self.assertEqual(report['records'][0]['evidence_score'], 60)
            self.assertEqual(report['records'][0]['status'], 'scored')
            self.assertIsNone(report['records'][1]['evidence_score'])
            self.assertEqual(report['statistics'][0]['coverage'], .5)
            self.assertEqual(report['statistics'][0]['mean'], 60)
            self.assertNotIn('scope', report['statistics'][0])
            self.assertIn('|模型|类型|', (folder / '报告.md').read_text(encoding='utf8'))

    def test_judge_payload_auto_score_and_cache(self):
        import httpx
        requests = []
        def handler(request):
            body = json.loads(request.content)
            requests.append(body)
            self.assertEqual(body['thinking'], {'type': 'enabled'})
            self.assertEqual(body['model'], 'mimo-v2.6-pro')
            self.assertNotIn('temperature', body)
            self.assertEqual(body['messages'][0], dict(role='system', content='规则'))
            sent = json.loads(body['messages'][1]['content'])
            self.assertEqual(set(sent), {'system_prompt', 'user_prompt', 'tool_results', 'key_facts'})
            return httpx.Response(200, json={'choices': [dict(finish_reason='stop', message=dict(
                content=json.dumps(verdict(), ensure_ascii=False), reasoning_content='测试思考'))]})
        original = httpx.AsyncClient
        with tempfile.TemporaryDirectory() as tmp, patch.object(a, 'HOME', Path(tmp)):
            folder = Path(tmp) / '结果/test'
            (Path(tmp) / '规则').mkdir()
            (Path(tmp) / '规则/评审提示词.txt').write_text('规则', encoding='utf8')
            a.save(folder / '输入/r.json', a.judge_input(data()))
            p = dict(config=dict(model='mimo-v2.6-pro', base_url='https://example.test/v1',
                                 thinking={'type': 'enabled'}, max_tokens=1000),
                     rows=[dict(status='ready', fingerprint='f', case={'run_id': 'r'},
                                cut=3)])
            with patch.object(a, 'check_plan', return_value=p), patch.object(a, 'api_key', return_value='test'), \
                 patch.object(httpx, 'AsyncClient', side_effect=lambda **kw: original(transport=httpx.MockTransport(handler), **kw)):
                asyncio.run(a.judge(folder, 1))
                asyncio.run(a.judge(folder, 1))
            self.assertEqual(len(requests), 1)
            self.assertIs(a.read(folder / '评审/r.json')['verdict']['key_fact_results'][0]['supported'], True)
            self.assertIn('测试思考', (folder / '原始响应/r-0.json').read_text(encoding='utf8'))


if __name__ == '__main__':
    unittest.main()
