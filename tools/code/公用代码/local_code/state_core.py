# Extracted from the sibling file module; project-owned persistence.
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
MAX_FILE = 25 * 1024 * 1024
MAX_ENTRIES = 10000
MAX_TRANSACTION = 100 * 1024 * 1024
MAX_TEXT = 200000

def digest(data):
    return hashlib.sha256(data).hexdigest()

def page(items, offset, limit):
    if offset < 0 or not 1 <= limit <= 100:
        raise ValueError('offset >= 0; limit 1..100')
    end = offset + limit
    return {'items': items[offset:end], 'total': len(items), 'next_offset': end if end < len(items) else None}

class CodeState:

    def __init__(self, run_root):
        self.root = Path(run_root).resolve()
        self.workspace = self.root / 'workspace'
        self.service = self.root / 'services' / 'code'
        self.files = self.workspace
        self.state_path = self.service / 'state.json'
        self.lock = FileLock(str(self.service / 'state.lock'), timeout=10)
        self.files.mkdir(parents=True, exist_ok=True)
        self.service.mkdir(parents=True, exist_ok=True)
        if self.files.is_symlink() or self.files.is_junction():
            raise ValueError('Files root cannot be a link')
        with self.lock:
            if not self.state_path.exists():
                raise ValueError('Missing services/code/state.json; copy the initial environment into the run root first')
            state = self.load_json(self.state_path)
            clock = datetime.fromisoformat(state['now'].replace('Z', '+00:00'))
            if clock.tzinfo is None:
                raise ValueError('now must include a timezone')
            state.setdefault('sequence', 0)

    @staticmethod
    def load_json(p):
        return json.loads(p.read_text(encoding='utf-8'))

    @staticmethod
    def atomic_json(path, data):
        CodeState.atomic_bytes(path, (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))

    @staticmethod
    def atomic_bytes(path, data):
        fd, name = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)

    @staticmethod
    def encode(data):
        return base64.b64encode(data).decode('ascii')

    @staticmethod
    def read_bytes(p):
        with p.open('rb') as f:
            data = f.read(MAX_FILE + 1)
        if len(data) > MAX_FILE:
            raise ValueError('File exceeds 25 MiB')
        return data

    @staticmethod
    def check_entry(p):
        if p.is_symlink() or p.is_junction():
            raise ValueError(f'Links/junctions are not supported: {p.name}')
        if p.exists() and p.is_file() and (p.stat().st_nlink > 1):
            raise ValueError(f'Hard-linked files are not supported: {p.name}')

    def path(self, value, allow_root=True):
        if not value or ':' in str(value).replace(str(Path(value).drive), '', 1):
            raise ValueError('Empty paths and alternate data streams are not supported')
        p = Path(value)
        p = p if p.is_absolute() else self.files / p
        lexical = Path(os.path.abspath(p))
        if not lexical.is_relative_to(self.files):
            raise ValueError("Path must be inside this run's files directory")
        current = self.files
        self.check_entry(current)
        for part in lexical.relative_to(self.files).parts:
            current = current / part
            self.check_entry(current)
            if current != lexical and current.exists() and (not current.is_dir()):
                raise NotADirectoryError(f'Parent path is not a directory: {current.name}')
        resolved = lexical.resolve()
        if not resolved.is_relative_to(self.files) or (not allow_root and resolved == self.files):
            raise ValueError('Cannot modify the files root or escape the running files directory')
        return resolved

    @staticmethod
    def walk_root(root):
        if not root.exists():
            return []
        CodeState.check_entry(root)
        result = []
        stack = [root]
        while stack:
            directory = stack.pop()
            for p in sorted(directory.iterdir(), key=lambda p: p.name.casefold()):
                CodeState.check_entry(p)
                if not p.is_file() and (not p.is_dir()):
                    raise ValueError('Only regular files and directories are supported')
                result.append(p)
                if len(result) > MAX_ENTRIES:
                    raise ValueError('Tree exceeds 10000 entries; narrow the path')
                if p.is_dir():
                    stack.append(p)
        return sorted(result, key=lambda p: p.as_posix())

    def apply_plan(self, plan):
        for rel in sorted(plan['mkdirs'], key=lambda x: len(Path(x).parts)):
            self.path(rel, False).mkdir(parents=True, exist_ok=True)
        for rel, content in plan['puts'].items():
            dest = self.path(rel, False)
            dest.parent.mkdir(parents=True, exist_ok=True)
            self.atomic_bytes(dest, base64.b64decode(content, validate=True))
        for rel in plan['deletes']:
            self.path(rel, False).unlink(missing_ok=True)
        for rel in sorted(plan['rmdirs'], key=lambda x: len(Path(x).parts), reverse=True):
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
        result, size = ([], 0)
        for x in entries:
            item = {'path': self.rel(x), 'type': 'directory' if x.is_dir() else 'file'}
            if x.is_file():
                data = self.read_bytes(x)
                size += len(data)
                if size > MAX_TRANSACTION:
                    raise ValueError('Transaction exceeds 100 MiB')
                item.update(sha256=digest(data), content_base64=self.encode(data))
            result.append(item)
        return result

    def mutate(self, state, action, plan):
        state = copy.deepcopy(state)
        state['sequence'] += 1
        state['now'] = (datetime.fromisoformat(state['now'].replace('Z', '+00:00')) + timedelta(microseconds=1)).isoformat()
        self.apply_plan(plan)
        self.atomic_json(self.state_path, state)
        return {'sequence': state['sequence'], 'action': action}

    @staticmethod
    def empty_plan():
        return {'puts': {}, 'mkdirs': [], 'deletes': [], 'rmdirs': []}
