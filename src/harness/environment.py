"""Run-environment lifecycle: case lookup, directories, locks, reset and save.

Everything here operates on the host copies under ``运行环境/``; the model never
sees these paths.  Private-directory hardening lives here too because it is
applied immediately after a fixture is copied.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from filelock import FileLock

from .catalog import ROOT
from .sandbox import validate_tree
from .transport import write_json


def initial_case(name):
    parent = (ROOT / "初始环境").resolve()
    source = (parent / name).resolve()
    if source.parent != parent or not source.is_dir():
        raise ValueError("case 必须是初始环境下的一个用例目录")
    validate_tree(source)
    if not (source / "workspace").is_dir() or not (source / "services").is_dir():
        raise ValueError("用例必须包含 workspace/ 和 services/")
    return source


def manifest(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def model_directory(model="deepseek-flash"):
    # Keep common model names readable; encode provider/model IDs and Windows
    # reserved names without allowing paths or ambiguous filename mappings.
    name = model.casefold()
    if (re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,99}", name)
            and not name.endswith(".")
            and name.split(".")[0] not in {"con", "prn", "aux", "nul", *[f"{p}{n}" for p in ("com", "lpt") for n in range(1, 10)]}):
        return name
    return "model-" + hashlib.sha256(model.encode("utf-8")).hexdigest()


def case_directory(case="综合测试"):
    # Use a digest to keep case keys safe and case-insensitive on Windows.
    return "case-" + hashlib.sha256(case.casefold().encode("utf-8")).hexdigest()


def environment_directory(model="deepseek-flash", case="综合测试"):
    return ROOT / "运行环境" / model_directory(model) / case_directory(case)


def model_lock(model="deepseek-flash", case="综合测试"):
    records = ROOT / "运行记录"
    records.mkdir(exist_ok=True)
    return FileLock(str(records / (".runner-" + model_directory(model) + "-" + case_directory(case) + ".lock")), timeout=0)


def reset_environment(source, model="deepseek-flash"):
    parent = ROOT / "运行环境"
    run_root = environment_directory(model, source.name)
    # Only this model/case directory may be replaced recursively.
    if run_root.resolve() != run_root.absolute() or source.resolve().is_relative_to(parent.resolve()):
        raise ValueError("运行目录必须是项目下的真实运行环境目录")
    validate_tree(source)
    if run_root.exists():
        validate_tree(run_root)
        shutil.rmtree(run_root, onexc=lambda fn, path, exc: (os.chmod(path, 0o700), fn(path)))
    shutil.copytree(source, run_root)
    apply_private_directories(run_root)
    return run_root


def save_environment(run_root, record):
    validate_tree(run_root)
    shutil.copytree(run_root, record / "final_environment")
    write_json(record / "final_manifest.json", manifest(record / "final_environment"))


def apply_private_directories(root, create=True):
    """Apply host-enforced private workspace directories after copying a fixture."""
    root = Path(root).resolve()
    state = root / 'services/files/state.json'
    if not state.exists():
        return
    paths = json.loads(state.read_text(encoding='utf-8')).get('private_directories', [])
    workspace = (root / 'workspace').resolve()
    sid = None
    if paths and os.name == 'nt':
        identity = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'],
                                  check=True, capture_output=True, text=True)
        sid = re.search(r'S-1-5-\d+(?:-\d+)+', identity.stdout).group()
    for relative in paths:
        directory = (workspace / relative).resolve()
        if directory == workspace or not directory.is_relative_to(workspace):
            raise ValueError('Private directory must be inside workspace')
        if not create and not directory.exists():
            continue
        directory.mkdir(parents=True, exist_ok=True)
        if os.name == 'nt':
            subprocess.run(['icacls', str(directory), '/inheritance:r', '/grant:r',
                            f'*{sid}:(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'],
                           check=True, capture_output=True)
            # Same-volume moves can retain a file's old Windows DACL. Reset
            # children to inherit the private parent's ACL, including moved keys.
            for child in directory.iterdir():
                if child.is_symlink():
                    raise ValueError('Private store cannot contain symbolic links')
                subprocess.run(['icacls', str(child), '/reset', '/T', '/Q'],
                               check=True, capture_output=True)
        else:
            directory.chmod(0o700)
            for child in directory.rglob('*'):
                if child.is_symlink():
                    raise ValueError('Private store cannot contain symbolic links')
                child.chmod(0o700 if child.is_dir() else 0o600)
