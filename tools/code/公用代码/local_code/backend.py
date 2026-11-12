"""Real project files with structural edits and recoverable multi-file commits."""
import difflib
import fnmatch
import hashlib
import keyword
import re
import textwrap
import threading
from pathlib import Path

import jedi

from . import analysis
from .state_core import CodeState, MAX_TEXT, digest, page

JEDI_LOCK = threading.RLock()
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache"}


def normalize(text):
    return text.replace("\r\n", "\n")


from .workbench import CodeWorkbench


class CodeStore(CodeWorkbench, CodeState):
    def __init__(self, run_root):
        super().__init__(run_root)
        state = self.load_json(self.state_path)
        self.projects = state.get("projects", [])
        ids = [p["id"] for p in self.projects]
        if not ids or len(ids) != len(set(ids)) or any(not re.fullmatch(r"[A-Za-z0-9_-]+", x) for x in ids):
            raise ValueError("projects require unique simple IDs")
        paths = []
        for project in self.projects:
            path = Path(project["path"])
            if path.is_absolute() or not path.parts or ".." in path.parts or ":" in str(path):
                raise ValueError("Project paths must be relative to the workspace")
            if any(path.is_relative_to(p) or p.is_relative_to(path) for p in paths):
                raise ValueError("Projects must not overlap")
            paths.append(path)
            if not (self.workspace / path).is_dir():
                raise ValueError("Initial project must be an existing directory")

    def project(self, project_id):
        projects = self.load_json(self.state_path).get("projects", [])
        project = next((p for p in projects if p["id"] == project_id), None)
        if project is None:
            raise ValueError("Unknown project ID")
        root = self.path(project["path"])
        if not root.is_dir():
            raise NotADirectoryError(str(root))
        return root

    def code_path(self, project_id, path, allow_root=False):
        root = self.project(project_id)
        p = Path(path)
        target = self.path(str(p if p.is_absolute() else root / p))
        if not target.is_relative_to(root) or (target == root and not allow_root):
            raise ValueError("Path must stay inside the selected project")
        if any(part in SKIP_DIRS for part in target.relative_to(root).parts):
            raise ValueError("Generated/dependency/internal directories are excluded")
        return target

    def code_files(self, project_id):
        root = self.project(project_id); stack = [root]; found = []; visited = 0
        while stack:
            folder = stack.pop()
            for p in sorted(folder.iterdir()):
                if p.name in SKIP_DIRS:
                    continue
                visited += 1
                if visited > 10000:
                    raise ValueError("Project exceeds 10000 entries")
                self.code_path(project_id, str(p))
                if p.is_dir():
                    stack.append(p)
                elif p.is_file():
                    found.append(p)
                else:
                    raise ValueError("Only regular files are supported")
        return sorted(found)

    def text(self, path):
        data = self.read_bytes(path)
        text = data.decode("utf-8-sig")
        if "\x00" in text or len(text) > MAX_TEXT:
            raise ValueError("Expected UTF-8 text with at most 200000 characters")
        return data, text

    @staticmethod
    def encode_text(text, original=b""):
        if len(text) > MAX_TEXT or "\x00" in text:
            raise ValueError("Expected text with at most 200000 characters and no NUL")
        return (b"\xef\xbb\xbf" if original.startswith(b"\xef\xbb\xbf") else b"") + text.encode("utf-8")

    @staticmethod
    def fragment(text, original):
        return normalize(text).replace("\n", "\r\n") if "\r\n" in original else normalize(text)

    def list_projects(self):
        with self.session():
            projects = self.load_json(self.state_path).get("projects", [])
            return {"items": [{"id": p["id"], "name": p.get("name", p["id"]), "root": str(self.project(p["id"]))} for p in projects], "structural_languages": sorted(analysis.QUERIES.keys() | {"tsx"}), "semantic_languages": ["python"]}

    def list_code_files(self, project_id, pattern="*", offset=0, limit=50):
        with self.session():
            root = self.project(project_id)
            items = [{"path": p.relative_to(root).as_posix(), "size": p.stat().st_size, "language": analysis.EXTENSIONS.get(p.suffix.lower())} for p in self.code_files(project_id) if fnmatch.fnmatchcase(p.relative_to(root).as_posix(), pattern)]
            return page(items, offset, limit)

    def read_code(self, project_id, path, start_line=1, end_line=None):
        with self.session():
            data, text = self.text(self.code_path(project_id, path)); lines = text.splitlines(keepends=True)
            end = len(lines) if end_line is None else end_line
            if start_line < 1 or end < 0 or (end < start_line and not (not lines and start_line == 1 and end == 0)):
                raise ValueError("Use one-based inclusive line ranges")
            return {"path": path, "content": "".join(lines[start_line-1:end]), "start_line": start_line, "end_line": min(end, len(lines)), "total_lines": len(lines), "sha256": digest(data)}

    def search_code(self, project_id, query, pattern="*", case_sensitive=True, offset=0, limit=20):
        if not query:
            raise ValueError("query cannot be empty")
        with self.session():
            root = self.project(project_id); found, skipped = [], []
            for p in self.code_files(project_id):
                rel = p.relative_to(root).as_posix()
                if not fnmatch.fnmatchcase(rel, pattern):
                    continue
                try:
                    _, text = self.text(p)
                except (UnicodeError, ValueError) as exc:
                    skipped.append({"path": rel, "error": str(exc)}); continue
                for line, content in enumerate(text.splitlines(), 1):
                    if (query if case_sensitive else query.casefold()) in (content if case_sensitive else content.casefold()):
                        found.append({"path": rel, "line": line, "text": content[:2000]})
                        if len(found) > 10000:
                            raise ValueError("More than 10000 matches; narrow query")
            return {**page(found, offset, limit), "skipped": skipped}

    def get_symbols_overview(self, project_id, path, offset=0, limit=50):
        with self.session():
            data, text = self.text(self.code_path(project_id, path))
            return {**page([analysis.public_symbol(s, text) for s in analysis.symbols(path, text)], offset, limit), "sha256": digest(data)}

    def find_symbol(self, project_id, name, path=None, include_body=False, offset=0, limit=20):
        if not name:
            raise ValueError("name cannot be empty")
        with self.session():
            root = self.project(project_id)
            files = [self.code_path(project_id, path)] if path is not None else self.code_files(project_id)
            matches, skipped, size = [], [], 0
            for p in files:
                if p.suffix.lower() not in analysis.EXTENSIONS:
                    continue
                rel = p.relative_to(root).as_posix()
                try:
                    data, text = self.text(p); found = analysis.symbols(p, text)
                except (UnicodeError, ValueError) as exc:
                    skipped.append({"path": rel, "error": str(exc)}); continue
                for item in found:
                    if name in item["name_path"]:
                        # Include bodies only for the requested page.
                        hit = {"path": rel, **analysis.public_symbol(item, text, include_body and offset <= len(matches) < offset+limit), "sha256": digest(data)}
                        size += len(str(hit))
                        if size > 1000000:
                            raise ValueError("Result too large; narrow symbol search")
                        matches.append(hit)
            return {**page(matches, offset, limit), "skipped": skipped}

    def get_diagnostics(self, project_id, path):
        with self.session():
            data, text = self.text(self.code_path(project_id, path))
            return {"path": path, "sha256": digest(data), **analysis.diagnostics(path, text)}

    def _apply(self, state, project_id, changes, action, dry_run=False, validate_syntax=False):
        if not 1 <= len(changes) <= 100:
            raise ValueError("Provide 1..100 file changes")
        results, plan, seen = [], self.empty_plan(), set()
        for change in changes:
            if set(change) - {"path", "content", "expected_sha256"} or not {"path", "content"} <= set(change):
                raise ValueError("Each change requires path/content and optional expected_sha256; content null deletes")
            p = self.code_path(project_id, change["path"])
            if str(p).casefold() in seen:
                raise ValueError("Duplicate target path")
            seen.add(str(p).casefold())
            if p.exists() and not p.is_file():
                raise IsADirectoryError(str(p))
            raw, old = self.text(p) if p.exists() else (None, "")
            expected = change.get("expected_sha256")
            if expected is not None and (raw is None or digest(raw) != expected):
                raise ValueError("File changed: expected_sha256 does not match")
            content = change["content"]
            if content is None and raw is None:
                raise FileNotFoundError(str(p))
            if content is not None and not isinstance(content, str):
                raise ValueError("content must be string or null")
            data = None if content is None else self.encode_text(content, raw or b"")
            if data is not None and validate_syntax and p.suffix.lower() in analysis.EXTENSIONS:
                check = analysis.diagnostics(p, content)
                if not check["ok"]:
                    raise ValueError("New code fails syntax validation: " + str(check["diagnostics"]))
            rel = self.rel(p)
            if data is None:
                plan["deletes"].append(rel)
            else:
                plan["puts"][rel] = self.encode(data)
            delta = "".join(difflib.unified_diff(normalize(old).splitlines(keepends=True), normalize(content or "").splitlines(keepends=True), fromfile=change["path"] if raw is not None else "/dev/null", tofile=change["path"] if data is not None else "/dev/null"))
            results.append({"path": change["path"], "before_sha256": digest(raw) if raw is not None else None, "sha256": digest(data) if data is not None else None, "deleted": data is None, "diff": delta})
        if sum(len(r["diff"]) for r in results) > MAX_TEXT:
            raise ValueError("Combined diff exceeds 200000 characters")
        # Parent/child target collisions must fail before writing pending.
        targets = [self.code_path(project_id, c["path"]) for c in changes]
        if any(a != b and a in b.parents for a in targets for b in targets):
            raise ValueError("Target file paths must not nest")
        if dry_run:
            return {"dry_run": True, "changes": results}
        committed = self.mutate(state, action, plan)
        return {**committed, "dry_run": False, "changes": results}

    def apply_workspace_edit(self, project_id, changes, dry_run=False, validate_syntax=False):
        with self.session() as s:
            return self._apply(s, project_id, changes, "apply_workspace_edit", dry_run, validate_syntax)

    def create_code_file(self, project_id, path, content, validate_syntax=False):
        with self.session() as s:
            if self.code_path(project_id, path).exists():
                raise FileExistsError(path)
            return self._apply(s, project_id, [{"path": path, "content": content}], "create_code_file", validate_syntax=validate_syntax)

    def replace_text(self, project_id, path, edits, expected_sha256=None, dry_run=False, validate_syntax=False):
        if not 1 <= len(edits) <= 100:
            raise ValueError("Provide 1..100 edits")
        with self.session() as s:
            raw, original = self.text(self.code_path(project_id, path)); text = original
            for edit in edits:
                if set(edit) - {"old_text", "new_text", "expected_count"} or not {"old_text", "new_text"} <= set(edit):
                    raise ValueError("Each edit requires old_text/new_text and optional expected_count")
                old, new = self.fragment(edit["old_text"], original), self.fragment(edit["new_text"], original)
                count = edit.get("expected_count", 1)
                if not old or type(count) is not int or count < 1 or text.count(old) != count:
                    raise ValueError("old_text must match expected_count exactly")
                text = text.replace(old, new)
            return self._apply(s, project_id, [{"path": path, "content": text, "expected_sha256": expected_sha256}], "replace_text", dry_run, validate_syntax)

    def replace_lines(self, project_id, path, start_line, end_line, content, expected_sha256=None, dry_run=False, validate_syntax=False):
        with self.session() as s:
            _, old = self.text(self.code_path(project_id, path)); lines = old.splitlines(keepends=True)
            if not 1 <= start_line <= len(lines)+1 or not start_line-1 <= end_line <= len(lines):
                raise ValueError("One-based inclusive range; end_line=start_line-1 inserts")
            fragment = self.fragment(content, old)
            if fragment and end_line < len(lines) and not fragment.endswith("\n"):
                fragment += "\r\n" if "\r\n" in old else "\n"
            if start_line == len(lines)+1 and old and not old.endswith("\n") and fragment:
                fragment = ("\r\n" if "\r\n" in old else "\n") + fragment
            text = "".join(lines[:start_line-1]) + fragment + "".join(lines[end_line:])
            return self._apply(s, project_id, [{"path": path, "content": text, "expected_sha256": expected_sha256}], "replace_lines", dry_run, validate_syntax)

    def replace_symbol_body(self, project_id, path, name_path, body, expected_sha256=None, dry_run=False, validate_syntax=True):
        with self.session() as s:
            _, old = self.text(self.code_path(project_id, path)); item = analysis.select_symbol(path, old, name_path)
            data = old.encode("utf-8"); start, end = item["start_byte"], item["end_byte"]
            prefix = data[data.rfind(b"\n", 0, start)+1:start].decode()
            indent = prefix if not prefix.strip() else ""
            value = textwrap.dedent(normalize(body)).rstrip("\n")
            if not value.strip():
                raise ValueError("body must contain the full replacement definition")
            value = value.replace("\n", "\n"+indent)
            value = self.fragment(value, old)
            text = (data[:start] + value.encode() + data[end:]).decode()
            return self._apply(s, project_id, [{"path": path, "content": text, "expected_sha256": expected_sha256}], "replace_symbol_body", dry_run, validate_syntax)

    def insert_relative_to_symbol(self, project_id, path, name_path, content, position="after", expected_sha256=None, dry_run=False, validate_syntax=True):
        if position not in ("before", "after") or not content.strip():
            raise ValueError("Use before/after and nonempty content")
        with self.session() as s:
            _, old = self.text(self.code_path(project_id, path)); item = analysis.select_symbol(path, old, name_path)
            data = old.encode(); start, end = item["start_byte"], item["end_byte"]
            line_start = data.rfind(b"\n", 0, start)+1
            line_end = data.find(b"\n", end)
            line_end = len(data) if line_end == -1 else line_end+1
            indent = data[line_start:start].decode()
            if indent.strip() or data[end:line_end].strip():
                raise ValueError("Symbol must occupy complete lines; use replace_text for inline declarations")
            value = textwrap.dedent(normalize(content)).strip("\n")
            value = self.fragment("\n".join(indent+line if line else "" for line in value.split("\n"))+"\n", old)
            offset = line_start if position == "before" else line_end
            if position == "after" and offset and not data[:offset].endswith(b"\n"):
                value = ("\r\n" if "\r\n" in old else "\n") + value
            text = (data[:offset]+value.encode()+data[offset:]).decode()
            return self._apply(s, project_id, [{"path": path, "content": text, "expected_sha256": expected_sha256}], "insert_relative_to_symbol", dry_run, validate_syntax)

    def python_script(self, project_id, path, line, column):
        p = self.code_path(project_id, path)
        if p.suffix.lower() not in (".py", ".pyi"):
            raise ValueError("Semantic references/rename currently support Python only")
        _, text = self.text(p); lines = text.splitlines()
        if not 1 <= line <= len(lines) or not 0 <= column <= len(lines[line-1]):
            raise ValueError("Use one-based line and zero-based character column")
        # Validate the whole project before Jedi follows local modules.
        for file in self.code_files(project_id):
            if file.suffix.lower() in (".py", ".pyi"):
                self.text(file)
        project = jedi.Project(self.project(project_id), sys_path=[str(self.project(project_id))], smart_sys_path=False, load_unsafe_extensions=False)
        return jedi.Script(text, path=p, project=project)

    def find_references(self, project_id, path, line, column, offset=0, limit=50):
        with self.session(), JEDI_LOCK:
            script = self.python_script(project_id, path, line, column); root = self.project(project_id)
            matches = []
            for ref in script.get_references(line, column, include_builtins=False, scope="project"):
                if ref.module_path is None or not Path(ref.module_path).is_relative_to(root):
                    continue
                target = self.code_path(project_id, str(ref.module_path))
                matches.append({"path": target.relative_to(root).as_posix(), "name": ref.name, "line": ref.line, "column": ref.column, "is_definition": ref.is_definition()})
            matches.sort(key=lambda r: (r["path"], r["line"], r["column"]))
            return {**page(matches, offset, limit), "analysis": "jedi-static-python"}

    def rename_symbol(self, project_id, path, line, column, new_name, dry_run=False):
        if not new_name.isidentifier() or keyword.iskeyword(new_name):
            raise ValueError("new_name must be a valid non-keyword Python identifier")
        with self.session() as s, JEDI_LOCK:
            script = self.python_script(project_id, path, line, column)
            refactoring = script.rename(line, column, new_name=new_name)
            if refactoring.get_renames():
                raise ValueError("Module/file renaming is outside symbol rename; use workspace edits")
            changes = []
            root = self.project(project_id)
            for file, changed in refactoring.get_changed_files().items():
                target = self.code_path(project_id, str(file)); raw, original = self.text(target)
                code = self.fragment(normalize(changed.get_new_code()), original)
                changes.append({"path": target.relative_to(root).as_posix(), "content": code, "expected_sha256": digest(raw)})
            if not changes:
                raise ValueError("No statically resolved symbol changes")
            return self._apply(s, project_id, changes, "rename_symbol", dry_run, True)

    def get_changes(self, project_id, include_diff=False, offset=0, limit=20):
        with self.session():
            root = self.project(project_id)
            initial = self.service / "baseline" / project_id
            if not initial.is_dir():
                raise ValueError("Missing services/code/baseline/" + project_id)
            before = {p.relative_to(initial).as_posix(): p for p in self.walk_root(initial) if p.is_file() and not any(part in SKIP_DIRS for part in p.relative_to(initial).parts)}
            after = {p.relative_to(root).as_posix(): p for p in self.code_files(project_id)}
            changes = []
            for name in sorted(before.keys() | after.keys()):
                def fingerprint(path):
                    with path.open('rb') as stream:
                        return hashlib.file_digest(stream, 'sha256').hexdigest()
                a = fingerprint(before[name]) if name in before else None
                b = fingerprint(after[name]) if name in after else None
                if a == b:
                    continue
                changes.append({"path": name, "status": "created" if a is None else "deleted" if b is None else "modified", "before_sha256": a, "sha256": b})
            result = page(changes, offset, limit); size = 0
            if include_diff:
                for item in result["items"]:
                    name = item["path"]
                    try:
                        a = self.text(before[name])[1] if name in before else ""
                        b = self.text(after[name])[1] if name in after else ""
                        delta = "".join(difflib.unified_diff(normalize(a).splitlines(keepends=True), normalize(b).splitlines(keepends=True), fromfile=name, tofile=name))
                        size += len(delta)
                        if size > MAX_TEXT:
                            raise ValueError("Diff too large; narrow page")
                        item["diff"] = delta
                    except UnicodeError:
                        item["binary"] = True
            return result
