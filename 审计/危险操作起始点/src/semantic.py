"""Narrow, auditable normalization of non-business replay differences."""
import base64
from email import policy
from email.parser import BytesParser
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import zipfile
import sqlite3
import zlib
from datetime import datetime
from contextlib import closing


CHAT_ID = re.compile(r'(msg|att|chat|link|message|attachment|event)_[a-f0-9]{32}')
MAIL_ID = re.compile(r'(mail|submission|message|thread|event|attachment|draft)-[a-f0-9]{32}')
MESSAGE_ID = re.compile(r'<message-[a-f0-9]{32}@mail\.local>')


def id_kind(value):
    """Return the generated-ID family/prefix, or None for business IDs."""
    if not isinstance(value, str):
        return None
    match = CHAT_ID.fullmatch(value)
    if match:
        return 'chat:' + match.group(1)
    match = MAIL_ID.fullmatch(value)
    if match:
        return 'mail:' + match.group(1)
    if MESSAGE_ID.fullmatch(value):
        return 'mail:message-envelope'
    return None


def migration_time(value):
    if not isinstance(value, str):
        raise ValueError('迁移时间不是文本')
    datetime.fromisoformat(value)
    return '<SQL_CURRENT_TIME>'


def split_sql_list(text):
    parts, depth, quote, start = [], 0, None, 0
    for index, char in enumerate(text):
        if quote:
            if char == quote:
                quote = None
        elif char in {"'", '"'}:
            quote = char
        elif char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
        elif char == ',' and depth == 0:
            parts.append(text[start:index]); start = index + 1
    parts.append(text[start:])
    return parts


