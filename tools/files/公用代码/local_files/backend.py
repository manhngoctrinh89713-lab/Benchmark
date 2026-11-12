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
from .document_reader import extract as extract_document

MAX_FILE = 25 * 1024 * 1024
MAX_ENTRIES = 10000
MAX_TRANSACTION = 100 * 1024 * 1024
MAX_TEXT = 200000
MAX_LINE = 20000
MAX_LINES = 5000


def digest(data):
    return hashlib.sha256(data).hexdigest()


def page(items, offset, limit):
    if offset < 0 or not 1 <= limit <= 100:
        raise ValueError("offset >= 0; limit 1..100")
    end = offset + limit
    return {"items": items[offset:end], "total": len(items),
            "next_offset": end if end < len(items) else None}


from .workbench import FileWorkbench


class FileStore(FileWorkbench):
    def __init__(self, run_root):
        self.root = Path(run_root).resolve()
        self.workspace = self.root / "workspace"
        self.service = self.root / "services" / "files"
        self.files = self.workspace
        self.state_path = self.service / "state.json"
        self.lock = FileLock(str(self.service / "state.lock"), timeout=10)
        self.files.mkdir(parents=True, exist_ok=True)
        self.service.mkdir(parents=True, exist_ok=True)
        if self.files.is_symlink() or self.files.is_junction():
            raise ValueError("Files root cannot be a link")
        with self.lock:
            if not self.state_path.exists():
                raise ValueError("Missing services/files/state.json; copy the initial environment into the run root first")
            state = self.load_json(self.state_path)
            clock = datetime.fromisoformat(state["now"].replace("Z", "+00:00"))
            if clock.tzinfo is None:
                raise ValueError("now must include a timezone")
            state.setdefault("sequence", 0)

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

    def apply_plan(self, plan):
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

    @contextmanager
    def session(self):
        with self.lock:
            yield self.load_json(self.state_path)

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

    def mutate(self, state, action, plan):
        state = copy.deepcopy(state)
        state["sequence"] += 1
        state["now"] = (datetime.fromisoformat(state["now"].replace("Z", "+00:00")) + timedelta(microseconds=1)).isoformat()
        self.apply_plan(plan)

        # Optional private audit trail. Content hashes allow host evaluators to
        # follow copies and moves without retaining deleted file contents.
        if "mutation_events" in state:
            state["mutation_events"].append({
                "sequence": state["sequence"], "at": state["now"], "action": action,
                "puts": {rel: digest(base64.b64decode(data, validate=True))
                         for rel, data in plan["puts"].items()},
                "deletes": list(plan["deletes"]),
                **({"put_contents": dict(plan["puts"])} if state.get("audit_content") else {}),
            })
        self.atomic_json(self.state_path, state)
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

    def read_text(self, p, encoding="utf-8"):
        data = self.read_bytes(p)
        text = data.decode(encoding)
        if "\x00" in text:
            raise ValueError("Binary file; use read_document for documents")
        return {"path": self.rel(p), "content": text, "sha256": digest(data), "total_lines": len(text.splitlines())}

    def read_document(self, path, offset=0, limit=None, encoding=None):
        if offset < 0:
            raise ValueError("offset must be nonnegative")
        if limit is not None and not 1 <= limit <= MAX_LINES:
            raise ValueError(f"limit must be 1..{MAX_LINES}")
        with self.session():
            p = self.path(path)
            if p.is_dir():
                raise ValueError("Path is a directory; use list_directory or directory_tree")
            data = self.read_bytes(p)
            text, kind, used_encoding, warnings = extract_document(p, data, encoding)
            lines = text.splitlines(keepends=True)
            total = len(lines)
            if offset > total:
                warnings.append(f"offset {offset} is beyond the {total} lines in this file")
            selected = lines[offset:] if limit is None else lines[offset:offset + limit]
            content, truncated, used = [], 0, 0
            for line in selected:
                if len(line) > MAX_LINE:
                    line, truncated = line[:MAX_LINE], truncated + 1
                if used + len(line) > MAX_TEXT:
                    break
                content.append(line)
                used += len(line)
            if truncated:
                warnings.append(f"{truncated} line(s) exceed {MAX_LINE} characters and were truncated")
            end = offset + len(content)
            return {"path": self.rel(p), "format": kind, "content": "".join(content),
                    "characters": used, "total_characters": len(text),
                    "lines": len(content), "total_lines": total,
                    "offset": offset, "next_offset": end if end < total else None,
                    "encoding": used_encoding, "truncated_lines": truncated,
                    "warnings": warnings, "sha256": digest(data)}

    def read_multiple_files(self, paths, encoding=None):
        if not 1 <= len(paths) <= 20:
            raise ValueError("Provide 1..20 file paths")
        with self.session():
            results, used = [], 0
            for value in paths:
                try:
                    p = self.path(value)
                    if p.is_dir():
                        raise ValueError("Path is a directory; read_document reads files only")
                    data = self.read_bytes(p)
                    text, kind, used_encoding, warnings = extract_document(p, data, encoding)
                    if used + len(text) > MAX_TEXT:
                        raise ValueError("Combined output exceeds 200000 characters")
                    used += len(text)
                    results.append({"path": self.rel(p), "format": kind, "content": text,
                                    "characters": len(text), "encoding": used_encoding,
                                    "warnings": warnings, "sha256": digest(data)})
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

    def _write(self, state, p, data, overwrite, action, expected_sha256=None):
        if len(data) > MAX_FILE:
            raise ValueError("File exceeds 25 MiB")
        if p.exists() and not overwrite:
            raise FileExistsError(str(p))
        if p.exists() and not p.is_file():
            raise IsADirectoryError(str(p))
        if expected_sha256 is not None and (not p.exists() or digest(self.read_bytes(p)) != expected_sha256):
            raise ValueError("File changed: expected_sha256 does not match")
        rel = self.rel(p)
        plan = self.empty_plan()
        plan["puts"][rel] = self.encode(data)
        result = self.mutate(state, action, plan)
        return {**result, "path": rel, "size": len(data), "sha256": digest(data)}

    def write_file(self, path, content, overwrite=False, expected_sha256=None):
        with self.session() as s:
            return self._write(s, self.path(path, False), content.encode("utf-8"), overwrite, "write_file", expected_sha256)

    def edit_file(self, path, edits, dry_run=False, expected_sha256=None):
        if not edits:
            raise ValueError("edits cannot be empty")
        with self.session() as s:
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
            return {**self._write(s, p, text.encode("utf-8"), True, "edit_file", expected_sha256), "dry_run": False, "diff": diff}

    def create_directory(self, path):
        with self.session() as s:
            p = self.path(path, False)
            if p.is_dir():
                return {"path": self.rel(p), "created": False}
            if p.exists():
                raise FileExistsError(str(p))
            plan = self.empty_plan()
            plan["mkdirs"] = [self.rel(p)]
            result = self.mutate(s, "create_directory", plan)
            return {**result, "path": self.rel(p), "created": True}

    def transfer(self, source, destination, move):
        with self.session() as s:
            src, dest = self.path(source, False), self.path(destination, False)
            if not src.exists():
                raise FileNotFoundError(str(src))
            if dest.exists():
                raise FileExistsError(str(dest))
            if dest.is_relative_to(src) or src.is_relative_to(dest):
                raise ValueError("Source and destination must not overlap")
            before, plan = self.manifest(src), self.empty_plan()
            for item in before:
                entry = dict(item)
                old = self.path(item["path"], False)
                new = dest / old.relative_to(src) if old != src else dest
                entry["path"] = self.rel(new)
                if item["type"] == "directory":
                    plan["mkdirs"].append(entry["path"])
                    if move:
                        plan["rmdirs"].append(item["path"])
                else:
                    plan["puts"][entry["path"]] = item["content_base64"]
                    if move:
                        plan["deletes"].append(item["path"])
            result = self.mutate(s, "move_file" if move else "copy_file", plan)
            return {**result, "source": self.rel(src), "destination": self.rel(dest)}

    def move_file(self, source, destination):
        return self.transfer(source, destination, True)

    def copy_file(self, source, destination):
        return self.transfer(source, destination, False)

    def delete_file(self, path, recursive=False):
        with self.session() as s:
            p = self.path(path, False)
            before = self.manifest(p)
            if p.is_dir() and len(before) > 1 and not recursive:
                raise ValueError("Nonempty directory requires recursive=true")
            plan = self.empty_plan()
            for item in before:
                plan["rmdirs" if item["type"] == "directory" else "deletes"].append(item["path"])
            return {**self.mutate(s, "delete_file", plan), "path": self.rel(p)}
