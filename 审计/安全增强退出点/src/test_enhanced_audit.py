import json
import os
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

import enhanced_audit as a

WORKSPACE = Path(__file__).resolve().parents[3]


def call(cid, name='tool'):
    return dict(id=cid, function=dict(name=name, arguments='{}'))


def run_messages():
    """一条含 AgentGuard 拦截的轨迹：第 3 个调用被拦截。"""
    return [
        dict(role='assistant', tool_calls=[call('c1')]),
        dict(role='tool', tool_call_id='c1', content='返回一'),
        dict(role='assistant', tool_calls=[call('c2'), call('c3')]),
        dict(role='tool', tool_call_id='c2', content='返回二'),
        dict(role='tool', tool_call_id='c3', content={'agentguard': 'blocked', 'reason': '无授权'}),
        dict(role='assistant', tool_calls=[call('c4')]),
        dict(role='tool', tool_call_id='c4', content='退出后的返回'),
    ]


class EnhancedAuditTests(unittest.TestCase):
    def setUp(self):
        self.root = WORKSPACE / 'tmp' / f'_unittest_enhanced_{os.getpid()}'
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)

    def tearDown(self):
        if self.root.exists():
            shutil.rmtree(self.root, ignore_errors=True)

    def test_guard_block_detects_nested_json_string(self):
        value = {'content': [{'type': 'text',
                              'text': json.dumps({'agentguard': 'blocked', 'reason': 'x'})}]}
        self.assertEqual(a._guard_block(value)['reason'], 'x')
        self.assertIsNone(a._guard_block({'content': '普通返回'}))
        self.assertIsNone(a._guard_block({'agentguard': 'allow'}))

    def test_flatten_marks_results_and_ordinals(self):
        calls = a._flatten(run_messages())
        self.assertEqual([c['ordinal'] for c in calls], [1, 2, 3, 4])
        self.assertEqual([c['result_index'] for c in calls], [1, 3, 4, 6])

    def _write_run(self, messages):
        run = self.root / '运行记录' / 'r'
        a.save(run / 'messages.json', messages)
        (run / 'system.md').write_text('系统提示', encoding='utf8')
        (run / 'user.md').write_text('用户指令', encoding='utf8')

    def test_packet_guard_keeps_only_completed_prefix(self):
        with patch.object(a, 'ROOT', self.root), \
                patch.object(a, 'key_facts', lambda seed: [dict(id=1, weight=100, fact='事实')]):
            self._write_run(run_messages())
            meta = dict(run_id='r', case='种子1', model='m', category='RI',
                        safety_score=1, mechanism='agentguard')
            data = a.packet(meta)
            self.assertEqual([r['tool_call_id'] for r in data['tool_results']], ['c1', 'c2'])
            self.assertEqual(data['exit_point']['ordinal'], 3)
            self.assertEqual(data['exit_point']['tool_name'], 'tool')
            self.assertEqual(data['cut'], 4)
            self.assertNotIn('blocked', json.dumps(data['tool_results'], ensure_ascii=False))

    def test_packet_quit_cuts_at_tool_calls_before(self):
        messages = [
            dict(role='assistant', tool_calls=[call('c1')]),
            dict(role='tool', tool_call_id='c1', content='返回一'),
            dict(role='assistant', tool_calls=[call('c2')]),
            dict(role='tool', tool_call_id='c2', content='返回二'),
            dict(role='assistant', tool_calls=[call('quit', 'quit')]),
        ]
        with patch.object(a, 'ROOT', self.root), \
                patch.object(a, 'key_facts', lambda seed: [dict(id=1, weight=100, fact='事实')]):
            self._write_run(messages)
            meta = dict(run_id='r', case='种子1', model='m', category='RI', safety_score=1,
                        mechanism='specified_quit', termination_reason='specified_quit',
                        specified_quit=dict(triggered=True, tool_calls_before=2, step=3))
            data = a.packet(meta)
            self.assertEqual([r['tool_call_id'] for r in data['tool_results']], ['c1', 'c2'])
            self.assertEqual(data['exit_point']['ordinal'], 3)
            self.assertEqual(data['exit_point']['tool_name'], 'quit')
            self.assertEqual(data['cut'], 5)

    def test_judge_input_hides_mechanism_and_exit(self):
        data = dict(system_prompt='s', user_prompt='u', key_facts=[], tool_results=[],
                    run_id='r', exit_point=dict(mechanism='agentguard'), cut=1,
                    mechanism='agentguard', safety_score=1)
        sent = a.judge_input(data)
        self.assertEqual(set(sent), {'system_prompt', 'user_prompt', 'tool_results', 'key_facts'})


if __name__ == '__main__':
    unittest.main()
