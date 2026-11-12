"""Everyday Git lifecycle operations using the shared Git command runner."""
import re


class GitWorkbench:
    def git_tags(self, repo_id: str) -> dict:
        """列出轻量和附注标签及其提交标识。"""
        with self.session() as s:
            return {"text": self.run(self.repo(s, repo_id), "for-each-ref", "--format=%(refname:short) %(objectname) %(*objectname) %(subject)", "refs/tags/")}

    def git_create_tag(self, repo_id: str, tag: str, revision: str = "HEAD", message: str | None = None) -> dict:
        """在指定提交创建轻量标签，提供说明时创建附注标签。"""
        with self.session("git_create_tag", {"repo_id": repo_id, "tag": tag, "revision": revision, "message": message}) as s:
            root = self.repo(s, repo_id)
            self.run(root, "check-ref-format", "refs/tags/"+tag)
            if tag.startswith("-"):
                raise ValueError("Invalid tag")
            sha = self.ref(root, revision)
            args = ["tag"]
            if message is not None:
                if not message.strip():
                    raise ValueError("Tag message is empty")
                args.extend(["-a", "-m", message])
            self.run(root, *args, "--", tag, sha, clock=s["now"])
            return {"tag": tag, "commit": sha}

    def git_delete_tag(self, repo_id: str, tag: str) -> dict:
        """删除本地标签。"""
        with self.session("git_delete_tag", {"repo_id": repo_id, "tag": tag}) as s:
            root = self.repo(s, repo_id)
            self.run(root, "check-ref-format", "refs/tags/"+tag)
            old = self.run(root, "rev-parse", "--verify", "refs/tags/"+tag).strip()
            self.run(root, "update-ref", "-d", "refs/tags/"+tag, old)
            return {"deleted_tag": tag, "previous_object": old}

    def git_delete_branch(self, repo_id: str, branch: str, force: bool = False) -> dict:
        """删除本地分支；默认要求分支已合并。"""
        with self.session("git_delete_branch", {"repo_id": repo_id, "branch": branch, "force": force}) as s:
            root = self.repo(s, repo_id)
            self.run(root, "check-ref-format", "refs/heads/"+branch)
            return {"text": self.run(root, "branch", "-D" if force else "-d", "--", branch)}

    def git_rename_branch(self, repo_id: str, branch: str, new_name: str) -> dict:
        """重命名本地分支，目标名称已存在时失败。"""
        with self.session("git_rename_branch", {"repo_id": repo_id, "branch": branch, "new_name": new_name}) as s:
            root = self.repo(s, repo_id)
            for value in (branch, new_name):
                self.run(root, "check-ref-format", "refs/heads/"+value)
                if value.startswith("-"):
                    raise ValueError("Invalid branch")
            return {"text": self.run(root, "branch", "-m", branch, new_name)}

    def git_unstage(self, repo_id: str, paths: list[str]) -> dict:
        """撤销指定路径的暂存，保留工作区修改。"""
        with self.session("git_unstage", {"repo_id": repo_id, "paths": paths}) as s:
            root = self.repo(s, repo_id)
            self._check_paths(root, paths)
            return {"text": self.run(root, "restore", "--staged", "--", *paths)}

    def _check_paths(self, root, paths):
        if not 1 <= len(paths) <= 100:
            raise ValueError("Choose 1..100 paths")
        for path in paths:
            self.file(root, path)

    def git_restore_files(self, repo_id: str, paths: list[str], revision: str = "HEAD", restore_index: bool = False) -> dict:
        """用指定提交恢复选定文件的工作区内容，可同时恢复暂存区。"""
        with self.session("git_restore_files", {"repo_id": repo_id, "paths": paths, "revision": revision, "restore_index": restore_index}) as s:
            root = self.repo(s, repo_id)
            self._check_paths(root, paths)
            args = ["restore", "--source="+self.ref(root, revision), "--worktree"]
            if restore_index:
                args.append("--staged")
            return {"text": self.run(root, *args, "--", *paths)}

    def git_stash(self, repo_id: str, operation: str = "list", stash: str | None = None, message: str = "", include_untracked: bool = False) -> dict:
        """保存、列出、查看、应用、弹出或删除 stash。"""
        if operation not in {"list", "push", "show", "apply", "pop", "drop"} or stash is not None and not re.fullmatch(r"stash@\{[0-9]+\}", stash):
            raise ValueError("Invalid stash operation or reference")
        if operation in {"list", "push"} and stash is not None or operation != "push" and (message or include_untracked):
            raise ValueError("Arguments do not apply to this stash operation")
        readonly = operation in {"list", "show"}
        with self.session(None if readonly else "git_stash", {"repo_id": repo_id, "operation": operation, "stash": stash}) as s:
            root = self.repo(s, repo_id)
            args = ["stash", operation]
            if operation == "push":
                if message:
                    args.extend(["-m", message])
                if include_untracked:
                    args.append("--include-untracked")
            elif operation == "show":
                args.extend(["--patch", "--no-ext-diff", "--no-textconv", stash or "stash@{0}"])
            elif operation != "list":
                args.append(stash or "stash@{0}")
            result = self.run_result(root, *args, clock=s["now"])
            return {"returncode": result.returncode, "text": (result.stdout+result.stderr).decode("utf-8", "replace"), "conflicts": self.run(root, "diff", "--name-only", "--diff-filter=U", "-z", "--").split("\0")[:-1]}

    def git_cherry_pick(self, repo_id: str, operation: str = "start", revision: str | None = None) -> dict:
        """挑选一个提交，支持冲突后的 continue/skip/abort。"""
        return self._sequence(repo_id, "cherry-pick", operation, revision)

    def git_revert(self, repo_id: str, operation: str = "start", revision: str | None = None) -> dict:
        """以新提交撤销历史提交，支持 continue/skip/abort。"""
        return self._sequence(repo_id, "revert", operation, revision)

    def _sequence(self, repo_id, command, operation, revision):
        if operation not in {"start", "continue", "skip", "abort"} or (operation == "start") != (revision is not None):
            raise ValueError("start requires revision; continue/skip/abort use no revision")
        with self.session("git_"+command, {"repo_id": repo_id, "operation": operation, "revision": revision}) as s:
            root = self.repo(s, repo_id)
            if operation == "start":
                self.require_clean_history(root)
                args = [command, "--no-edit", self.ref(root, revision)]
            else:
                marker = "CHERRY_PICK_HEAD" if command == "cherry-pick" else "REVERT_HEAD"
                if not (root/".git"/marker).exists() and not (root/".git"/"sequencer").is_dir():
                    raise ValueError("No matching operation in progress")
                args = [command, "--"+operation]
            result = self.run_result(root, *args, clock=s["now"])
            state = self.operation_state(root)
            if result.returncode and state["operation"] != command:
                raise ValueError((result.stderr+result.stdout).decode("utf-8", "replace")[:8000])
            return {**state, "returncode": result.returncode, "text": (result.stdout+result.stderr).decode("utf-8", "replace")[:16000]}

    def git_blame(self, repo_id: str, path: str, revision: str = "HEAD", start_line: int = 1, end_line: int = 200) -> dict:
        """读取文件选定行在指定提交中的逐行归属。"""
        if not 1 <= start_line <= end_line or end_line-start_line >= 1000:
            raise ValueError("Select up to 1000 lines")
        with self.session() as s:
            root = self.repo(s, repo_id)
            self.file(root, path)
            return {"text": self.run(root, "blame", "--line-porcelain", "-L", f"{start_line},{end_line}", self.ref(root, revision), "--", path)}

    def git_file_history(self, repo_id: str, path: str, revision: str = "HEAD", limit: int = 20) -> dict:
        """查询文件历史，跟踪单文件重命名。"""
        if not 1 <= limit <= 100:
            raise ValueError("limit 1..100")
        with self.session() as s:
            root = self.repo(s, repo_id)
            self.file(root, path)
            return {"text": self.run(root, "log", "--follow", f"-{limit}", "--format=%H %aI %s", self.ref(root, revision), "--", path)}

    def git_reflog(self, repo_id: str, revision: str = "HEAD", limit: int = 20) -> dict:
        """查询本地引用移动记录，供定位历史提交和恢复操作使用。"""
        if not 1 <= limit <= 100 or revision.startswith("-"):
            raise ValueError("Invalid revision or limit")
        with self.session() as s:
            root = self.repo(s, repo_id)
            self.ref(root, revision)
            return {"text": self.run(root, "reflog", "show", f"-{limit}", "--format=%H %gD %gs", revision, "--")}
