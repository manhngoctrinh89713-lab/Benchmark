import base64
from email.message import EmailMessage
import json
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
import zipfile
import sqlite3
import zlib
from contextlib import closing

from semantic import Comparison, sqlite_value, mime_value, xlsx_value, now_insert_columns
from openpyxl import Workbook


class SemanticTests(unittest.TestCase):
    def database(self, timestamp, amount=10, fixed='2020-01-01T00:00:00', version='0012'):
        with closing(sqlite3.connect(':memory:')) as conn:
            conn.executescript('CREATE TABLE schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT); CREATE TABLE orders(id INTEGER PRIMARY KEY, amount INTEGER);')
            conn.executemany('INSERT INTO schema_migrations VALUES(?,?)', [('0011',fixed),(version,timestamp)])
            conn.execute('INSERT INTO orders VALUES(1,?)', (amount,));conn.commit()
            return conn.serialize()

    def enable_now(self, c):
        c.prepare_call('database__execute_transaction', {'db_id':'orders-prod','statements':[
            {'sql':"INSERT INTO schema_migrations(version,applied_at) VALUES('0012',datetime('now','localtime'))"}]})

    def test_sql_clock_scope_preserves_amount_fixed_time_and_version(self):
        a=self.database('2026-11-04T10:00:00');b=self.database('2026-11-06T10:00:00')
        self.assertEqual(sqlite_value(a,{'0012'}),sqlite_value(b,{'0012'}))
        self.assertNotEqual(sqlite_value(a,set()),sqlite_value(b,set()))
        for bad in [self.database('2026-11-06T10:00:00',amount=20),
                    self.database('2026-11-06T10:00:00',fixed='2021-01-01T00:00:00'),
                    self.database('2026-11-06T10:00:00',version='WRONG')]:
            self.assertNotEqual(sqlite_value(a,{'0012'}),sqlite_value(bad,{'0012'}))
        with self.assertRaises(ValueError):sqlite_value(self.database('not a time'),{'0012'})

    def test_sql_now_insert_columns_are_normalized(self):
        def db(start, result='ok'):
            with closing(sqlite3.connect(':memory:')) as conn:
                conn.execute('CREATE TABLE batch_runs(id TEXT, started_at TEXT, result TEXT)')
                conn.execute('INSERT INTO batch_runs VALUES(?,?,?)', ('QA', start, result))
                conn.commit(); return conn.serialize()
        dynamic = now_insert_columns([{'sql': "INSERT INTO batch_runs (id, started_at, result) "
                                                 "VALUES ('QA', datetime('now'), 'ok')"}])
        self.assertEqual(dynamic, {'batch_runs': {'started_at'}})
        a, b = db('2026-11-08 03:53:00'), db('2026-11-10 13:42:12')
        self.assertEqual(sqlite_value(a, set(), dynamic), sqlite_value(b, set(), dynamic))
        self.assertNotEqual(sqlite_value(a, set(), dynamic), sqlite_value(db('2026-11-10 13:42:12', 'wrong'), set(), dynamic))

    def test_only_now_insert_enables_migration_clock_normalization(self):
        c=self.comparison()
        c.prepare_call('database__execute_transaction', {'db_id':'d','statements':[
            {'sql':"INSERT INTO schema_migrations(version,applied_at) VALUES('x','2020-01-01')"}]})
        self.assertEqual(c.migration_versions,{})
        c.prepare_call('database__execute_transaction', {'db_id':'d','statements':[
            {'sql':"INSERT INTO schema_migrations(version, applied_at) VALUES ('0012', strftime('%Y-%m-%dT%H:%M:%S+08:00','now','+8 hours'))"}]})
        self.assertEqual(c.migration_versions,{'d':{'0012'}})

    def test_sql_read_time_only_normalized_for_approved_query_and_rows(self):
        c=self.comparison();self.enable_now(c)
        def response(time):return {'content':[{'text':json.dumps({'columns':['version','applied_at'],'rows':[['0012',time]]})}]}
        c.prepare_call('database__read_query',{'db_id':'orders-prod','sql':'SELECT version, applied_at FROM schema_migrations'})
        self.assertTrue(c.tool_equal('database__read_query',response('2020-01-01'),response('2026-01-01')))
        c.prepare_call('database__read_query',{'db_id':'orders-prod','sql':'SELECT version, applied_at FROM important_events'})
        self.assertFalse(c.tool_equal('database__read_query',response('2020-01-01'),response('2026-01-01')))

    def test_database_hash_snapshot_and_final_file_agree_semantically(self):
        a,b=self.database('2020-01-01'),self.database('2026-01-01')
        def state(raw):return {'mutation_events':[{'sequence':2,'db_id':'orders-prod','snapshot_encoding':'zlib',
            'before_base64':base64.b64encode(zlib.compress(raw)).decode(),'after_base64':base64.b64encode(zlib.compress(raw)).decode()}]}
        def response(raw):return {'content':[{'text':json.dumps({'sequence':2,'sha256':hashlib.sha256(raw).hexdigest()})}]}
        with tempfile.TemporaryDirectory() as tmp:
            ref,env=Path(tmp)/'ref',Path(tmp)/'env'
            for p,raw in [(ref,a),(env,b)]:
                (p/'services/database/databases').mkdir(parents=True)
                (p/'services/database/databases/orders-prod.sqlite').write_bytes(raw)
                (p/'services/database/state.json').write_text(json.dumps(state(raw)),encoding='utf8')
            c=Comparison(ref,env,ref);self.enable_now(c)
            forged=response(b)
            payload=json.loads(forged['content'][0]['text']);payload['sha256']='f'*64
            forged['content'][0]['text']=json.dumps(payload)
            self.assertFalse(c.tool_equal('database__execute_transaction',response(a),forged))
            self.assertTrue(c.tool_equal('database__execute_transaction',response(a),response(b)))
            c.aliases.clear()
            c.prepare_call('database__execute_schema',{'db_id':'orders-prod','sql':'CREATE INDEX idx ON orders(amount)'})
            self.assertTrue(c.tool_equal('database__execute_schema',response(a),response(b)))
            self.assertEqual(c.environment_diff(ref,env)[0],[])
            bad=self.database('2026-01-01',amount=20)
            (env/'services/database/databases/orders-prod.sqlite').write_bytes(bad)
            (env/'services/database/state.json').write_text(json.dumps(state(bad)),encoding='utf8')
            c=Comparison(ref,env,ref);self.enable_now(c)
            self.assertFalse(c.tool_equal('database__execute_transaction',response(a),response(bad)))
            self.assertTrue(c.environment_diff(ref,env)[0])

    def comparison(self):
        return Comparison('D:/original', 'D:/replay', Path('D:/reference'))

    def test_mtime_only_is_not_a_business_difference(self):
        c = self.comparison()
        a = {'content': [{'text': '{"size":10,"sha256":"same","modified_ns":1}'}]}
        b = {'content': [{'text': '{"size":10,"sha256":"same","modified_ns":2}'}]}
        self.assertTrue(c.tool_equal('files__get_file_info', a, b))
        self.assertTrue(c.tool_equal('files__search_files', a, b))
        b['content'][0]['text'] = '{"size":11,"sha256":"changed","modified_ns":2}'
        self.assertFalse(c.tool_equal('files__get_file_info', a, b))
        self.assertFalse(c.tool_equal('files__search_files', a, b))

    def test_generated_ids_are_mapped_but_message_content_stays_checked(self):
        c = self.comparison()
        old, new = 'msg_'+'a'*32, 'msg_'+'b'*32
        self.assertTrue(c.tool_equal('chat__send_message', {'id': old, 'text': 'x'}, {'id': new, 'text': 'x'}))
        self.assertEqual(c.arguments({'quote_message_id': old}), {'quote_message_id': new})
        self.assertFalse(c.tool_equal('chat__send_message', {'id': old, 'text': 'x'}, {'id': new, 'text': 'wrong'}))
        old_msg, new_msg = 'message_'+'c'*32, 'message_'+'d'*32
        old_att, new_att = 'attachment_'+'e'*32, 'attachment_'+'f'*32
        a = {'id': old_msg, 'attachments': [{'id': old_att}]}
        b = {'id': new_msg, 'attachments': [{'id': new_att}]}
        self.assertTrue(c.tool_equal('chat__send_file', a, b))
        self.assertEqual(c.arguments({'quote_message_id': old_msg, 'attachment_id': old_att}),
                         {'quote_message_id': new_msg, 'attachment_id': new_att})
        self.assertFalse(c.tool_equal('chat__send_file', a, dict(b, text='changed')))
        old_event, new_event = 'event_'+'1'*32, 'event_'+'2'*32
        self.assertTrue(c.tool_equal('chat__send_message', {'id': old_event}, {'id': new_event}))
        self.assertTrue(c.tool_equal('chat__get_chat', {'chat': {'last_message': {'id': old_msg}}},
                                                      {'chat': {'last_message': {'id': new_msg}}}))

    def test_mail_generated_ids_are_mapped_but_business_content_is_checked(self):
        c = self.comparison()
        old = dict(email_id='mail-' + 'a' * 32,
                   message_id='<message-' + 'c' * 32 + '@mail.local>',
                   submission_id='submission-' + 'e' * 32, status='accepted')
        new = dict(email_id='mail-' + 'b' * 32,
                   message_id='<message-' + 'd' * 32 + '@mail.local>',
                   submission_id='submission-' + 'f' * 32, status='accepted')
        wrapped = lambda body: {'content': [{'text': json.dumps(body)}]}
        self.assertTrue(c.tool_equal('mail__send_email', wrapped(old), wrapped(new)))
        self.assertEqual(c.arguments({'email_id': old['email_id'], 'message_id': old['message_id']}),
                         {'email_id': new['email_id'], 'message_id': new['message_id']})
        self.assertFalse(c.tool_equal('mail__send_email', wrapped(old), wrapped(dict(new, status='failed'))))
        self.assertFalse(self.comparison().tool_equal('mail__read_email', {'id': 'mail-fixed'},
                                                      {'id': 'mail-other'}))

    def test_mail_thread_and_event_ids_are_mapped_in_state(self):
        c = self.comparison()
        old_thread, new_thread = 'thread-' + '1' * 32, 'thread-' + '2' * 32
        old_event, new_event = 'event-' + '3' * 32, 'event-' + '4' * 32
        a = {'threads': [{'id': old_thread}], 'events': [{'id': old_event, 'thread_id': old_thread}]}
        b = {'threads': [{'id': new_thread}], 'events': [{'id': new_event, 'thread_id': new_thread}]}
        x, y = c.align_state(a, b)
        self.assertEqual(x, y)

    def test_mail_message_id_header_is_not_a_business_difference(self):
        def message(mid):
            return (f"From: a@b\nTo: c@d\nSubject: s\nMessage-ID: <{mid}>\n\nbody\n").encode()
        self.assertEqual(mime_value(message('<message-' + 'a' * 32 + '@mail.local>')),
                         mime_value(message('<message-' + 'b' * 32 + '@mail.local>')))

    def test_files_archive_compares_member_bytes_and_ignores_timestamps(self):
        def archive(year):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w') as z:
                z.writestr(zipfile.ZipInfo('a.txt', (year, 1, 1, 0, 0, 0)), b'x')
            return stream.getvalue()
        with tempfile.TemporaryDirectory() as temp:
            ref, env = Path(temp)/'ref', Path(temp)/'env'
            (ref/'workspace').mkdir(parents=True); (env/'workspace').mkdir(parents=True)
            old, new = archive(2020), archive(2021)
            (ref/'workspace'/'b.zip').write_bytes(old); (env/'workspace'/'b.zip').write_bytes(new)
            c = Comparison(ref, env, ref)
            a = {'content': [{'text': {'path': 'b.zip', 'size': len(old), 'sha256': hashlib.sha256(old).hexdigest()}}]}
            b = {'content': [{'text': {'path': 'b.zip', 'size': len(new), 'sha256': hashlib.sha256(new).hexdigest()}}]}
            self.assertTrue(c.tool_equal('files__create_archive', a, b))

    def test_database_now_output_columns_are_normalized(self):
        c = self.comparison()
        c.prepare_call('database__read_query', {'db_id': 'wms', 'sql': "SELECT datetime('now') AS utc_now, COUNT(*) AS n FROM orders"})
        a = {'content': [{'text': {'columns': ['utc_now', 'n'], 'rows': [['2026-11-08 03:53:00', 2]]}}]}
        b = {'content': [{'text': {'columns': ['utc_now', 'n'], 'rows': [['2026-11-10 13:42:12', 2]]}}]}
        self.assertTrue(c.tool_equal('database__read_query', a, b))
        b['content'][0]['text']['rows'][0][1] = 3
        self.assertFalse(c.tool_equal('database__read_query', a, b))

    def test_spreadsheet_read_compares_cells_not_container_hash(self):
        c = self.comparison()
        a = {'content': [{'text': {'path': 'x.xlsx', 'sha256': 'old', 'cells': [{'cell': 'A1', 'value': 1}]}}]}
        b = {'content': [{'text': {'path': 'x.xlsx', 'sha256': 'new', 'cells': [{'cell': 'A1', 'value': 1}]}}]}
        self.assertTrue(c.tool_equal('files__read_spreadsheet', a, b))
        b['content'][0]['text']['cells'][0]['value'] = 2
        self.assertFalse(c.tool_equal('files__read_spreadsheet', a, b))

    def test_spreadsheet_values_ignore_zip_container_timestamps(self):
        def raw(value=42):
            wb = Workbook(); ws = wb.active; ws['A1'] = 'x'; ws['B2'] = value
            stream = io.BytesIO(); wb.save(stream); return stream.getvalue()
        def rezip(data, year):
            source = zipfile.ZipFile(io.BytesIO(data)); out = io.BytesIO()
            with zipfile.ZipFile(out, 'w') as target:
                for info in source.infolist():
                    target.writestr(zipfile.ZipInfo(info.filename, (year, 1, 1, 0, 0, 0)),
                                    source.read(info.filename))
            return out.getvalue()
        a = raw(); b = rezip(a, 2020)
        self.assertNotEqual(a, b)
        self.assertEqual(xlsx_value(a), xlsx_value(b))
        with tempfile.TemporaryDirectory() as temp:
            ref, env = Path(temp)/'ref', Path(temp)/'env'
            ref.mkdir(); env.mkdir()
            (ref/'sales.xlsx').write_bytes(a); (env/'sales.xlsx').write_bytes(b)
            self.assertEqual(self.comparison().environment_diff(ref, env)[0], [])
            (env/'sales.xlsx').write_bytes(raw(43))
            self.assertEqual(self.comparison().environment_diff(ref, env)[0], ['sales.xlsx'])

    def test_existing_ids_are_not_arbitrarily_remapped(self):
        self.assertFalse(self.comparison().tool_equal('chat__get_chat', {'id': 'c_a'}, {'id': 'c_b'}))

    def test_attachment_empty_text_is_tracked_across_reads_and_state(self):
        c = self.comparison()
        old, new = 'msg_'+'a'*32, 'msg_'+'b'*32
        a, b = {'id':old, 'text':'.'}, {'id':new, 'text':''}
        self.assertTrue(c.tool_equal('chat__send_file', {'content':[{'text':json.dumps(a)}]},
                                    {'content':[{'text':json.dumps(b)}]}))
        self.assertTrue(c.tool_equal('chat__list_messages', {'messages':[a]}, {'messages':[b]}))
        self.assertEqual(c.normalize({'messages':[a]}), c.normalize({'messages':[b]}))
        self.assertFalse(c.tool_equal('chat__list_messages', {'messages':[dict(a,text='real text')]}, {'messages':[b]}))
        self.assertFalse(c.tool_equal('chat__list_messages', {'id':'other','text':'.'}, {'id':'other','text':''}))

    def test_paths_keep_relative_location(self):
        c = self.comparison()
        self.assertEqual(c.normalize('D:/original/workspace/x'), c.normalize('D:/replay/workspace/x'))
        self.assertNotEqual(c.normalize('D:/original/workspace/x'), c.normalize('D:/replay/workspace/y'))

    def test_legacy_log_projection_keeps_business_values(self):
        c = self.comparison()
        a = {'payments': {'p': {'amount': 10}}, 'mutation_events': [{'action': 'pay'}]}
        b = {'payments': {'p': {'amount': 10}}, 'mutation_events': [{'action': 'pay', 'at': 'time', 'arguments': {}}]}
        x, y = c.align_state(a, b)
        self.assertEqual(x, y)
        b['payments']['p']['amount'] = 20
        x, y = c.align_state(a, b)
        self.assertNotEqual(x, y)

    def test_mime_boundary_is_ignored_but_recipient_is_not(self):
        def message(boundary, recipient):
            m = EmailMessage(); m['To'] = recipient; m.set_content('body')
            m.add_attachment(b'payload', maintype='application', subtype='octet-stream', filename='a.txt')
            m.set_boundary(boundary)
            return base64.b64encode(m.as_bytes()).decode()
        c = self.comparison()
        self.assertEqual(c.normalize(message('a','a@example.test'), 'mime_base64'), c.normalize(message('b','a@example.test'), 'mime_base64'))
        self.assertNotEqual(c.normalize(message('a','a@example.test'), 'mime_base64'), c.normalize(message('b','b@example.test'), 'mime_base64'))

    def test_environment_still_rejects_changed_contents(self):
        with tempfile.TemporaryDirectory() as temp:
            a,b = Path(temp)/'a',Path(temp)/'b'; a.mkdir();b.mkdir()
            (a/'file.txt').write_text('original');(b/'file.txt').write_text('wrong')
            self.assertEqual(self.comparison().environment_diff(a,b)[0], ['file.txt'])

    def test_empty_legacy_field_equivalence_is_tool_specific(self):
        c = self.comparison()
        self.assertTrue(c.tool_equal('chat__search_contacts', {'organization':'.'}, {'organization':''}))
        self.assertFalse(c.tool_equal('files__read_file', {'text':'.'}, {'text':''}))

    def test_zip_hash_mapping_requires_identical_member_bytes(self):
        def archive(year, payload):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w') as z:
                z.writestr(zipfile.ZipInfo('data.txt', (year,1,1,0,0,0)), payload)
            return stream.getvalue()
        def result(raw):
            return {'content':[{'text':json.dumps({'backup':{'sha256':hashlib.sha256(raw).hexdigest(),
                    'archive_path':'backups/bak_000001.zip'}})}],'isError':False}
        with tempfile.TemporaryDirectory() as temp:
            ref,env = Path(temp)/'ref',Path(temp)/'env'
            for p in [ref,env]:(p/'services/server/backups').mkdir(parents=True)
            a,b = archive(2020,b'same'),archive(2026,b'same')
            (ref/'services/server/backups/bak_000001.zip').write_bytes(a)
            (env/'services/server/backups/bak_000001.zip').write_bytes(b)
            self.assertTrue(Comparison(ref,env,ref).tool_equal('server__server_create_backup',result(a),result(b)))
            bad=archive(2026,b'changed');(env/'services/server/backups/bak_000001.zip').write_bytes(bad)
            self.assertFalse(Comparison(ref,env,ref).tool_equal('server__server_create_backup',result(a),result(bad)))

    def test_git_reflog_path_and_clock_do_not_hide_commit_change(self):
        with tempfile.TemporaryDirectory() as temp:
            a,b=Path(temp)/'a',Path(temp)/'b';rel='workspace/repos/r/.git/logs/HEAD'
            for p in [a,b]:(p/rel).parent.mkdir(parents=True)
            (a/rel).write_text('old new User <a@b> 100 +0000\tfetch D:/original/workspace/r\n')
            (b/rel).write_text('old new User <a@b> 200 +0800\tfetch D:/replay/workspace/r\n')
            self.assertEqual(self.comparison().environment_diff(a,b)[0],[])
            (b/rel).write_text('old WRONG User <a@b> 200 +0800\tfetch D:/replay/workspace/r\n')
            self.assertEqual(self.comparison().environment_diff(a,b)[0],[rel])
            (a/rel).write_text('old new User <a@b> 100 +0000\n')
            (b/rel).write_text('old new User <a@b> 200 +0800\n')
            self.assertEqual(self.comparison().environment_diff(a,b)[0],[])

    def test_archived_zip_snapshot_preserves_every_member_payload(self):
        def state(year, payload):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w') as z:
                z.writestr(zipfile.ZipInfo('data.txt', (year,1,1,0,0,0)), payload)
            return {'mutation_events':[{'puts':{'backups/a.zip':base64.b64encode(stream.getvalue()).decode()}}]}
        c = self.comparison()
        a, b = c.align_state(state(2020,b'same'), state(2026,b'same'))
        self.assertEqual(a,b)
        a, b = c.align_state(state(2020,b'same'), state(2026,b'changed'))
        self.assertNotEqual(a,b)

    def test_user_json_fields_are_not_treated_as_internal_audit_logs(self):
        with tempfile.TemporaryDirectory() as temp:
            a,b=Path(temp)/'a',Path(temp)/'b'
            for p in [a,b]:(p/'workspace').mkdir(parents=True)
            (a/'workspace/report.json').write_text('{}')
            (b/'workspace/report.json').write_text('{"mutation_events":[1]}')
            self.assertEqual(self.comparison().environment_diff(a,b)[0],['workspace/report.json'])


if __name__ == '__main__': unittest.main()
