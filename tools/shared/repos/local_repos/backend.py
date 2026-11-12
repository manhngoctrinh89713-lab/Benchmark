import copy
import hashlib
import json
import os
import re
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

import git
from filelock import FileLock
from .git_reads import git_status, git_diff_staged, git_diff_unstaged
from .history import HistoryOperations
from .workbench import GitWorkbench

COLLABORATION_FIELDS = (
    "repositories", "issues", "pull_requests", "comments", "reviews", "labels", "milestones",
    "review_comments", "releases", "workflows", "workflow_runs", "notifications",
)


def page(items, offset=0, limit=20):
    if offset < 0 or not 1 <= limit <= 100:
        raise ValueError("offset >= 0; limit 1..100")
    return {"items": items[offset:offset+limit], "total": len(items),
            "next_offset": offset+limit if offset+limit < len(items) else None}


class RepoStore(GitWorkbench, HistoryOperations):
    SERVICE = "git"

    def __init__(self, run_root):
        self.root = Path(run_root).resolve()
        self.workspace = self.root / "workspace"
        self.repos = self.workspace / "repos"
        self.service = self.root / "services" / self.SERVICE
        self.state_path = self.service / "state.json"
        self.lock = FileLock(str(self.service / "state.lock"), timeout=30)
        self.repos.mkdir(parents=True, exist_ok=True)
        self.service.mkdir(parents=True, exist_ok=True)
        # Never inherit host Git variables, credentials, hooks or custom filters.
        self.git_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.git_env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                            GIT_TERMINAL_PROMPT="0", GIT_LITERAL_PATHSPECS="1")
        self.read_env = {k: None for k in os.environ if k.startswith("GIT_")}
        self.read_env.update(self.git_env)
        with self.lock:
            if not self.state_path.exists():
                raise ValueError(f"Missing services/{self.SERVICE}/state.json; copy the initial environment into the run root first")
            s = self.load(self.state_path)
            clock = datetime.fromisoformat(s["now"].replace("Z", "+00:00"))
            if clock.tzinfo is None:
                raise ValueError("now requires timezone")
            names = [r["id"] for r in s["repositories"]]
            if len(names) != len(set(names)) or any(not re.fullmatch(r"[A-Za-z0-9_-]+", n) for n in names):
                raise ValueError("Repository IDs must be unique simple names")
            for field in COLLABORATION_FIELDS:
                s.setdefault(field, [])
            s.setdefault("sequence", 0)
            for r in s["repositories"]:
                if not (self.repos / r["id"] / ".git").is_dir():
                    raise ValueError("Snapshot is missing repository " + r["id"])

    @staticmethod
    def load(p):
        return json.loads(p.read_text(encoding="utf-8"))

    @staticmethod
    def atomic(p, data):
        fd, name = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2); f.flush(); os.fsync(f.fileno())
            os.replace(name, p)
        finally:
            Path(name).unlink(missing_ok=True)

    @contextmanager
    def session(self, action=None, arguments=None):
        with self.lock:
            s = self.load(self.state_path)
            for field in COLLABORATION_FIELDS:
                s.setdefault(field, [])
            counters = s.setdefault("id_counters", {})
            for field in COLLABORATION_FIELDS:
                values = [row["id"] for row in s[field] if isinstance(row.get("id"), int)]
                counters[field] = max([counters.get(field, 0), *values])
            for repo in s["repositories"]:
                counter_key = "milestones/"+repo["id"]
                counters[counter_key] = max([counters.get(counter_key, 0), *[row["number"] for row in s["milestones"] if row["repo_id"] == repo["id"]]])
            yield s
            if action:
                s["sequence"] += 1
                s["now"] = (datetime.fromisoformat(s["now"].replace("Z", "+00:00")) + timedelta(seconds=1)).isoformat()
                self.atomic(self.state_path, s)

    def run_result(self, root, *args, clock=None):
        env = dict(self.git_env)
        env.update(GIT_EDITOR="true", GIT_SEQUENCE_EDITOR="true", GIT_MERGE_AUTOEDIT="no")
        if clock:
            env.update(GIT_AUTHOR_DATE=clock, GIT_COMMITTER_DATE=clock)
        command = ["git", "-c", "core.hooksPath=" + os.devnull, "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", "-c", "core.quotePath=false",
                   "-c", "user.name=Benchmark User", "-c", "user.email=benchmark@example.test", "-c", "diff.external=", "-c", "protocol.allow=never", "-C", str(root), *args]
        r = subprocess.run(command, env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=30,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if len(r.stdout) > 2 * 1024 * 1024:
            raise ValueError("Git output exceeds 2 MiB; narrow the request")
        return r

    def run(self, root, *args, clock=None):
        r = self.run_result(root, *args, clock=clock)
        if r.returncode:
            raise ValueError((r.stderr or r.stdout).decode("utf-8", "replace")[:8000])
        return r.stdout.decode("utf-8", "replace")

    def init_remotes(self, root, record):
        remotes = record.setdefault("remotes", [])
        if not isinstance(remotes, list):
            raise ValueError("remotes must be a list")
        names = set()
        for remote in remotes:
            name, url = remote.get("name"), remote.get("url")
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
                raise ValueError("Invalid remote name")
            if name in names:
                raise ValueError("Duplicate remote name")
            if not isinstance(url, str) or not url.strip():
                raise ValueError("Remote URL cannot be empty")
            refs = remote.setdefault("refs", {})
            if not isinstance(refs, dict):
                raise ValueError("Remote refs must be an object")
            normalized = {}
            for branch, revision in refs.items():
                if not isinstance(branch, str) or not branch:
                    raise ValueError("Invalid remote branch")
                ref = f"refs/remotes/{name}/{branch}"
                self.run(root, "check-ref-format", ref)
                sha = self.ref(root, revision)
                self.run(root, "update-ref", ref, sha)
                normalized[branch] = sha
            remote["refs"] = normalized
            names.add(name)

    @staticmethod
    def repo_record(s, repo_id):
        record = next((x for x in s["repositories"] if x["id"] == repo_id), None)
        if record is None:
            raise ValueError("Unknown repository")
        return record

    def repo(self, s, repo_id):
        if not any(r["id"] == repo_id for r in s["repositories"]):
            raise ValueError("Unknown repository")
        p = self.repos / repo_id
        if not (p / ".git").is_dir() or (p / ".git").is_symlink():
            raise ValueError("Only managed standalone Git repositories are supported")
        # Disallow custom repository config (filters, includes, aliases, etc.).
        cfg = self.run(p, "config", "--local", "--list")
        if any(line.split("=", 1)[0].lower() not in {"core.repositoryformatversion", "core.filemode", "core.bare", "core.logallrefupdates", "core.symlinks", "core.ignorecase"} for line in cfg.splitlines()):
            raise ValueError("Unexpected local Git configuration")
        return p

    def ref(self, p, value):
        if not value or value.startswith("-") or any(c in value for c in ("\x00", "\n", ":")):
            raise ValueError("Invalid Git revision")
        return self.run(p, "rev-parse", "--verify", value + "^{commit}").strip()

    def file(self, root, value):
        p = (root / value).resolve()
        if not p.is_relative_to(root) or p == root or any(x.casefold().rstrip(" .") == ".git" for x in p.relative_to(root).parts) or ":" in value:
            raise ValueError("File path must stay in working tree, outside .git")
        return p

    def list_repositories(self):
        with self.session() as s:
            return {"items": [{**r, "path": str(self.repos / r["id"])} for r in s["repositories"]]}

    def git_status(self, repo_id):
        with self.session() as s:
            p = self.repo(s, repo_id)
            with git.Repo(p) as repo, repo.git.custom_environment(**self.read_env):
                return {"text": git_status(repo)}

    def git_diff(self, repo_id, mode="unstaged", base=None, head=None):
        with self.session() as s:
            p = self.repo(s, repo_id)
            if mode in ("unstaged", "staged"):
                with git.Repo(p) as repo, repo.git.custom_environment(**self.read_env):
                    return {"diff": (git_diff_staged if mode == "staged" else git_diff_unstaged)(repo)}
            if mode != "refs" or not base or not head:
                raise ValueError("mode unstaged/staged/refs; refs requires base and head")
            return {"diff": self.run(p, "diff", "--no-ext-diff", "--no-textconv", self.ref(p, base), self.ref(p, head), "--")}

    def git_log(self, repo_id, revision="HEAD", limit=20):
        if not 1 <= limit <= 100:
            raise ValueError("limit 1..100")
        with self.session() as s:
            p = self.repo(s, repo_id)
            return {"text": self.run(p, "log", f"-{limit}", "--format=%H %aI %s", self.ref(p, revision), "--")}

    def git_show(self, repo_id, revision="HEAD"):
        with self.session() as s:
            p = self.repo(s, repo_id)
            return {"text": self.run(p, "show", "--no-ext-diff", "--no-textconv", self.ref(p, revision), "--")}

    def git_branches(self, repo_id):
        with self.session() as s:
            return {"text": self.run(self.repo(s, repo_id), "branch", "--list", "--format=%(refname:short) %(objectname) %(HEAD)")}

    def git_create_branch(self, repo_id, branch, base="HEAD"):
        with self.session("git_create_branch", locals_payload(repo_id=repo_id, branch=branch, base=base)) as s:
            p = self.repo(s, repo_id)
            if branch.startswith("-"):
                raise ValueError("Invalid branch")
            self.run(p, "check-ref-format", "--branch", branch)
            self.run(p, "branch", branch, self.ref(p, base))
            return {"branch": branch}

    def git_checkout(self, repo_id, branch):
        with self.session("git_checkout", {"repo_id": repo_id, "branch": branch}) as s:
            p = self.repo(s, repo_id)
            if self.run(p, "status", "--porcelain"):
                raise ValueError("Checkout requires clean working tree and index")
            self.run(p, "show-ref", "--verify", "refs/heads/" + branch)
            self.run(p, "switch", "--", branch)
            return {"branch": branch}

    def git_add(self, repo_id, paths):
        with self.session("git_add", {"repo_id": repo_id, "paths": paths}) as s:
            p = self.repo(s, repo_id)
            if not paths:
                raise ValueError("paths cannot be empty")
            for value in paths:
                if value != ".":
                    self.file(p, value)
            self.run(p, "add", "--", *paths)
            return {"staged": paths}

    def git_reset(self, repo_id):
        with self.session("git_reset", {"repo_id": repo_id}) as s:
            self.run(self.repo(s, repo_id), "reset", "--mixed", "HEAD", "--")
            return {"unstaged": True}

    def git_commit(self, repo_id, message):
        if not message.strip():
            raise ValueError("Commit message cannot be empty")
        with self.session("git_commit", {"repo_id": repo_id, "message": message}) as s:
            p = self.repo(s, repo_id)
            if not self.run(p, "diff", "--cached", "--name-only"):
                raise ValueError("No staged changes")
            self.run(p, "commit", "-m", message, clock=s["now"])
            return {"sha": self.ref(p, "HEAD")}

    def git_remote(self, repo_id, operation="list", name=None, url=None):
        if operation not in ("list", "add", "remove"):
            raise ValueError("operation list/add/remove")
        if operation == "list":
            with self.session() as s:
                self.repo(s, repo_id)
                record = self.repo_record(s, repo_id)
                return {"remotes": copy.deepcopy(record.get("remotes", []))}
        if operation == "add":
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
                raise ValueError("Invalid remote name")
            if not isinstance(url, str) or not url.strip():
                raise ValueError("Remote URL cannot be empty")
            with self.session("git_remote_add", {"repo_id": repo_id, "name": name, "url": url}) as s:
                self.repo(s, repo_id)
                record = self.repo_record(s, repo_id)
                remotes = record.setdefault("remotes", [])
                if any(x["name"] == name for x in remotes):
                    raise ValueError("Remote already exists")
                item = {"name": name, "url": url, "refs": {}}
                remotes.append(item)
                return {"remote": copy.deepcopy(item)}
        if not isinstance(name, str) or not name:
            raise ValueError("name is required for remove")
        with self.session("git_remote_remove", {"repo_id": repo_id, "name": name}) as s:
            p = self.repo(s, repo_id)
            record = self.repo_record(s, repo_id)
            remotes = record.setdefault("remotes", [])
            item = next((x for x in remotes if x["name"] == name), None)
            if item is None:
                raise ValueError("Unknown remote")
            prefix = f"refs/remotes/{name}/"
            for ref in self.run(p, "for-each-ref", "--format=%(refname)", prefix).splitlines():
                if ref:
                    self.run(p, "update-ref", "-d", ref)
            remotes.remove(item)
            return {"removed": name}

    def git_push(self, repo_id, remote, branch, remote_branch=None, force=False):
        if not isinstance(force, bool):
            raise ValueError("force must be boolean")
        remote_branch = remote_branch or branch
        with self.session("git_push", {"repo_id": repo_id, "remote": remote,
                                       "branch": branch, "remote_branch": remote_branch,
                                       "force": force}) as s:
            p = self.repo(s, repo_id)
            record = self.repo_record(s, repo_id)
            item = next((x for x in record.get("remotes", []) if x["name"] == remote), None)
            if item is None:
                raise ValueError("Unknown remote")
            self.run(p, "check-ref-format", f"refs/remotes/{remote}/{remote_branch}")
            new = self.ref(p, branch)
            old = item.setdefault("refs", {}).get(remote_branch)
            if old == new:
                return {"remote": remote, "branch": remote_branch, "old_sha": old,
                        "new_sha": new, "forced": False, "up_to_date": True}
            if old and not force:
                try:
                    self.run(p, "merge-base", "--is-ancestor", old, new)
                except ValueError:
                    raise ValueError("Non-fast-forward push requires force=true")
            item["refs"][remote_branch] = new
            self.run(p, "update-ref", f"refs/remotes/{remote}/{remote_branch}", new)
            # Keep each published tree even if a later push restores the branch.
            s.setdefault("push_events", []).append({
                "repo_id": repo_id, "remote": remote, "branch": remote_branch,
                "old_sha": old, "new_sha": new, "force": force,
                "tree": self.run(p, "ls-tree", "-r", new).splitlines(),
                "ancestors": self.run(p, "rev-list", new).splitlines(),
            })
            return {"remote": remote, "branch": remote_branch, "old_sha": old,
                    "new_sha": new, "forced": bool(force and old and old != new),
                    "up_to_date": False}

    def git_fetch(self, repo_id, remote, branch=None, prune=False):
        if not isinstance(prune, bool):
            raise ValueError("prune must be boolean")
        with self.session("git_fetch", {"repo_id": repo_id, "remote": remote,
                                        "branch": branch, "prune": prune}) as s:
            p = self.repo(s, repo_id)
            record = self.repo_record(s, repo_id)
            item = next((x for x in record.get("remotes", []) if x["name"] == remote), None)
            if item is None:
                raise ValueError("Unknown remote")
            refs = item.setdefault("refs", {})
            if branch is not None and branch not in refs:
                raise ValueError("Unknown remote branch")
            selected = {branch: refs[branch]} if branch is not None else dict(refs)
            fetched = []
            for name, sha in selected.items():
                ref = f"refs/remotes/{remote}/{name}"
                self.run(p, "check-ref-format", ref)
                try:
                    old = self.run(p, "rev-parse", "--verify", ref).strip()
                except ValueError:
                    old = None
                self.run(p, "update-ref", ref, sha)
                fetched.append({"branch": name, "sha": sha, "old_sha": old})
            pruned = []
            if prune:
                prefix = f"refs/remotes/{remote}/"
                for ref in self.run(p, "for-each-ref", "--format=%(refname)", prefix).splitlines():
                    if not ref:
                        continue
                    name = ref[len(prefix):]
                    if name not in refs:
                        self.run(p, "update-ref", "-d", ref)
                        pruned.append(name)
            return {"remote": remote, "fetched": fetched, "pruned": pruned}

    def read_repository_file(self, repo_id, path, revision=None):
        with self.session() as s:
            p = self.repo(s, repo_id); f = self.file(p, path)
            if revision:
                rel = f.relative_to(p).as_posix()
                content = self.run(p, "show", self.ref(p, revision) + ":" + rel)
            else:
                content = f.read_text(encoding="utf-8")
            if len(content) > 200000:
                raise ValueError("File output exceeds 200000 characters")
            return {"path": path, "content": content}

    def write_repository_file(self, repo_id, path, content, overwrite=False):
        with self.session("write_repository_file", {"repo_id": repo_id, "path": path}) as s:
            p = self.file(self.repo(s, repo_id), path)
            if p.exists() and not overwrite:
                raise FileExistsError(path)
            if len(content.encode()) > 1024 * 1024:
                raise ValueError("Text file exceeds 1 MiB")
            p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(content.encode())
            return {"path": path, "sha256": hashlib.sha256(content.encode()).hexdigest()}



def locals_payload(**kwargs):
    return kwargs
