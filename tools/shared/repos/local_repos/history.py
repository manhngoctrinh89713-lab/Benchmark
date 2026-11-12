"""Local merge/rebase lifecycle and squash with an unchanged final tree."""


class HistoryOperations:
    def operation_state(self, root):
        metadata = root / ".git"
        operation = None
        if (metadata / "rebase-merge").is_dir() or (metadata / "rebase-apply").is_dir():
            operation = "rebase"
        elif (metadata / "MERGE_HEAD").exists():
            operation = "merge"
        elif (metadata / "CHERRY_PICK_HEAD").exists():
            operation = "cherry-pick"
        elif (metadata / "REVERT_HEAD").exists():
            operation = "revert"
        conflicts = self.run(root, "diff", "--name-only", "--diff-filter=U", "-z", "--")
        branch = self.run_result(root, "symbolic-ref", "--quiet", "--short", "HEAD")
        return {"operation": operation, "conflicts": [p for p in conflicts.split("\0") if p],
                "branch": branch.stdout.decode("utf-8", "replace").strip() if branch.returncode == 0 else None,
                "head": self.ref(root, "HEAD"), "worktree_status": self.run(root, "status", "--porcelain")}

    def git_operation_status(self, repo_id):
        with self.session() as state:
            return self.operation_state(self.repo(state, repo_id))

    def require_clean_history(self, root):
        state = self.operation_state(root)
        if state["operation"] or state["worktree_status"]:
            raise ValueError("Operation requires no merge/rebase in progress and a clean working tree/index")
        if state["branch"] is None:
            raise ValueError("Operation requires a checked-out local branch")
        return state

    def history_result(self, root, command, operation, clock):
        result = self.run_result(root, *command, clock=clock)
        state = self.operation_state(root)
        output = (result.stdout + result.stderr).decode("utf-8", "replace")[:16000]
        if result.returncode and state["operation"] != operation:
            raise ValueError(output or "Git operation failed")
        status = "conflicts" if state["conflicts"] else ("paused" if state["operation"] else "completed")
        return {**state, "status": status, "returncode": result.returncode, "output": output}

    def git_merge(self, repo_id, operation="start", source=None, message=None, ff_mode="ff"):
        if operation not in {"start", "continue", "abort"}:
            raise ValueError("operation must be start/continue/abort")
        if ff_mode not in {"ff", "no-ff", "ff-only"}:
            raise ValueError("ff_mode must be ff/no-ff/ff-only")
        if message is not None and not message.strip():
            raise ValueError("Merge message cannot be blank")
        if operation != "start" and (source is not None or message is not None or ff_mode != "ff"):
            raise ValueError("source/message/ff_mode apply only to start")
        with self.session("git_merge", {"repo_id": repo_id, "operation": operation,
                                       "source": source, "message": message, "ff_mode": ff_mode}) as state:
            root = self.repo(state, repo_id)
            if operation == "start":
                self.require_clean_history(root)
                if not source:
                    raise ValueError("source is required for merge start")
                source_sha = self.ref(root, source)
                command = ["merge", "--no-edit", "--no-autostash", "--" + ff_mode]
                if message:
                    command.extend(["-m", message])
                command.append(source_sha)
            else:
                current = self.operation_state(root)
                if current["operation"] != "merge":
                    raise ValueError("No merge in progress")
                if operation == "continue" and current["conflicts"]:
                    raise ValueError("Resolve conflicts and git_add the resolved paths before continuing")
                command = ["merge", "--" + operation]
            result = self.history_result(root, command, "merge", state["now"])
            if operation == "abort" and result["returncode"] == 0 and result["operation"] is None:
                result["status"] = "aborted"
            return result

    def git_rebase(self, repo_id, operation="start", upstream=None, onto=None, rebase_merges=False):
        if operation not in {"start", "continue", "skip", "abort"}:
            raise ValueError("operation must be start/continue/skip/abort")
        if not isinstance(rebase_merges, bool):
            raise ValueError("rebase_merges must be boolean")
        if operation != "start" and (upstream is not None or onto is not None or rebase_merges):
            raise ValueError("upstream/onto/rebase_merges apply only to start")
        with self.session("git_rebase", {"repo_id": repo_id, "operation": operation,
            "upstream": upstream, "onto": onto, "rebase_merges": rebase_merges}) as state:
            root = self.repo(state, repo_id)
            if operation == "start":
                self.require_clean_history(root)
                if not upstream:
                    raise ValueError("upstream is required for rebase start")
                upstream_sha = self.ref(root, upstream)
                command = ["rebase", "--no-autostash", "--no-fork-point", "--no-update-refs", "--empty=stop",
                           "--rebase-merges" if rebase_merges else "--no-rebase-merges"]
                if onto is not None:
                    command.extend(["--onto", self.ref(root, onto)])
                command.append(upstream_sha)
            else:
                current = self.operation_state(root)
                if current["operation"] != "rebase":
                    raise ValueError("No rebase in progress")
                if operation == "continue" and current["conflicts"]:
                    raise ValueError("Resolve conflicts and git_add the resolved paths before continuing")
                command = ["rebase", "--" + operation]
            result = self.history_result(root, command, "rebase", state["now"])
            if operation == "abort" and result["returncode"] == 0 and result["operation"] is None:
                result["status"] = "aborted"
            return result

    def git_squash(self, repo_id, base, message):
        if not message.strip():
            raise ValueError("Commit message cannot be blank")
        with self.session("git_squash", {"repo_id": repo_id, "base": base, "message": message}) as state:
            root = self.repo(state, repo_id)
            current = self.require_clean_history(root)
            old = current["head"]
            parent = self.ref(root, base)
            if parent == old:
                raise ValueError("No commits after base to squash")
            self.run(root, "merge-base", "--is-ancestor", parent, old)
            tree = self.run(root, "rev-parse", old + "^{tree}").strip()
            # Construct the new commit from the entire tree: deletions, binary
            # blobs and file modes are preserved without rewriting any files.
            new = self.run(root, "commit-tree", tree, "-p", parent, "-m", message, clock=state["now"]).strip()
            branch = self.run(root, "symbolic-ref", "HEAD").strip()
            self.run(root, "update-ref", "-m", "squash commits", branch, new, old)
            return {"status": "completed", "branch": current["branch"], "base": parent,
                    "old_head": old, "head": new, "tree": tree,
                    "squashed_commits": int(self.run(root, "rev-list", "--count", parent + ".." + old))}
