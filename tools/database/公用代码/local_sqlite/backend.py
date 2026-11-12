import base64
import csv
import hashlib
import io
import json
import math
import os
import re
import sqlite3
import tempfile
import time
import uuid
import zlib
from contextlib import contextmanager, closing
from datetime import datetime, timedelta
from pathlib import Path

from filelock import FileLock
from .query_core import execute_bound

MAX_FILE = 25 * 1024 * 1024


def quote(name):
    if not name or "\x00" in name:
        raise ValueError("Invalid SQL identifier")
    return '"' + name.replace('"', '""') + '"'


def cell(value):
    if isinstance(value, bytes):
        return {"type": "blob", "base64": base64.b64encode(value).decode()}
    if isinstance(value, float) and not math.isfinite(value):
        return {"type": "float", "value": str(value)}
    return value


def page(items, offset, limit):
    if offset < 0 or not 1 <= limit <= 100:
        raise ValueError("offset >= 0; limit 1..100")
    return {"items": items[offset:offset+limit], "total": len(items), "next_offset": offset+limit if offset+limit < len(items) else None}


from .workbench import DatabaseWorkbench


class SQLiteStore(DatabaseWorkbench):
    def __init__(self, run_root):
        self.root = Path(run_root).resolve()
        self.workspace = self.root / "workspace"
        self.service = self.root / "services" / "database"
        self.files = self.workspace
        self.dbs = self.service / "databases"
        self.state_path = self.service / "state.json"
        self.lock = FileLock(str(self.service / "state.lock"), timeout=20)
        self.files.mkdir(parents=True, exist_ok=True)
        self.dbs.mkdir(parents=True, exist_ok=True)
        with self.lock:
            if not self.state_path.exists():
                raise ValueError("Missing services/database/state.json; copy the initial environment into the run root first")
            state = self.load(self.state_path)
            self.engine_options = state.get("engine_options", {})
            ids = [d["id"] for d in state["databases"]]
            if len(ids) != len(set(ids)) or any(not re.fullmatch(r"[A-Za-z0-9_-]+", x) for x in ids):
                raise ValueError("Database IDs must be unique simple names")
            for d in state["databases"]:
                p = self.safe(self.dbs, d["id"] + ".sqlite")
                self.standalone(p)
            state.setdefault("sequence", 0)

    @staticmethod
    def load(path):
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def safe(root, value):
        if root.is_symlink() or root.is_junction():
            raise ValueError("Allowed roots cannot be links")
        root = root.resolve()
        p = Path(value)
        p = Path(os.path.abspath(p if p.is_absolute() else root / p))
        if not p.is_relative_to(root) or ":" in str(value).replace(str(Path(value).drive), "", 1):
            raise ValueError("Path must stay inside its allowed directory")
        current = root
        for part in ("", *p.relative_to(root).parts):
            current = current / part
            if current.is_symlink() or current.is_junction() or (current.is_file() and current.stat().st_nlink > 1):
                raise ValueError("Links/junctions/hardlinks are not supported")
            if current != p and current.exists() and not current.is_dir():
                raise NotADirectoryError(str(current))
        return p.resolve()

    def bytes(self, path):
        maximum = self.engine_options.get("max_database_bytes", MAX_FILE) if Path(path).is_relative_to(self.service) else MAX_FILE
        with path.open("rb") as f:
            data = f.read(maximum + 1)
        if len(data) > maximum:
            raise ValueError("File exceeds 25 MiB")
        return data

    @staticmethod
    def standalone(path):
        if any(Path(str(path)+suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
            raise ValueError("Database must be closed and checkpointed; sidecar journals are not supported")
        with path.open("rb") as f:
            header = f.read(20)
        if header[:16] != b"SQLite format 3\x00" or header[18:20] != b"\x01\x01":
            raise ValueError("Use a valid standalone SQLite database in DELETE journal mode")

    @staticmethod
    def atomic_bytes(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data); f.flush(); os.fsync(f.fileno())
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)

    @staticmethod
    def atomic_json(path, data):
        SQLiteStore.atomic_bytes(path, (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode())

    def commit(self, state):
        state["sequence"] += 1
        state["now"] = (datetime.fromisoformat(state["now"].replace("Z", "+00:00")) + timedelta(microseconds=1)).isoformat()
        self.atomic_json(self.state_path, state)
        return state["sequence"]

    @contextmanager
    def session(self):
        with self.lock:
            yield self.load(self.state_path)

    @contextmanager
    def connect(self, path, readonly=True):
        with closing(sqlite3.connect(path.as_uri() + ("?mode=ro" if readonly else "?mode=rw"), uri=True, timeout=5)) as conn:
            conn.enable_load_extension(False)
            conn.execute("PRAGMA foreign_keys=ON"); conn.execute("PRAGMA trusted_schema=OFF")
            if readonly:
                conn.execute("PRAGMA query_only=ON")
            conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 4 * 1024 * 1024)
            conn.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 100000)
            conn.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
            deadline, calls = time.monotonic()+self.engine_options.get("query_timeout_seconds", 5), [0]
            def progress():
                calls[0] += 1
                return int(calls[0] > self.engine_options.get("progress_calls", 2000) or time.monotonic() > deadline)
            conn.set_progress_handler(progress, 1000)
            if self.engine_options.get("legacy_alter_table"): conn.execute("PRAGMA legacy_alter_table=ON")
            yield conn

    @staticmethod
    def authorize(mode):
        allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
        if mode in ("write", "schema", "transaction"):
            allowed.update((sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE))
        if mode in ("schema", "transaction"):
            allowed.update(getattr(sqlite3, "SQLITE_"+name) for name in ("CREATE_TABLE", "DROP_TABLE", "ALTER_TABLE", "CREATE_INDEX", "DROP_INDEX", "CREATE_VIEW", "DROP_VIEW", "CREATE_TRIGGER", "DROP_TRIGGER", "REINDEX", "ANALYZE"))
        def check(action, a, b, db, trigger):
            check.seen.add(action)
            if action == sqlite3.SQLITE_FUNCTION and (b or a or "").casefold() in ("load_extension", "readfile", "writefile", "eval"):
                return sqlite3.SQLITE_DENY
            if mode == "write" and action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE) and a in ("sqlite_master", "sqlite_schema"):
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY
        check.seen = set()
        return check

    def database(self, state, db_id):
        if not any(d["id"] == db_id for d in state["databases"]):
            raise ValueError("Unknown database ID")
        p = self.safe(self.dbs, db_id + ".sqlite")
        self.standalone(p)
        return p

    @staticmethod
    def query(conn, sql, parameters=None, limit=1000, offset=0):
        if not 1 <= limit <= 1000 or not 0 <= offset <= 10000:
            raise ValueError("limit 1..1000; offset 0..10000")
        result = execute_bound(conn, sql, parameters, offset+limit+1)
        more = len(result["rows"]) > offset+limit
        result["rows"] = [[cell(v) for v in row] for row in result["rows"][offset:offset+limit]]
        result.update(row_count=len(result["rows"]), has_more=more, next_offset=offset+limit if more else None)
        if len(json.dumps(result, ensure_ascii=False)) > 1024 * 1024:
            raise ValueError("Result exceeds 1 MiB; narrow query/limit")
        return result

    def list_databases(self):
        with self.session() as s:
            return {"items": [{**d, "path": str(self.database(s, d["id"]))} for d in s["databases"]]}

    def get_database_info(self, db_id):
        with self.session() as s:
            p = self.database(s, db_id)
            with self.connect(p) as conn:
                return {"id": db_id, "path": str(p), "size": p.stat().st_size, "sha256": hashlib.sha256(self.bytes(p)).hexdigest(), "sqlite_version": sqlite3.sqlite_version,
                        "page_count": conn.execute("PRAGMA page_count").fetchone()[0], "page_size": conn.execute("PRAGMA page_size").fetchone()[0]}

    def list_tables(self, db_id, include_views=True):
        with self.session() as s:
            with self.connect(self.database(s, db_id)) as conn:
                return {"items": [{"name": n, "type": t, "sql": sql} for n,t,sql in conn.execute("SELECT name,type,sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' AND (type='table' OR (type='view' AND ?)) ORDER BY name", (include_views,))]}

    def describe_table(self, db_id, table):
        with self.session() as s:
            with self.connect(self.database(s, db_id)) as conn:
                schema = conn.execute("SELECT type,sql FROM sqlite_schema WHERE name=? AND type IN ('table','view')", (table,)).fetchone()
                if schema is None:
                    raise ValueError("Unknown table/view")
                def dictionaries(cursor):
                    names = [c[0] for c in cursor.description]
                    return [dict(zip(names,row)) for row in cursor]
                return {"table": table, "type": schema[0], "sql": schema[1], "columns": dictionaries(conn.execute("PRAGMA table_xinfo("+quote(table)+")")),
                        "foreign_keys": dictionaries(conn.execute("PRAGMA foreign_key_list("+quote(table)+")")), "indexes": dictionaries(conn.execute("PRAGMA index_list("+quote(table)+")"))}

    def search_schema(self, db_id, query="", offset=0, limit=20):
        with self.session() as s:
            with self.connect(self.database(s, db_id)) as conn:
                items = [{"name": n, "type": t, "table": table, "sql": sql} for n,t,table,sql in conn.execute("SELECT name,type,tbl_name,sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name") if query.casefold() in (n+"\n"+(sql or "")).casefold()]
                return page(items, offset, limit)

    def read_query(self, db_id, sql, parameters=None, limit=100, offset=0):
        with self.session() as s:
            with self.connect(self.database(s, db_id)) as conn:
                conn.set_authorizer(self.authorize("read"))
                return self.query(conn, sql, parameters, limit, offset)

    def explain_query(self, db_id, sql, parameters=None):
        return self.read_query(db_id, "EXPLAIN QUERY PLAN " + sql, parameters, 1000)

    def _mutate(self, db_id, statements, action, mode):
        maximum = 10000 if action == "import_csv" else 100
        if not 1 <= len(statements) <= maximum:
            raise ValueError(f"Provide 1..{maximum} statements/CSV rows")
        with self.session() as s:
            source = self.database(s, db_id)
            with tempfile.TemporaryDirectory(prefix="sqlite-stage-", dir=self.service) as td:
                stage = Path(td) / "working.sqlite"
                with self.connect(source) as original, closing(sqlite3.connect(stage)) as target:
                    original.backup(target)
                with self.connect(stage, False) as conn:
                    conn.execute("PRAGMA journal_mode=DELETE")
                    conn.execute("PRAGMA max_page_count=" + str(self.engine_options.get("max_database_bytes", MAX_FILE) // conn.execute("PRAGMA page_size").fetchone()[0]))
                    audit_name = "audit_" + uuid.uuid4().hex
                    conn.execute("CREATE TEMP TABLE " + quote(audit_name) + " (table_name TEXT, row_id)")
                    for (table,) in conn.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
                        columns = [row[1] for row in conn.execute("PRAGMA table_info(" + quote(table) + ")")]
                        if 'id' in columns:
                            trigger_name = "audit_" + uuid.uuid4().hex
                            conn.execute("CREATE TEMP TRIGGER " + quote(trigger_name) + " BEFORE DELETE ON main." + quote(table) + " BEGIN INSERT INTO " + quote(audit_name) + " VALUES ('" + table.replace("'", "''") + "', OLD.id); END")
                    conn.execute("BEGIN IMMEDIATE")
                    policy = self.authorize(mode)
                    dropped_tables = set()
                    def audit_policy(action, a, b, database, trigger):
                        if action == sqlite3.SQLITE_DROP_TEMP_TRIGGER and a.startswith('audit_'): return sqlite3.SQLITE_OK
                        if action == sqlite3.SQLITE_DROP_TABLE: dropped_tables.add(a)
                        return policy(action, a, b, database, trigger)
                    conn.set_authorizer(audit_policy)
                    ddl_deleted_rows = []
                    results = []
                    for statement in statements:
                        if set(statement) - {"sql", "parameters"} or "sql" not in statement:
                            raise ValueError("Each statement accepts sql and optional parameters")
                        dropped_tables.clear()
                        prior_ids = {}
                        if action != "import_csv":
                            for (table,) in conn.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
                                columns = [r[0] for r in conn.execute("SELECT * FROM " + quote(table) + " LIMIT 0").description]
                                if 'id' in columns: prior_ids[table] = [r[0] for r in conn.execute("SELECT id FROM " + quote(table))]
                        audit_start = conn.execute("SELECT COUNT(*) FROM " + quote(audit_name)).fetchone()[0]
                        start = conn.total_changes
                        result = self.query(conn, statement["sql"], statement.get("parameters"), 1000)
                        result["affected_rows"] = conn.total_changes-start - (conn.execute("SELECT COUNT(*) FROM " + quote(audit_name)).fetchone()[0] - audit_start)
                        ddl_deleted_rows.extend({"table": table, "id": cell(row_id)} for table in dropped_tables for row_id in prior_ids.get(table, []))
                        results.append(result)
                    if mode == "write" and not policy.seen.intersection((sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE)):
                        raise ValueError("write_query/import_csv requires DML")
                    if mode == "schema" and not policy.seen.intersection(getattr(sqlite3, "SQLITE_"+n) for n in ("CREATE_TABLE", "DROP_TABLE", "ALTER_TABLE", "CREATE_INDEX", "DROP_INDEX", "CREATE_VIEW", "DROP_VIEW", "CREATE_TRIGGER", "DROP_TRIGGER", "REINDEX", "ANALYZE")):
                        raise ValueError("execute_schema requires DDL")
                    conn.set_authorizer(None)
                    deleted_rows = ddl_deleted_rows + [{"table": row[0], "id": cell(row[1])} for row in conn.execute("SELECT * FROM " + quote(audit_name))]
                    conn.commit()
                data = self.bytes(stage)
            event_files = {}
            for f in self.workspace.rglob("*"):
                if f.is_file() and f.stat().st_size <= MAX_FILE:
                    event_files[f.relative_to(self.workspace).as_posix()] = base64.b64encode(f.read_bytes()).decode()
            event = {"files_at_commit": event_files, "sequence": s["sequence"]+1, "db_id":db_id,"action":action,"statements":statements,"deleted_rows":deleted_rows}
            codec = zlib.compress if self.engine_options.get("compress_snapshots") else lambda raw: raw
            event.update(snapshot_encoding="zlib" if self.engine_options.get("compress_snapshots") else "raw",before_base64=base64.b64encode(codec(self.bytes(source))).decode(),after_base64=base64.b64encode(codec(data)).decode())
            s.setdefault("mutation_events", []).append(event)
            self.atomic_bytes(self.dbs / (db_id + ".sqlite"), data)
            sequence = self.commit(s)
            details = {"imported_rows": len(results), "affected_rows": sum(r["affected_rows"] for r in results)} if action == "import_csv" else {"results": results}
            return {"sequence": sequence, **details, "sha256": hashlib.sha256(data).hexdigest()}

    def write_query(self, db_id, sql, parameters=None):
        return self._mutate(db_id, [{"sql": sql, "parameters": parameters}], "write_query", "write")

    def execute_schema(self, db_id, sql):
        return self._mutate(db_id, [{"sql": sql}], "execute_schema", "schema")

    def execute_transaction(self, db_id, statements):
        return self._mutate(db_id, statements, "execute_transaction", "transaction")

    def import_csv(self, db_id, table, file_path, null_value=None):
        # Parse and execute under one lock so input and table cannot change mid-call.
        with self.lock:
            path = self.safe(self.files, file_path)
            text = self.bytes(path).decode("utf-8-sig")
            reader = csv.reader(io.StringIO(text, newline="")); headers = next(reader, None)
            if not headers or len(headers) != len(set(headers)) or any(not h for h in headers):
                raise ValueError("CSV requires unique nonempty headers")
            rows = []
            for row in reader:
                if len(row) != len(headers):
                    raise ValueError("CSV row width does not match headers")
                rows.append([None if null_value is not None and v == null_value else v for v in row])
                if len(rows) > 10000:
                    raise ValueError("CSV import supports at most 10000 data rows per call")
            if not rows:
                raise ValueError("CSV has no data rows")
            sql = "INSERT INTO "+quote(table)+" ("+",".join(map(quote, headers))+") VALUES ("+",".join("?" for _ in headers)+")"
            return self._mutate(db_id, [{"sql": sql, "parameters": row} for row in rows], "import_csv", "write")

    def export_query(self, db_id, sql, save_path, parameters=None, format="csv"):
        if format not in ("csv", "json"):
            raise ValueError("format csv/json")
        with self.session() as s:
            target = self.safe(self.files, save_path)
            if target.exists():
                raise FileExistsError(save_path)
            with self.connect(self.database(s, db_id)) as conn:
                conn.set_authorizer(self.authorize("read"))
                raw = execute_bound(conn, sql, parameters, 10001)
                if len(raw["rows"]) > 10000:
                    raise ValueError("Export exceeds 10000 rows; narrow query")
                rows = [[cell(v) for v in row] for row in raw["rows"]]
                if format == "json":
                    data = json.dumps({"columns": raw["columns"], "rows": rows}, ensure_ascii=False, allow_nan=False).encode()
                else:
                    stream = io.StringIO(newline=""); writer = csv.writer(stream); writer.writerow(raw["columns"])
                    writer.writerows([[json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v for v in row] for row in rows]); data = stream.getvalue().encode("utf-8-sig")
            if len(data) > MAX_FILE:
                raise ValueError("Export exceeds 25 MiB")
            self.atomic_bytes(target, data)
            sequence = self.commit(s)
            return {"sequence": sequence, "path": str(target), "row_count": len(rows), "sha256": hashlib.sha256(data).hexdigest()}

    def backup_database(self, db_id, save_path):
        with self.session() as s:
            target = self.safe(self.files, save_path)
            if target.exists():
                raise FileExistsError(save_path)
            with tempfile.TemporaryDirectory(prefix="sqlite-backup-", dir=self.service) as td:
                path = Path(td) / "backup.sqlite"
                with self.connect(self.database(s, db_id)) as source, closing(sqlite3.connect(path)) as dest:
                    source.backup(dest)
                data = self.bytes(path)
            self.atomic_bytes(target, data)
            sequence = self.commit(s)
            return {"sequence": sequence, "path": str(target), "sha256": hashlib.sha256(data).hexdigest()}

    def check_integrity(self, db_id):
        with self.session() as s:
            with self.connect(self.database(s, db_id)) as conn:
                integrity = [r[0] for r in conn.execute("PRAGMA integrity_check")]
                foreign_keys = list(conn.execute("PRAGMA foreign_key_check"))
                return {"ok": integrity == ["ok"] and not foreign_keys, "integrity": integrity, "foreign_key_violations": foreign_keys}
