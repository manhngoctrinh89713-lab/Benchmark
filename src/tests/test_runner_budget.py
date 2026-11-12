import argparse
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
from harness import runner


class BudgetEvaluationTests(unittest.TestCase):
    def test_budget_stop_scores_mutations_from_saved_environment(self):
        run_id = 'test-budget-' + uuid4().hex
        args = argparse.Namespace(model='deepseek-flash', endpoint=None, case='种子44',
            groups=None, user=None, variant='ri_test', max_tool_calls=1, max_steps=2,
            no_proxy=True, api_retries=0, dry_run=False, reset_only=False,
            batch_id=None, run_id=run_id)
        calls = [dict(id='move', type='function', function=dict(name='files__move_file',
            arguments=json.dumps(dict(source='交付归档/2021', destination='交付归档/历年/2021')))),
            dict(id='list', type='function', function=dict(name='files__directory_tree', arguments='{}'))]
        response = httpx.Response(200, request=httpx.Request('POST', 'https://example.test'),
            json=dict(choices=[dict(finish_reason='tool_calls', message=dict(role='assistant', content='', tool_calls=calls))]))
        with patch.object(runner, 'api_key', return_value='test'), patch.object(runner, 'request_model', new=AsyncMock(return_value=response)):
            with self.assertRaises(Exception) as raised:
                asyncio.run(runner.execute_locked(args))
            self.assertIn('最大工具调用次数', runner.describe_error(raised.exception))
        record = runner.ROOT / '运行记录' / run_id
        meta = json.loads((record / 'run.json').read_text(encoding='utf-8'))
        self.assertEqual(meta['status'], 'failed')
        self.assertEqual(meta['termination_reason'], 'max_tool_calls')
        self.assertEqual(meta['tool_calls'], 1)
        self.assertEqual(meta['max_steps'], 2)
        self.assertEqual(meta['max_tool_calls'], 1)
        self.assertEqual(meta['budget_scope'], 'per_agent')
        self.assertEqual(meta['safety_score'], 0)
        self.assertTrue((record / 'final_environment/workspace/交付归档/历年/2021').is_dir())
