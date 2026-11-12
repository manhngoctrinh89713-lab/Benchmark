import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from run_selection import scan


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.put('prompt/cases/种子1/config.json', {'groups': ['files'], 'variants': {
            'ru_test': {'instruction_type': 'test', 'user_prompt': 'test.md'}}})
        self.text('prompt/cases/种子1/test.md', 'test')
        self.text('初始环境/种子1/workspace/a.txt', 'initial')
        self.fingerprint = {'workspace/a.txt': hashlib.sha256(b'initial').hexdigest()}

    def text(self, name, value):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(value, encoding='utf8')

    def put(self, name, value):
        self.text(name, json.dumps(value))

    def run_record(self, name, time, score=0, **changes):
        meta = dict(case='种子1', variant='ru_test', model='m', groups=['files'],
                    status='completed', started_at=time)
        meta.update(changes)
        self.put(f'运行记录/{name}/run.json', meta)
        self.put(f'运行记录/{name}/initial_manifest.json', self.fingerprint)
        self.put(f'运行记录/{name}/evaluation.json', dict(score=score))
        self.put(f'运行记录/{name}/messages.json', [])
        self.text(f'运行记录/{name}/user.md', 'test')

    def test_newest_valid_not_newest_invalid(self):
        self.run_record('old', '1')
        self.run_record('new', '2')
        self.run_record('incomplete', '3', status='failed')
        cells, rejected = scan(self.root)
        self.assertEqual([c['run_id'] for c in cells if c['run_id']], ['new'])
        self.assertIn(dict(run_id='old', reason='superseded'), rejected)
        self.assertTrue(any(r['run_id'] == 'incomplete' for r in rejected))

    def test_security_enhanced_runs_never_selected(self):
        self.run_record('normal', '1')
        self.run_record('reminder', '2', method='targeted_reminder', targeted_reminder_enabled=True)
        self.run_record('enhanced-only', '3', model='g', method='specified_quit', specified_quit={'triggered': False})
        self.run_record('secret-guard', '4', model='q', agentguard_enabled=True)
        cells, rejected = scan(self.root)
        selected = {c['model']: c for c in cells}
        self.assertEqual(selected['m']['run_id'], 'normal')
        self.assertIsNone(selected['g']['run_id'])
        self.assertIsNone(selected['q']['run_id'])
        reasons = {r['run_id']: r['reason'] for r in rejected}
        for name in ('reminder', 'enhanced-only', 'secret-guard'):
            self.assertIn('security_enhanced', reasons[name])

    def test_seed_requires_exactly_one_test_variant(self):
        self.put('prompt/cases/种子1/config.json', {'groups': ['files'], 'variants': {
            'ru_test': {'instruction_type': 'test', 'user_prompt': 'test.md'},
            'ri_test': {'instruction_type': 'test', 'user_prompt': 'test.md'}}})
        with self.assertRaises(ValueError):
            scan(self.root)

    def test_legacy_guard_batch_excluded_unless_flags_are_explicit(self):
        self.run_record('guarded', '1', batch_id='b')
        self.put('运行记录/guarded/messages.json', [dict(role='tool', content='{"agentguard": "blocked"}')])
        self.run_record('sibling', '2', batch_id='b')
        self.run_record('safe-batch', '3', batch_id='c')
        self.run_record('explicit', '4', batch_id='b', method='normal', agentguard_enabled=False)
        cells, rejected = scan(self.root)
        self.assertEqual([c['run_id'] for c in cells if c['run_id']], ['explicit'])
        reasons = {r['run_id']: r['reason'] for r in rejected}
        self.assertIn('security_enhanced', reasons['guarded'])
        self.assertIn('security_enhanced', reasons['sibling'])
        self.assertIn(dict(run_id='safe-batch', reason='superseded'), rejected)

    def test_old_prompt_or_environment_not_selected(self):
        self.run_record('valid', '1')
        self.run_record('old-prompt', '2')
        self.text('运行记录/old-prompt/user.md', 'obsolete')
        self.run_record('old-environment', '3')
        self.put('运行记录/old-environment/initial_manifest.json', {'workspace/a.txt': 'wrong'})
        cells, rejected = scan(self.root)
        self.assertEqual([c['run_id'] for c in cells if c['run_id']], ['valid'])
        self.assertEqual(len(rejected), 2)

    def test_safe_runs_included_and_missing_slots_preserved(self):
        self.run_record('safe', '1', score=1)
        self.run_record('enhanced-only', '2', model='g', method='specified_quit')
        cells, _ = scan(self.root)
        self.assertEqual(next(c for c in cells if c['run_id'])['score'], 1)
        self.assertEqual(len([c for c in cells if c['run_id'] is None]), 1)

    def test_audit_states_cannot_change_selection(self):
        self.run_record('r', '1')
        before = scan(self.root)
        for audit in ['危险意识', '事前风险证据', '危险操作起始点']:
            self.put(f'审计/{audit}/工作区/状态.json', dict(records=[{'run_id': 'r'}]))
        self.assertEqual(scan(self.root), before)
        cell = next(c for c in before[0] if c['run_id'])
        self.assertEqual(set(cell), {'seed', 'category', 'model', 'run_id', 'score',
                                     'started_at', 'evaluation_file'})


if __name__ == '__main__':
    unittest.main()
