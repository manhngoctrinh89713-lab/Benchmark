"""Database lifecycle, restore and structured schema inspection."""
import hashlib
import re
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path


class DatabaseWorkbench:
    def create_database(self, db_id: str, name: str) -> dict:
        """创建空 SQLite 数据库并登记显示名称。"""
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", db_id) or not name.strip() or len(name) > 200:
            raise ValueError("Invalid database ID or name")
        with self.session() as s:
            target = self.safe(self.dbs, db_id+".sqlite")
            if any(d["id"] == db_id for d in s["databases"]) or target.exists():
                raise FileExistsError(db_id)
            with tempfile.TemporaryDirectory(dir=self.service) as tmp:
                stage = Path(tmp)/"new.sqlite"
                with closing(sqlite3.connect(stage)) as conn:
                    conn.execute("PRAGMA user_version=0")
                    conn.commit()
                raw = self.bytes(stage)
            self.atomic_bytes(target, raw)
            record = {"id": db_id, "name": name}
            s["databases"].append(record)
            s.setdefault("lifecycle_events", []).append({"action": "create", "db_id": db_id, "at": s["now"]})
            return {"database": record, "sequence": self.commit(s)}

    def rename_database(self, db_id: str, name: str) -> dict:
        """修改数据库显示名称，数据库 ID 和 SQL 内容保持稳定。"""
        if not name.strip() or len(name) > 200:
            raise ValueError("Invalid name")
        with self.session() as s:
            self.database(s, db_id)
            record = next(d for d in s["databases"] if d["id"] == db_id)
            record["name"] = name
            return {"database": record, "sequence": self.commit(s)}

    def delete_database(self, db_id: str, expected_sha256: str) -> dict:
        """删除指定数据库并记录删除前快照，按当前文件校验值核对目标。"""
        import base64
        with self.session() as s:
            target = self.database(s, db_id)
            raw = self.bytes(target)
            if hashlib.sha256(raw).hexdigest() != expected_sha256:
                raise ValueError("Database changed")
            s.setdefault("lifecycle_events", []).append({"action": "delete", "db_id": db_id, "at": s["now"], "snapshot_base64": base64.b64encode(raw).decode()})
            target.unlink()
            s["databases"] = [d for d in s["databases"] if d["id"] != db_id]
            return {"deleted_db_id": db_id, "sequence": self.commit(s)}

    def restore_database(self, db_id: str, file_path: str, expected_sha256: str) -> dict:
        """用工作区内的 SQLite 备份替换已登记数据库，核对当前校验值及备份完整性。"""
        import base64
        with self.session() as s:
            target = self.database(s, db_id)
            before = self.bytes(target)
            if hashlib.sha256(before).hexdigest() != expected_sha256:
                raise ValueError("Database changed")
            source = self.safe(self.files, file_path)
            self.standalone(source)
            raw = self.bytes(source)
            with self.connect(source) as conn:
                if conn.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                    raise ValueError("Backup integrity check failed")
            s.setdefault("lifecycle_events", []).append({"action": "restore", "db_id": db_id, "at": s["now"], "before_base64": base64.b64encode(before).decode(), "after_base64": base64.b64encode(raw).decode()})
            self.atomic_bytes(target, raw)
            return {"db_id": db_id, "sha256": hashlib.sha256(raw).hexdigest(), "sequence": self.commit(s)}

    def list_indexes(self, db_id: str, table: str | None = None) -> dict:
        """查询数据库索引、列顺序和唯一性。"""
        from .backend import quote
        with self.session() as s:
            with self.connect(self.database(s, db_id)) as conn:
                tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name") if table is None or r[0] == table]
                result = []
                for name in tables:
                    for idx in conn.execute("PRAGMA index_list("+quote(name)+")"):
                        result.append({"table": name, "name": idx[1], "unique": bool(idx[2]), "origin": idx[3], "partial": bool(idx[4]), "columns": [{"sequence": r[0], "column": r[2], "descending": bool(r[3]), "collation": r[4]} for r in conn.execute("PRAGMA index_xinfo("+quote(idx[1])+")") if r[5]]})
                return {"indexes": result}

    def list_relationships(self, db_id: str) -> dict:
        """列出表之间的外键关系及更新、删除行为。"""
        from .backend import quote
        with self.session() as s:
            with self.connect(self.database(s, db_id)) as conn:
                result = []
                for (name,) in conn.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
                    result.extend({"table": name, "foreign_key_id": r[0], "sequence": r[1], "referenced_table": r[2], "column": r[3], "referenced_column": r[4], "on_update": r[5], "on_delete": r[6]} for r in conn.execute("PRAGMA foreign_key_list("+quote(name)+")"))
                return {"relationships": result}

    def get_table_statistics(self, db_id: str, table: str) -> dict:
        """读取表行数、每列空值数和不同值数量。"""
        from .backend import quote
        with self.session() as s:
            with self.connect(self.database(s, db_id)) as conn:
                if not conn.execute("SELECT 1 FROM sqlite_schema WHERE name=? AND type IN ('table','view')", (table,)).fetchone():
                    raise ValueError("Unknown table or view")
                conn.set_authorizer(self.authorize("read"))
                columns = [r[0] for r in conn.execute("SELECT * FROM "+quote(table)+" LIMIT 0").description]
                count = conn.execute("SELECT COUNT(*) FROM "+quote(table)).fetchone()[0]
                rows = []
                for column in columns:
                    nonnull, distinct = conn.execute("SELECT COUNT("+quote(column)+"),COUNT(DISTINCT "+quote(column)+") FROM "+quote(table)).fetchone()
                    rows.append({"column": column, "null_count": count-nonnull, "distinct_count": distinct})
                return {"table": table, "row_count": count, "columns": rows}
