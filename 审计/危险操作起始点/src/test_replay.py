import json
from pathlib import Path
import tempfile
import unittest

from replay import canonical, environment_diff, first_unsafe, latest_index, work_directory


class ReplayTests(unittest.TestCase):
    def test_first_failure_is_preserved_even_if_state_recovers(self):
        rows = [dict(ordinal=i, score=s, tool_call_id=f'call{i}', name='test')
                for i, s in enumerate([1, 1, 0, 1, 0])]
        self.assertEqual(first_unsafe(rows)['tool_call_id'], 'call2')

    def test_initial_violation_cannot_be_attributed_to_first_call(self):
        with self.assertRaises(ValueError):
            first_unsafe([dict(ordinal=0, score=0)])

    def test_safe_trajectory_including_zero_calls(self):
        self.assertIsNone(first_unsafe([dict(ordinal=0, score=1)]))

    def test_output_comparison_does_not_hide_dynamic_values(self):
        self.assertEqual(canonical({'text': '{"id":"a", "x":1}'}),
                         canonical({'text': '{"x":1,"id":"a"}'}))
        self.assertNotEqual(canonical({'id': 'a', 'time': '1'}),
                            canonical({'id': 'a', 'time': '2'}))
        self.assertNotEqual(canonical({'content': [], 'isError': False}),
                            canonical({'content': [], 'isError': True}))

    def test_final_environment_checks_hidden_state_and_missing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / 'old', Path(tmp) / 'new'
            a.mkdir(); b.mkdir()
            (a / 'state.json').write_text('{"x":1,"y":2}', encoding='utf8')
            (b / 'state.json').write_text('{"y":2, "x":1}', encoding='utf8')
            self.assertEqual(environment_diff(a, b), [])
            (b / 'state.json').write_text(json.dumps(dict(x=1, y=3)), encoding='utf8')
            (b / 'extra.txt').write_text('x', encoding='utf8')
            self.assertEqual(environment_diff(a, b), ['extra.txt', 'state.json'])

    def test_latest_index_records_counts_and_errors(self):
        folder = Path('D:/batch')
        ok = latest_index(folder, [dict(status='verified'), dict(status='no_unsafe_action'),
                                   dict(status='verified')])
        self.assertEqual(ok['status'], 'completed')
        self.assertEqual(ok['total'], 3)
        self.assertEqual(ok['counts'], {'no_unsafe_action': 1, 'verified': 2})
        self.assertEqual(ok['summary'], str(folder / '汇总.json'))
        partial = latest_index(folder, [dict(status='verified'), dict(status='error')])
        self.assertEqual(partial['status'], 'partial')
        self.assertEqual(partial['counts'], {'error': 1, 'verified': 1})

    def test_work_directory_supports_nested_writes_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            with work_directory(Path(tmp)) as path:
                (path / 'nested').mkdir()
                (path / 'nested' / 'x.txt').write_text('x', encoding='utf8')
                self.assertTrue((path / 'nested' / 'x.txt').is_file())
            self.assertFalse(path.exists())


if __name__ == '__main__':
    unittest.main()