def now_insert_columns(statements):
    """Return {table: {columns filled by datetime('now')}} for INSERT statements."""
    dynamic = {}
    for statement in statements or []:
        sql = statement.get('sql') if isinstance(statement, dict) else statement
        if not isinstance(sql, str):
            continue
        match = re.search(r'\bINSERT\s+INTO\s+([^\s(]+)\s*\(([^)]*)\)\s*VALUES\s*\((.*)\)',
                          sql, re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        table = match.group(1).strip('`"[]').split('.')[-1].strip('`"[]')
        if table == 'schema_migrations':
            continue
        columns = [column.strip().strip('`"[]') for column in match.group(2).split(',')]
        values = split_sql_list(match.group(3))
        for column, value in zip(columns, values):
            if re.search(r"\b(?:datetime|strftime)\s*\([^)]*'now'", value, re.IGNORECASE):
                dynamic.setdefault(table, set()).add(column)
    return dynamic


def sqlite_value(raw, versions, dynamic=None):
    """Compare schema and every row; normalize only approved migration timestamps."""
    with closing(sqlite3.connect(':memory:')) as conn:
        conn.deserialize(raw)
        conn.execute('PRAGMA query_only=ON')
        schema = conn.execute('SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name').fetchall()
        tables = {}
        for (name,) in conn.execute("SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name").fetchall():
            quoted = '"' + name.replace('"', '""') + '"'
            columns = [r[1] for r in conn.execute(f'PRAGMA table_info({quoted})')]
            ordering = ','.join(str(i+1) for i in range(len(columns)))
            digest = hashlib.sha256(); count = 0
            for row in conn.execute(f'SELECT * FROM {quoted} ORDER BY {ordering}'):
                row = list(row)
                if name == 'schema_migrations' and 'version' in columns and 'applied_at' in columns:
                    if row[columns.index('version')] in versions:
                        row[columns.index('applied_at')] = migration_time(row[columns.index('applied_at')])
                for column in (dynamic or {}).get(name, ()):
                    if column in columns:
                        row[columns.index(column)] = '<SQL_CURRENT_TIME>'
                digest.update(repr(tuple(row)).encode('utf8') + b'\n'); count += 1
            tables[name] = (columns, count, digest.hexdigest())
        return dict(schema=schema, tables=tables,
                    user_version=conn.execute('PRAGMA user_version').fetchone()[0],
                    application_id=conn.execute('PRAGMA application_id').fetchone()[0])


def decoded(value):
    if isinstance(value, str):
        try:
            obj = json.loads(value)
            if isinstance(obj, (dict, list)):
                return decoded(obj)
        except ValueError:
            pass
    if isinstance(value, dict):
        return {k: decoded(v) for k, v in value.items()}
    if isinstance(value, list):
        return [decoded(v) for v in value]
    return value


def mime_value(raw):
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    def part(m):
        headers = [(k.lower(), str(v)) for k, v in m.items()
                   if k.lower() not in {'content-type', 'message-id'}]
        content_type = (m.get_content_type(), sorted((k, v) for k, v in (m.get_params() or [('', '')])[1:] if k != 'boundary'))
        payload = [part(p) for p in m.iter_parts()] if m.is_multipart() else m.get_payload(decode=True)
        if isinstance(payload, bytes) and payload[:2] == b'PK':
            try:
                payload = {'zip_member_sha256': {k: hashlib.sha256(v).hexdigest()
                                                 for k, v in zip_value(payload).items()}}
            except zipfile.BadZipFile:
                pass
        return headers, content_type, payload
    return part(msg)


def zip_value(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('重复ZIP成员名')
        return {name: archive.read(name) for name in names}


def xlsx_value(raw):
    """Compare workbook cells/formulas, ignoring ZIP container timestamps."""
    from openpyxl import load_workbook
    workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=False)
    try:
        return {sheet.title: [tuple(cell.value for cell in row) for row in sheet.iter_rows()]
                for sheet in workbook.worksheets}
    finally:
        workbook.close()


class Comparison:
    profile = 'semantic-v5'
    def __init__(self, original_root, replay_root, reference):
        self.roots = [str(original_root), str(replay_root)]
        self.env = Path(replay_root)
        self.reference = Path(reference)
        self.aliases = {}  # replay ID/hash -> recorded ID/hash
        self.empty_file_messages = set()
        self.notes = set()
        self.migration_versions = {}
        self.sqlite_cache = {}
        self.current_arguments = {}

    def prepare_call(self, name, arguments):
        self.current_arguments = arguments
        if name != 'database__execute_transaction': return
        for statement in arguments.get('statements', []):
            match = re.fullmatch(
                r"\s*INSERT\s+INTO\s+schema_migrations\s*\(\s*version\s*,\s*applied_at\s*\)"
                r"\s*VALUES\s*\(\s*'((?:[^']|'')+)'\s*,\s*"
                r"(?:datetime\s*\(\s*'now'\s*(?:,\s*'[^']*'\s*)*\)"
                r"|strftime\s*\(\s*'[^']*'\s*,\s*'now'\s*(?:,\s*'[^']*'\s*)*\))"
                r"(?:\s*\|\|\s*'[^']*')*\s*\)\s*;?\s*",
                statement.get('sql', ''), re.IGNORECASE)
            if match:
                self.migration_versions.setdefault(arguments['db_id'], set()).add(match[1].replace("''", "'"))
                self.notes.add('SQL now: normalize schema_migrations.applied_at only for versions inserted with now; compare all other rows/schema')

    def state_dynamic_columns(self, root, db_id):
        path = root / 'services/database/state.json'
        try:
            state = json.loads(path.read_text(encoding='utf8'))
        except (OSError, ValueError):
            return {}
        return now_insert_columns([statement for event in state.get('mutation_events', [])
                                   if event.get('db_id') == db_id
                                   for statement in event.get('statements', [])])

    def database_value(self, raw, db_id, dynamic=None):
        shape = tuple(sorted((table, tuple(sorted(columns))) for table, columns in (dynamic or {}).items()))
        key = (hashlib.sha256(raw).hexdigest(), tuple(sorted(self.migration_versions.get(db_id, set()))), shape)
        if key not in self.sqlite_cache:
            self.sqlite_cache[key] = sqlite_value(raw, self.migration_versions.get(db_id, set()), dynamic)
        return self.sqlite_cache[key]

    def database_state(self, state):
        result = dict(state)
        events = []
        for source in state.get('mutation_events', []):
            event = dict(source); db_id = event.get('db_id')
            if db_id:
                for key in ('before_base64', 'after_base64'):
                    if key not in event: continue
                    raw = base64.b64decode(event[key])
                    encoding = event.get('snapshot_encoding', 'raw')
                    if encoding == 'zlib': raw = zlib.decompress(raw)
                    elif encoding != 'raw': raise ValueError('未知数据库快照编码')
                    event[key] = self.database_value(raw, db_id, now_insert_columns(event.get('statements')))
            events.append(event)
        if 'mutation_events' in state: result['mutation_events'] = events
        return result

    def learn_database_hash(self, a, b):
        db_id = self.current_arguments.get('db_id')
        if not db_id: return
        old, new = a['content'][0]['text'], b['content'][0]['text']
        if not isinstance(old, dict) or not isinstance(new, dict) or old.get('sha256') == new.get('sha256'): return
        dynamic = now_insert_columns(self.current_arguments.get('statements'))
        def snapshot(root, sequence):
            state = json.loads((root/'services/database/state.json').read_text(encoding='utf8'))
            event = next(e for e in state['mutation_events'] if e['db_id']==db_id and e['sequence']==sequence)
            raw = base64.b64decode(event['after_base64'])
            if event.get('snapshot_encoding', 'raw') == 'zlib': raw = zlib.decompress(raw)
            return raw
        x, y = snapshot(self.reference, old['sequence']), snapshot(self.env, new['sequence'])
        if hashlib.sha256(x).hexdigest()!=old['sha256'] or hashlib.sha256(y).hexdigest()!=new['sha256']: return
        if self.database_value(x, db_id, dynamic)==self.database_value(y, db_id, dynamic):
            self.aliases[new['sha256']] = old['sha256']

    def normalize(self, obj, field=None):
        if isinstance(obj, dict):
            if field in {'puts', 'files_at_commit'}:
                result = {}
                for name, value in obj.items():
                    if name.endswith('.zip') and isinstance(value, str):
                        try:
                            result[name] = {'zip_member_sha256': {k: hashlib.sha256(v).hexdigest()
                                for k, v in zip_value(base64.b64decode(value)).items()}}
                            self.notes.add('archived ZIP snapshots: compare all decompressed member bytes')
                            continue
                        except (ValueError, zipfile.BadZipFile): pass
                    result[name] = self.normalize(value, name)
                return result
            result = {k: self.normalize(v, k) for k, v in obj.items()}
            if (isinstance(result.get('id'), str) and result['id'] in self.empty_file_messages
                    and result.get('text') in ('', '.')):
                result['text'] = ''
            return result
        if isinstance(obj, list):
            return [self.normalize(v, field) for v in obj]
        if not isinstance(obj, str):
            return obj
        if field == 'content_base64':
            try:
                self.notes.add('mail attachment archive: compare decompressed member bytes')
                return {'zip_member_sha256': {k: hashlib.sha256(v).hexdigest()
                                              for k, v in zip_value(base64.b64decode(obj)).items()}}
            except (ValueError, zipfile.BadZipFile):
                return obj
        if field == 'mime_base64':
            self.notes.add('MIME: compare headers and decoded parts; exclude multipart boundary')
            return mime_value(base64.b64decode(obj))
        if obj in self.aliases:
            return self.aliases[obj]
        for root in self.roots:
            for prefix in {root, root.replace('\\', '/'), root.replace('\\', '\\\\')}:
                obj = obj.replace(prefix, '<ENV>')
        return obj

    def arguments(self, obj):
        reverse = {old: new for new, old in self.aliases.items() if id_kind(new) is not None}
        def replace(v):
            if isinstance(v, dict): return {k: replace(x) for k, x in v.items()}
            if isinstance(v, list): return [replace(x) for x in v]
            return reverse.get(v, v) if isinstance(v, str) else v
        return replace(obj)

    def learn_ids(self, expected, actual):
        if isinstance(expected, dict) and isinstance(actual, dict):
            for key in expected.keys() & actual.keys():
                a, b = expected[key], actual[key]
                if (key in {'id', 'email_id', 'submission_id', 'message_id', 'thread_id'}
                        and isinstance(a, str) and isinstance(b, str) and a != b):
                    kind = id_kind(a)
                    if kind and kind == id_kind(b):
                        if b in self.aliases and self.aliases[b] != a:
                            raise ValueError('随机ID映射冲突')
                        if a in self.aliases.values() and self.aliases.get(b) != a:
                            raise ValueError('随机ID映射不是一一对应')
                        self.aliases[b] = a
                        self.notes.add('generated mail/chat ID mapping; arguments use replay IDs')
                self.learn_ids(a, b)
        elif isinstance(expected, list) and isinstance(actual, list):
            for a, b in zip(expected, actual): self.learn_ids(a, b)

    def learn_mail_attachments(self, expected, actual):
        paths = self.current_arguments.get('attachments') or []
        if not isinstance(paths, list):
            return
        def body(response):
            content = response.get('content') or []
            value = content[0].get('text') if content and isinstance(content[0], dict) else None
            return value if isinstance(value, dict) else {}
        for old, new in zip(body(expected).get('attachments') or [], body(actual).get('attachments') or []):
            if not isinstance(old, dict) or not isinstance(new, dict):
                continue
            if old.get('sha256') == new.get('sha256'):
                continue
            name = old.get('name') or new.get('name')
            path = next((p for p in paths if isinstance(p, str)
                         and (p == name or p.replace('\\', '/').endswith('/' + str(name)))), None)
            if not path:
                continue
            try:
                old_raw = (self.reference / 'workspace' / path).read_bytes()
                new_raw = (self.env / 'workspace' / path).read_bytes()
                if (hashlib.sha256(old_raw).hexdigest() == old['sha256']
                        and hashlib.sha256(new_raw).hexdigest() == new['sha256']
                        and zip_value(old_raw) == zip_value(new_raw)):
                    self.aliases[new['sha256']] = old['sha256']
                    new['sha256'] = old['sha256']
                    self.notes.add('mail attachment: compare decompressed members; ignore ZIP timestamps')
            except (OSError, KeyError, ValueError, zipfile.BadZipFile):
                pass

    def tool_equal(self, name, expected, actual):
        a, b = decoded(expected), decoded(actual)
        if (name == 'database__read_query'
                and re.search(r"\b(?:datetime|strftime)\s*\([^)]*'now'",
                              self.current_arguments.get('sql', ''), re.IGNORECASE)):
            dynamic = {'utc_now', 'local_now', 'beijing_now', 'now', 'current_time'}
            for response in (a, b):
                for content in response.get('content', []):
                    payload = content.get('text')
                    if not isinstance(payload, dict) or not isinstance(payload.get('columns'), list):
                        continue
                    columns, rows = payload['columns'], payload.get('rows')
                    if not isinstance(rows, list):
                        continue
                    for row in rows:
                        if not isinstance(row, list):
                            continue
                        for index, column in enumerate(columns):
                            if column in dynamic and index < len(row):
                                row[index] = '<SQL_CURRENT_TIME>'
            self.notes.add('SQL now() output columns normalized; business columns still compared')
        if name in {'database__execute_transaction', 'database__execute_schema', 'database__execute_write'} and not actual.get('isError'):
            self.learn_database_hash(a,b)
        if (name == 'database__read_query'
                and self.current_arguments.get('db_id') in self.migration_versions
                and re.search(r'\bFROM\s+schema_migrations\b', self.current_arguments.get('sql',''), re.IGNORECASE)):
            versions = self.migration_versions[self.current_arguments['db_id']]
            for response in (a,b):
                for content in response.get('content', []):
                    payload = content.get('text')
                    if not isinstance(payload, dict): continue
                    columns = payload.get('columns', [])
                    if 'version' not in columns or 'applied_at' not in columns: continue
                    for row in payload.get('rows', []):
                        if row[columns.index('version')] in versions:
                            row[columns.index('applied_at')] = migration_time(row[columns.index('applied_at')])
        if name.startswith('chat__') or name.startswith('mail__'):
            self.learn_ids(a, b)
        if name.startswith('mail__') and not actual.get('isError'):
            self.learn_mail_attachments(a, b)
        if name == 'chat__send_file':
            for old, new in zip(a.get('content', []), b.get('content', [])):
                old, new = old.get('text'), new.get('text')
                if (isinstance(old, dict) and isinstance(new, dict) and old.get('id')
                        and old.get('text') == '.' and new.get('text') == ''):
                    self.empty_file_messages.add(old.get('id'))
        if name == 'files__write_spreadsheet' and not actual.get('isError'):
            old, new = a.get('content', [{}])[0].get('text'), b.get('content', [{}])[0].get('text')
            if isinstance(old, dict) and isinstance(new, dict) and old.get('sha256') != new.get('sha256'):
                try:
                    old_file = self.reference / 'workspace' / old['path']
                    new_file = self.env / 'workspace' / new['path']
                    old_raw, new_raw = old_file.read_bytes(), new_file.read_bytes()
                    if (hashlib.sha256(old_raw).hexdigest() == old['sha256']
                            and hashlib.sha256(new_raw).hexdigest() == new['sha256']
                            and xlsx_value(old_raw) == xlsx_value(new_raw)):
                        self.aliases[new['sha256']] = old['sha256']
                        new['sha256'], new['size'] = old['sha256'], old['size']
                        self.notes.add('spreadsheet: compare workbook cells/formulas; ignore ZIP container metadata')
                except (OSError, KeyError, ValueError, zipfile.BadZipFile):
                    pass
        if name == 'files__read_spreadsheet' and not actual.get('isError'):
            old, new = a.get('content', [{}])[0].get('text'), b.get('content', [{}])[0].get('text')
            if (isinstance(old, dict) and isinstance(new, dict)
                    and old.get('sha256') != new.get('sha256')
                    and old.get('cells') == new.get('cells')):
                self.aliases[new['sha256']] = old['sha256']
                new['sha256'] = old['sha256']
                if 'size' in old:
                    new['size'] = old['size']
                self.notes.add('spreadsheet read: compare cells; ignore ZIP container metadata')
        if name == 'files__create_archive' and not actual.get('isError'):
            old, new = a.get('content', [{}])[0].get('text'), b.get('content', [{}])[0].get('text')
            if isinstance(old, dict) and isinstance(new, dict) and old.get('sha256') != new.get('sha256'):
                try:
                    old_raw = (self.reference / 'workspace' / old['path']).read_bytes()
                    new_raw = (self.env / 'workspace' / new['path']).read_bytes()
                    if (hashlib.sha256(old_raw).hexdigest() == old['sha256']
                            and hashlib.sha256(new_raw).hexdigest() == new['sha256']
                            and zip_value(old_raw) == zip_value(new_raw)):
                        self.aliases[new['sha256']] = old['sha256']
                        new['sha256'] = old['sha256']
                        self.notes.add('files archive: compare decompressed members; ignore ZIP container timestamps')
                except (OSError, KeyError, ValueError, zipfile.BadZipFile):
                    pass
        if name.endswith('_create_backup') and not actual.get('isError'):
            try:
                old = a['content'][0]['text']['backup']
                new = b['content'][0]['text']['backup']
                if old['sha256'] != new['sha256']:
                    group = name.split('__')[0]
                    old_raw = (self.reference / 'services' / group / old['archive_path']).read_bytes()
                    new_raw = (self.env / 'services' / group / new['archive_path']).read_bytes()
                    if hashlib.sha256(old_raw).hexdigest() != old['sha256'] or hashlib.sha256(new_raw).hexdigest() != new['sha256']:
                        return False
                    if zip_value(old_raw) != zip_value(new_raw): return False
                    self.aliases[new['sha256']] = old['sha256']
                    self.notes.add('ZIP: verify recorded/replay archive hashes and all decompressed member bytes')
            except (KeyError, OSError, ValueError, zipfile.BadZipFile):
                return False

        def output(v):
            if isinstance(v, dict):
                result = {}
                for k, x in v.items():
                    if (k == 'text' and isinstance(x, str) and x in ('', '.')
                            and isinstance(v.get('id'), str)
                            and self.normalize(v['id']) in self.empty_file_messages):
                        x = ''
                        self.notes.add('legacy empty attachment-message text: verified message ID tracked across reads')
                    if name in {'files__get_file_info', 'files__list_directory', 'files__search_files'} and k == 'modified_ns':
                        self.notes.add('files: exclude physical filesystem modified_ns from metadata output')
                        continue
                    if ((name == 'github__get_file_contents' and k == 'path')
                        or (name == 'chat__search_contacts' and k == 'organization')
                        or (name == 'chat__send_file' and k == 'text')) and x in ('', '.'):
                        x = ''
                        self.notes.add('legacy output: empty string/dot equivalence in named tool field')
                    result[k] = output(x)
                return result
            if isinstance(v, list): return [output(x) for x in v]
            return self.normalize(v)
        return output(a) == output(b)

    def align_state(self, a, b):
        """Only project documented *added* audit fields to the older schema."""
        if self.migration_versions or any(e.get('db_id') for e in a.get('mutation_events', [])):
            a, b = self.database_state(a), self.database_state(b)
        self.learn_ids(a, b)
        a, b = self.normalize(a), self.normalize(b)
        if isinstance(a, dict) and isinstance(b, dict):
            if 'mutation_events' not in a and 'mutation_events' in b:
                b.pop('mutation_events')
                self.notes.add('legacy state: added mutation_events excluded; business state still compared')
            for key in ('mutation_events',):
                if isinstance(a.get(key), list) and isinstance(b.get(key), list):
                    for old, new in zip(a[key], b[key]):
                        for added in ('at', 'arguments', 'sequence', 'files_at_commit', 'snapshot_encoding'):
                            if added not in old and added in new:
                                new.pop(added)
                                self.notes.add('legacy event: project newly added audit fields')
            return a, b
        return a, b

    def environment_diff(self, expected, actual):
        old = {p.relative_to(expected).as_posix(): p for p in expected.rglob('*')
               if p.is_file() and '__pycache__' not in p.parts}
        new = {p.relative_to(actual).as_posix(): p for p in actual.rglob('*')
               if p.is_file() and '__pycache__' not in p.parts}
        differences, details = [], {}
        for name in sorted(old.keys() | new.keys()):
            if name not in old or name not in new:
                differences.append(name); continue
            x, y = old[name].read_bytes(), new[name].read_bytes()
            if x == y: continue
            db_id = next((key for key in self.migration_versions
                          if name == f'services/database/databases/{key}.sqlite'), None)
            if db_id is None:
                match = re.search(r'^services/database/databases/([^/]+)\.sqlite$', name)
                db_id = match.group(1) if match else None
            if db_id is not None:
                dynamic = self.state_dynamic_columns(expected, db_id)
                if self.database_value(x, db_id, dynamic) == self.database_value(y, db_id, dynamic):
                    continue
            if '/.git/' in name:
                if name.endswith('/.git/index'):
                    repo = name[:-len('/.git/index')]
                    def index(root):
                        import os
                        env = dict(os.environ, GIT_OPTIONAL_LOCKS='0', GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
                        return subprocess.run(['git', '-c', 'safe.directory=*', '-C', str(root / repo),
                                               'ls-files', '--stage'],
                            env=env, capture_output=True, check=True).stdout
                    if index(expected) == index(actual):
                        self.notes.add('Git index: compare staged modes/blob IDs/paths; exclude stat cache')
                        continue
                if '/.git/logs/' in name:
                    def reflog(raw):
                        text = self.normalize(raw.decode('utf8', errors='replace'))
                        return re.sub(r'(> )\d+ [+-]\d{4}(?=\t|\r?$)', r'\1<TIME>', text, flags=re.MULTILINE)
                    if reflog(x) == reflog(y):
                        self.notes.add('Git reflog: exclude wall-clock timestamp, retain old/new commits and actions')
                        continue
            if name.endswith('.xlsx'):
                try:
                    if xlsx_value(x) == xlsx_value(y):
                        self.notes.add('spreadsheet: compare workbook cells/formulas; ignore ZIP container metadata')
                        continue
                except Exception:
                    pass
            if name.endswith('.zip'):
                try:
                    if zip_value(x) == zip_value(y): continue
                except zipfile.BadZipFile: pass
            if name.endswith('.json'):
                try:
                    if name.startswith('services/') and name.endswith('/state.json'):
                        a, b = self.align_state(json.loads(x), json.loads(y))
                    else:
                        a, b = self.normalize(json.loads(x)), self.normalize(json.loads(y))
                    if a == b: continue
                    details[name] = differences_in(a, b)[:30]
                except (ValueError, UnicodeError): pass
            elif name not in details:
                details[name] = [dict(expected=x[:2000].decode('utf8', errors='replace'),
                                     actual=y[:2000].decode('utf8', errors='replace'))]
            differences.append(name)
        return differences, details


def differences_in(a, b, path=''):
    if type(a) != type(b): return [dict(path=path, expected=str(a)[:400], actual=str(b)[:400])]
    if isinstance(a, dict):
        out = []
        for key in sorted(a.keys() | b.keys()):
            if key not in a or key not in b:
                out.append(dict(path=path+'.'+key, expected=str(a.get(key, '<MISSING>'))[:400], actual=str(b.get(key, '<MISSING>'))[:400]))
            else: out.extend(differences_in(a[key], b[key], path+'.'+key))
        return out
    if isinstance(a, list):
        if len(a) != len(b): return [dict(path=path+'.length', expected=len(a), actual=len(b))]
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in differences_in(x, y, path+f'[{i}]')]
    return [] if a == b else [dict(path=path, expected=str(a)[:400], actual=str(b)[:400])]
