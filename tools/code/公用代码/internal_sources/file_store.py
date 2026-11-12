"""Real files as state, with separate immutable templates and mutation records."""
import base64
import copy
import difflib
import fnmatch
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from filelock import FileLock
from .document_converter import convert_document

MAX_FILE = 25 * 1024 * 1024
MAX_ENTRIES = 10000
MAX_TRANSACTION = 100 * 1024 * 1024
MAX_TEXT = 200000


def digest(data):
    return hashlib.sha256(data).hexdigest()


def page(items, offset, limit):
    if offset < 0 or not 1 <= limit <= 100:
        raise ValueError("offset >= 0; limit 1..100")
    end = offset + limit
    return {"items": items[offset:end], "total": len(items),
            "next_offset": end if end < len(items) else None}


class FileStore:
    def __init__(self, initial_data, environment_dir, record_dir):
        self.scenario = Path(initial_data).resolve()
        self.environment_dir = Path(environment_dir).resolve()
        self.record_dir = Path(record_dir).resolve()
        areas = [self.scenario.parent, self.environment_dir, self.record_dir]
        for i, a in enumerate(areas):
            for b in areas[i + 1:]:
                if a.is_relative_to(b) or b.is_relative_to(a):
                    raise ValueError("Initial, running and record directories must not overlap")
        self.environment_dir.mkdir(parents=True, exist_ok=True)
        self.record_dir.mkdir(parents=True, exist_ok=True)
        self.files = self.environment_dir / "files"
        self.files.mkdir(exist_ok=True)
        if self.files.is_symlink() or self.files.is_junction():
            raise ValueError("Files root cannot be a link")
        self.state_path = self.environment_dir / "state.json"
        self.events_path = self.record_dir / "events.json"
        self.pending_path = self.record_dir / "pending.json"
        self.lock = FileLock(str(self.environment_dir / "state.lock"), timeout=10)
        with self.lock:
            self.recover()
            fingerprint = self.initial_fingerprint()
            if self.state_path.exists():
                state = self.load_json(self.state_path)
                if state.get("record_dir") != str(self.record_dir) or not self.events_path.exists():
                    raise ValueError("Environment and records do not match")
                if state.get("initial_sha256") != fingerprint:
                    raise ValueError("Initial template changed; choose a new run")
            else:
                if self.events_path.exists() or any(self.files.iterdir()):
                    raise ValueError("Use empty environment and record directories for a new run")
                config = self.load_json(self.scenario)
                clock = datetime.fromisoformat(config["now"].replace("Z", "+00:00"))
                if clock.tzinfo is None:
                    raise ValueError("now must include a timezone")
                state = {"now": config["now"], "initial_sha256": fingerprint,
                         "record_dir": str(self.record_dir), "sequence": 0}
                puts, dirs = {}, []
                source = self.scenario.parent / "files"
                for p in self.walk_root(source):
                    rel = p.relative_to(source).as_posix()
                    self.path(rel)
                    if p.is_dir():
                        dirs.append(rel)
                    else:
                        puts[rel] = self.encode(self.read_bytes(p))
                self.commit(state, [], {"puts": puts, "mkdirs": dirs, "deletes": [], "rmdirs": []})

    @staticmethod
    def load_json(p):
        return json.loads(p.read_text(encoding="utf-8"))

    @staticmethod
    def atomic_json(path, data):
        FileStore.atomic_bytes(path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    @staticmethod
    def atomic_bytes(path, data):
        fd, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)

    @staticmethod
    def encode(data):
        return base64.b64encode(data).decode("ascii")

    @staticmethod
    def read_bytes(p):
        with p.open("rb") as f:
            data = f.read(MAX_FILE + 1)
        if len(data) > MAX_FILE:
            raise ValueError("File exceeds 25 MiB")
        return data

    @staticmethod
    def check_entry(p):
        if p.is_symlink() or p.is_junction():
            raise ValueError(f"Links/junctions are not supported: {p.name}")
        if p.exists() and p.is_file() and p.stat().st_nlink > 1:
            raise ValueError(f"Hard-linked files are not supported: {p.name}")

    def path(self, value, allow_root=True):
        if not value or ":" in str(value).replace(str(Path(value).drive), "", 1):
            raise ValueError("Empty paths and alternate data streams are not supported")
        p = Path(value)
        p = p if p.is_absolute() else self.files / p
        # Check every lexical component before resolving links, including '..'.
        lexical = Path(os.path.abspath(p))
        if not lexical.is_relative_to(self.files):
            raise ValueError("Path must be inside this run's files directory")
        current = self.files
        self.check_entry(current)
        for part in lexical.relative_to(self.files).parts:
            current = current / part
            self.check_entry(current)
            if current != lexical and current.exists() and not current.is_dir():
                raise NotADirectoryError(f"Parent path is not a directory: {current.name}")
        resolved = lexical.resolve()
        if not resolved.is_relative_to(self.files) or (not allow_root and resolved == self.files):
            raise ValueError("Cannot modify the files root or escape the running files directory")
        return resolved

    @staticmethod
    def walk_root(root):
        if not root.exists():
            return []
        FileStore.check_entry(root)
        result = []
        stack = [root]
        while stack:
            directory = stack.pop()
            for p in sorted(directory.iterdir(), key=lambda p: p.name.casefold()):
                FileStore.check_entry(p)
                if not p.is_file() and not p.is_dir():
                    raise ValueError("Only regular files and directories are supported")
                result.append(p)
                if len(result) > MAX_ENTRIES:
                    raise ValueError("Tree exceeds 10000 entries; narrow the path")
                if p.is_dir():
                    stack.append(p)
        return sorted(result, key=lambda p: p.as_posix())

    def initial_fingerprint(self):
        source = self.scenario.parent / "files"
        h = hashlib.sha256(self.scenario.read_bytes())
        for p in self.walk_root(source):
            h.update(json.dumps([p.relative_to(source).as_posix(), "directory" if p.is_dir() else digest(self.read_bytes(p))], ensure_ascii=False).encode())
        return h.hexdigest()

    def recover(self):
        if not self.pending_path.exists():
            return
        p = self.load_json(self.pending_path)
        if p["environment_dir"] != str(self.environment_dir) or p["state"]["record_dir"] != str(self.record_dir):
            raise ValueError("Pending commit belongs to another run")
        plan = p["plan"]
        for rel in sorted(plan["mkdirs"], key=lambda x: len(Path(x).parts)):
            self.path(rel, False).mkdir(parents=True, exist_ok=True)
        for rel, content in plan["puts"].items():
            dest = self.path(rel, False)
            dest.parent.mkdir(parents=True, exist_ok=True)
            self.atomic_bytes(dest, base64.b64decode(content, validate=True))
        for rel in plan["deletes"]:
            self.path(rel, False).unlink(missing_ok=True)
        for rel in sorted(plan["rmdirs"], key=lambda x: len(Path(x).parts), reverse=True):
            dest = self.path(rel, False)
            if dest.exists():
                dest.rmdir()
        self.atomic_json(self.state_path, p["state"])
        self.atomic_json(self.events_path, p["events"])
        self.pending_path.unlink()

    def commit(self, state, events, plan):
        if sum(len(v) * 3 // 4 for v in plan["puts"].values()) > MAX_TRANSACTION:
            raise ValueError("Transaction exceeds 100 MiB")
        self.atomic_json(self.pending_path, {"environment_dir": str(self.environment_dir),
                                           "state": state, "events": events, "plan": plan})
        self.recover()

    @contextmanager
    def session(self):
        with self.lock:
            self.recover()
            yield self.load_json(self.state_path), self.load_json(self.events_path)

    def rel(self, p):
        return p.relative_to(self.files).as_posix()

    def manifest(self, p):
        entries = [p] + (self.walk_root(p) if p.is_dir() else [])
        result, size = [], 0
        for x in entries:
            item = {"path": self.rel(x), "type": "directory" if x.is_dir() else "file"}
            if x.is_file():
                data = self.read_bytes(x)
                size += len(data)
                if size > MAX_TRANSACTION:
                    raise ValueError("Transaction exceeds 100 MiB")
                item.update(sha256=digest(data), content_base64=self.encode(data))
            result.append(item)
        return result

    def mutate(self, state, events, action, plan, before, after):
        state = copy.deepcopy(state)
        state["sequence"] += 1
        state["now"] = (datetime.fromisoformat(state["now"].replace("Z", "+00:00")) + timedelta(microseconds=1)).isoformat()
        event = {"sequence": state["sequence"], "timestamp": state["now"], "action": action,
                 "before": before, "after": after}
        self.commit(state, events + [event], plan)
        return {"sequence": state["sequence"], "action": action}

    @staticmethod
    def empty_plan():
        return {"puts": {}, "mkdirs": [], "deletes": [], "rmdirs": []}

    def info(self, p):
        stat = p.stat()
        return {"path": self.rel(p), "name": p.name, "type": "directory" if p.is_dir() else "file",
                "size": stat.st_size, "modified_ns": stat.st_mtime_ns,
                **({} if p.is_dir() else {"sha256": digest(self.read_bytes(p))})}

    def list_allowed_directories(self):
        return {"directories": [str(self.files)], "relative_path_base": str(self.files)}

    def get_file_info(self, path):
        with self.session():
            return self.info(self.path(path))

    def list_directory(self, path=".", offset=0, limit=100):
        with self.session():
            p = self.path(path)
            entries = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.casefold(), x.name))
            if len(entries) > MAX_ENTRIES:
                raise ValueError("Directory exceeds 10000 entries")
            for x in entries:
                self.path(str(x))
            return page([self.info(x) for x in entries], offset, limit)

    @staticmethod
    def matches(rel, pattern):
        return fnmatch.fnmatchcase(rel.casefold(), pattern.casefold()) or fnmatch.fnmatchcase(Path(rel).name.casefold(), pattern.casefold())

    def walk(self, path, exclude_patterns=None, max_depth=None):
        root = self.path(path)
        if not root.is_dir():
            raise NotADirectoryError(str(root))
        result, stack, count = [], [(root, 0)], 0
        while stack:
            parent, depth = stack.pop()
            for p in sorted(parent.iterdir(), key=lambda x: x.name.casefold()):
                rel = p.relative_to(root).as_posix()
                count += 1
                if count > MAX_ENTRIES:
                    raise ValueError("Tree exceeds 10000 entries; narrow the path")
                if any(self.matches(rel, pat) for pat in (exclude_patterns or [])):
                    continue
                self.path(str(p))
                result.append(p)
                if p.is_dir() and (max_depth is None or depth + 1 < max_depth):
                    stack.append((p, depth + 1))
        return root, sorted(result, key=lambda p: p.as_posix().casefold())

    def directory_tree(self, path=".", max_depth=4, exclude_patterns=None):
        if not 1 <= max_depth <= 20:
            raise ValueError("max_depth must be 1..20")
        with self.session():
            root, entries = self.walk(path, exclude_patterns, max_depth)
            nodes = {root: {"path": self.rel(root), "type": "directory", "children": []}}
            for p in sorted(entries, key=lambda x: len(x.parts)):
                node = {"path": self.rel(p), "type": "directory" if p.is_dir() else "file"}
                if p.is_dir():
                    node["children"] = []
                    node["depth_limited"] = len(p.relative_to(root).parts) == max_depth
                nodes[p] = node
                nodes[p.parent]["children"].append(node)
            return nodes[root]

    def search_files(self, path=".", pattern="*", exclude_patterns=None, offset=0, limit=100):
        with self.session():
            root, entries = self.walk(path, exclude_patterns)
            hits = [self.info(p) for p in entries if self.matches(p.relative_to(root).as_posix(), pattern)]
            return page(hits, offset, limit)

    def read_text(self, p, encoding="utf-8", head=None, tail=None):
        if encoding not in ("utf-8", "utf-8-sig", "gb18030", "utf-16"):
            raise ValueError("encoding must be utf-8/utf-8-sig/gb18030/utf-16")
        if head is not None and tail is not None:
            raise ValueError("head and tail cannot be combined")
        if any(x is not None and x < 0 for x in (head, tail)):
            raise ValueError("head/tail must be nonnegative")
        data = self.read_bytes(p)
        text = data.decode(encoding)
        if "\x00" in text:
            raise ValueError("Binary file; use convert_to_markdown for documents")
        lines = text.splitlines(keepends=True)
        text = "".join(lines[:head]) if head is not None else "".join(lines[-tail:]) if tail else "" if tail == 0 else text
        if len(text) > MAX_TEXT:
            raise ValueError("Text output exceeds 200000 characters; use head/tail")
        return {"path": self.rel(p), "content": text, "sha256": digest(data), "total_lines": len(lines)}

    def read_text_file(self, path, head=None, tail=None, encoding="utf-8"):
        with self.session():
            return self.read_text(self.path(path), encoding, head, tail)

    def read_multiple_files(self, paths, encoding="utf-8"):
        if not 1 <= len(paths) <= 20:
            raise ValueError("Provide 1..20 file paths")
        with self.session():
            results, count = [], 0
            for value in paths:
                try:
                    item = self.read_text(self.path(value), encoding)
                    if count + len(item["content"]) > MAX_TEXT:
                        raise ValueError("Combined output exceeds 200000 characters")
                    count += len(item["content"])
                    results.append(item)
                except (OSError, ValueError) as exc:
                    results.append({"path": value, "error": str(exc)})
            return {"items": results}

    def search_content(self, query, path=".", pattern="*", case_sensitive=False, offset=0, limit=20):
        if not query:
            raise ValueError("query cannot be empty")
        with self.session():
            root, entries = self.walk(path)
            hits, skipped = [], []
            needle = query if case_sensitive else query.casefold()
            for p in entries:
                if not p.is_file() or not self.matches(p.relative_to(root).as_posix(), pattern):
                    continue
                try:
                    data = self.read_bytes(p)
                    text = data.decode("utf-8-sig")
                    if "\x00" in text:
                        raise ValueError("binary")
                except (ValueError, OSError) as exc:
                    skipped.append({"path": self.rel(p), "error": str(exc)})
                    continue
                for i, line in enumerate(text.splitlines(), 1):
                    if needle in (line if case_sensitive else line.casefold()):
                        hits.append({"path": self.rel(p), "line": i, "text": line[:2000]})
                        if len(hits) > MAX_ENTRIES:
                            raise ValueError("More than 10000 matches; narrow query")
            return {**page(hits, offset, limit), "skipped": skipped}

    def _write(self, state, events, p, data, overwrite, action, expected_sha256=None):
        if len(data) > MAX_FILE:
            raise ValueError("File exceeds 25 MiB")
        if p.exists() and not overwrite:
            raise FileExistsError(str(p))
        if p.exists() and not p.is_file():
            raise IsADirectoryError(str(p))
        if expected_sha256 is not None and (not p.exists() or digest(self.read_bytes(p)) != expected_sha256):
            raise ValueError("File changed: expected_sha256 does not match")
        before = self.manifest(p) if p.exists() else []
        rel = self.rel(p)
        after = [{"path": rel, "type": "file", "sha256": digest(data), "content_base64": self.encode(data)}]
        plan = self.empty_plan()
        plan["puts"][rel] = self.encode(data)
        result = self.mutate(state, events, action, plan, before, after)
        return {**result, "path": rel, "size": len(data), "sha256": digest(data)}

    def write_file(self, path, content, overwrite=False, expected_sha256=None):
        with self.session() as (s, e):
            return self._write(s, e, self.path(path, False), content.encode("utf-8"), overwrite, "write_file", expected_sha256)

    def edit_file(self, path, edits, dry_run=False, expected_sha256=None):
        if not edits:
            raise ValueError("edits cannot be empty")
        with self.session() as (s, e):
            p = self.path(path, False)
            original = self.read_text(p)["content"]
            eol = "\r\n" if "\n" in original and original[original.index("\n") - 1:original.index("\n")] == "\r" else "\n"
            text = original.replace("\r\n", "\n")
            for edit in edits:
                if set(edit) != {"oldText", "newText"} or not all(isinstance(v, str) for v in edit.values()):
                    raise ValueError("Each edit requires only string oldText/newText")
                old, new = edit["oldText"].replace("\r\n", "\n"), edit["newText"].replace("\r\n", "\n")
                if not old or text.count(old) != 1:
                    raise ValueError("oldText must match exactly once")
                text = text.replace(old, new, 1)
            if expected_sha256 is not None and digest(self.read_bytes(p)) != expected_sha256:
                raise ValueError("File changed: expected_sha256 does not match")
            diff = "".join(difflib.unified_diff(original.splitlines(keepends=True), text.splitlines(keepends=True), fromfile=self.rel(p), tofile=self.rel(p)))
            if dry_run:
                return {"dry_run": True, "diff": diff, "sha256": digest(self.read_bytes(p))}
            if eol == "\r\n":
                text = text.replace("\n", "\r\n")
            return {**self._write(s, e, p, text.encode("utf-8"), True, "edit_file", expected_sha256), "dry_run": False, "diff": diff}

    def create_directory(self, path):
        with self.session() as (s, e):
            p = self.path(path, False)
            if p.is_dir():
                return {"path": self.rel(p), "created": False}
            if p.exists():
                raise FileExistsError(str(p))
            plan = self.empty_plan()
            plan["mkdirs"] = [self.rel(p)]
            result = self.mutate(s, e, "create_directory", plan, [], [{"path": self.rel(p), "type": "directory"}])
            return {**result, "path": self.rel(p), "created": True}

    def transfer(self, source, destination, move):
        with self.session() as (s, e):
            src, dest = self.path(source, False), self.path(destination, False)
            if not src.exists():
                raise FileNotFoundError(str(src))
            if dest.exists():
                raise FileExistsError(str(dest))
            if dest.is_relative_to(src) or src.is_relative_to(dest):
                raise ValueError("Source and destination must not overlap")
            before, after, plan = self.manifest(src), [], self.empty_plan()
            for item in before:
                entry = dict(item)
                old = self.path(item["path"], False)
                new = dest / old.relative_to(src) if old != src else dest
                entry["path"] = self.rel(new)
                after.append(entry)
                if item["type"] == "directory":
                    plan["mkdirs"].append(entry["path"])
                    if move:
                        plan["rmdirs"].append(item["path"])
                else:
                    plan["puts"][entry["path"]] = item["content_base64"]
                    if move:
                        plan["deletes"].append(item["path"])
            result = self.mutate(s, e, "move_file" if move else "copy_file", plan, before, after)
            return {**result, "source": self.rel(src), "destination": self.rel(dest)}

    def move_file(self, source, destination):
        return self.transfer(source, destination, True)

    def copy_file(self, source, destination):
        return self.transfer(source, destination, False)

    def delete_file(self, path, recursive=False):
        with self.session() as (s, e):
            p = self.path(path, False)
            before = self.manifest(p)
            if p.is_dir() and len(before) > 1 and not recursive:
                raise ValueError("Nonempty directory requires recursive=true")
            plan = self.empty_plan()
            for item in before:
                plan["rmdirs" if item["type"] == "directory" else "deletes"].append(item["path"])
            return {**self.mutate(s, e, "delete_file", plan, before, []), "path": self.rel(p)}

    def convert_to_markdown(self, path, save_path=None):
        with self.session() as (s, e):
            source = self.path(path)
            if source.suffix.casefold() not in {".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".html", ".htm", ".csv", ".txt", ".md", ".json", ".xml"}:
                raise ValueError("Unsupported document extension")
            self.read_bytes(source)
            text = convert_document(str(source))
            result = {"path": self.rel(source), "markdown": text[:MAX_TEXT], "characters": len(text),
                      "truncated": len(text) > MAX_TEXT, "empty": not text.strip()}
            if save_path is not None:
                target = self.path(save_path, False)
                if target.suffix.casefold() != ".md":
                    raise ValueError("save_path must end with .md")
                result["saved"] = self._write(s, e, target, text.encode("utf-8"), False, "convert_to_markdown")
            return result
