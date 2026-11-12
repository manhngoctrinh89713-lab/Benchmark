"""Filesystem boundary for the bundled, trusted Python tools.

This is an application boundary, not an OS sandbox for arbitrary executable code.
The worker never exposes shell, Python execution, or network tools.
"""
import os
import sys
import shlex
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

_scope = ContextVar("tool_root", default=None)
_runtime = (Path(sys.base_prefix).resolve() / "Lib", Path(sys.prefix).resolve() / "Lib")


def check_path(value, root, write=False):
    if value is None or isinstance(value, int):
        return
    raw = os.fsdecode(value)
    if raw == os.devnull:
        return
    path = Path(os.path.abspath(raw))
    # Parsers load Python modules, grammars and document-format resources.
    # These dependency directories are read-only; tool file APIs still enforce
    # their own workspace paths before opening user-supplied filenames.
    if not write and any(path.is_relative_to(base) for base in _runtime):
        return
    if not path.is_relative_to(root) or not path.resolve().is_relative_to(root):
        raise PermissionError("Tool access must stay inside run_root")
    cursor = root
    for part in path.relative_to(root).parts:
        cursor = cursor / part
        if cursor.is_symlink() or cursor.is_junction():
            raise PermissionError("Links and junctions are not allowed")
        if cursor.is_file() and cursor.stat().st_nlink > 1:
            raise PermissionError("Hard links are not allowed")
    if write and any(p.casefold().rstrip(" .") == ".git" for p in path.relative_to(root).parts):
        raise ValueError("Git metadata can only be changed by Git tools")


def audit(event, args):
    root = _scope.get()
    if root is None:
        return
    if event == "open":
        flags = args[2]
        check_path(args[0], root, bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)))
    elif event in {"os.listdir", "os.scandir", "os.chdir"}:
        check_path(args[0] if args else os.getcwd(), root)
    elif event in {"os.remove", "os.rmdir", "os.mkdir", "os.chmod", "os.utime", "os.truncate"}:
        check_path(args[0], root, True)
    elif event in {"os.rename", "os.replace"}:
        check_path(args[0], root, True)
        check_path(args[1], root, True)
    elif event in {"os.symlink", "os.link", "os.system", "os.exec", "os.posix_spawn", "socket.connect", "socket.bind"}:
        raise PermissionError("Tool operation is outside the local sandbox contract")
    elif event == "subprocess.Popen":
        executable, argv, cwd, _env = args
        if isinstance(argv, str):
            argv = [part.strip('"') for part in shlex.split(argv, posix=False)]
        if not isinstance(argv, (list, tuple)) or Path(executable or argv[0]).name.lower() not in {"git", "git.exe"}:
            raise PermissionError("Only managed Git commands are allowed")
        if "-C" in argv:
            cwd = argv[argv.index("-C") + 1]
        check_path(cwd or os.getcwd(), root)
        # A .git file can redirect Git to a host repository.
        git_dir = Path(cwd or os.getcwd()) / ".git"
        check_path(git_dir, root)
        if git_dir.is_file() or (git_dir / "commondir").exists() or (git_dir / "objects/info/alternates").exists():
            raise PermissionError("Only standalone Git repositories are allowed")


sys.addaudithook(audit)


@contextmanager
def tool_scope(root):
    token = _scope.set(Path(root).resolve())
    try:
        yield
    finally:
        _scope.reset(token)


def validate_tree(root):
    root = Path(root).resolve()
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            check_path(Path(directory) / name, root)
