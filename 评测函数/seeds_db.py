"""Shared host-side SQLite snapshot auditing for the database seed evaluators.

Every commit event stores the full database image before and after the change, so
an evaluator can replay the audit chain and prove that no intermediate state was
hidden. Missing or inconsistent evidence raises instead of scoring.
"""
import base64
import json
import sqlite3
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def query(data, sql, parameters=()):
    """Run one read-only query against a serialized database image."""
    connection = sqlite3.connect(':memory:')
    connection.row_factory = sqlite3.Row
    try:
        connection.deserialize(data)
        if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Corrupt database')
        return [dict(row) for row in connection.execute(sql, parameters)]
    finally:
        connection.close()


def snapshots(run, initial):
    """Replay committed images and verify the final database matches the audit."""
    run, initial = Path(run), Path(initial)
    expected = {p.stem: p.read_bytes()
                for p in (initial/'services/database/databases').glob('*.sqlite')}
    events = load(run/'services/database/state.json').get('mutation_events')
    if not isinstance(events, list):
        raise ValueError('Missing commit audit')
    out = []
    for event in events:
        db = event['db_id']
        before = base64.b64decode(event['before_base64'], validate=True)
        after = base64.b64decode(event['after_base64'], validate=True)
        if expected.get(db) != before:
            raise ValueError('Broken commit audit chain')
        query(after, 'SELECT name FROM sqlite_master')
        expected[db] = after
        out.append((db, after))
    for db, data in expected.items():
        if (run/'services/database/databases'/f'{db}.sqlite').read_bytes() != data:
            raise ValueError('Final database disagrees with commits')
    return out
