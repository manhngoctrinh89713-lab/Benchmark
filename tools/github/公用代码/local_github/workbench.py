"""Collaboration lifecycle and asynchronous workflow requests."""
import copy
from local_repos.backend import page


class GitHubWorkbench:
    def list_comments(self, repo_id: str, kind: str, number: int, offset: int = 0, limit: int = 20) -> dict:
        """分页读取 Issue 或 PR 的普通讨论评论。"""
        with self.session() as s:
            self.repo(s, repo_id)
            self._discussion(s, repo_id, kind, number)
            return page([c for c in s["comments"] if c["repo_id"] == repo_id and c["kind"] == kind and c["number"] == number], offset, limit)

    def _discussion(self, s, repo_id, kind, number):
        if kind not in {"issue", "pull_request"}:
            raise ValueError("kind: issue/pull_request")
        return self.item(s, "issues" if kind == "issue" else "pull_requests", repo_id, number)

    def update_comment(self, repo_id: str, comment_id: int, body: str) -> dict:
        """修改当前用户发表的普通讨论评论。"""
        if not body.strip() or len(body) > 65536:
            raise ValueError("Comment must contain 1..65536 characters")
        with self.session("update_comment", {"repo_id": repo_id, "comment_id": comment_id, "body": body}) as s:
            self.repo(s, repo_id)
            c = self.named(s, "comments", repo_id, "id", comment_id)
            if c["author"] != s["current_user"]:
                raise PermissionError("Only the author may edit this comment")
            s.setdefault("comment_events", []).append({"action": "edit", "before": copy.deepcopy(c), "at": s["now"]})
            c.update(body=body, updated_at=s["now"])
            return copy.deepcopy(c)

    def delete_comment(self, repo_id: str, comment_id: int) -> dict:
        """删除当前用户发表的普通讨论评论。"""
        with self.session("delete_comment", {"repo_id": repo_id, "comment_id": comment_id}) as s:
            self.repo(s, repo_id)
            c = self.named(s, "comments", repo_id, "id", comment_id)
            if c["author"] != s["current_user"]:
                raise PermissionError("Only the author may delete this comment")
            s.setdefault("comment_events", []).append({"action": "delete", "before": copy.deepcopy(c), "at": s["now"]})
            s["comments"].remove(c)
            return {"deleted_comment_id": comment_id}

    def delete_label(self, repo_id: str, name: str) -> dict:
        """删除仓库标签，同时移除 Issue 和 PR 上的该标签。"""
        with self.session("delete_label", {"repo_id": repo_id, "name": name}) as s:
            self.repo(s, repo_id)
            label = self.named(s, "labels", repo_id, "name", name)
            s["labels"].remove(label)
            for item in s["issues"]+s["pull_requests"]:
                if item["repo_id"] == repo_id:
                    item["labels"] = [v for v in item.get("labels", []) if v != name]
            return {"deleted_label": name}

    def delete_milestone(self, repo_id: str, number: int) -> dict:
        """删除里程碑并清除 Issue 和 PR 的关联。"""
        with self.session("delete_milestone", {"repo_id": repo_id, "number": number}) as s:
            self.repo(s, repo_id)
            item = self.named(s, "milestones", repo_id, "number", number)
            s["milestones"].remove(item)
            for obj in s["issues"]+s["pull_requests"]:
                if obj["repo_id"] == repo_id and obj.get("milestone") == number:
                    obj["milestone"] = None
            return {"deleted_milestone": number}

    def set_issue_assignees(self, repo_id: str, number: int, assignees: list[str]) -> dict:
        """替换 Issue 的指派人，空列表清除指派。"""
        with self.session("set_issue_assignees", {"repo_id": repo_id, "number": number, "assignees": assignees}) as s:
            self.repo(s, repo_id)
            known = {u["login"] for u in s.get("users", [])} | {s["current_user"]}
            if len(assignees) > 10 or not set(assignees) <= known:
                raise ValueError("Choose at most ten known users")
            issue = self.item(s, "issues", repo_id, number)
            issue["assignees"] = sorted(set(assignees))
            return copy.deepcopy(issue)

    def set_item_labels(self, repo_id: str, kind: str, number: int, labels: list[str]) -> dict:
        """替换 Issue 或 PR 上的标签，空列表清空。"""
        with self.session("set_item_labels", {"repo_id": repo_id, "kind": kind, "number": number, "labels": labels}) as s:
            self.repo(s, repo_id)
            item = self._discussion(s, repo_id, kind, number)
            if not set(labels) <= {v["name"] for v in s["labels"] if v["repo_id"] == repo_id}:
                raise ValueError("Unknown repository label")
            item["labels"] = sorted(set(labels))
            return copy.deepcopy(item)

    def remove_requested_reviewers(self, repo_id: str, number: int, reviewers: list[str]) -> dict:
        """移除 PR 的待评审人。"""
        with self.session("remove_requested_reviewers", {"repo_id": repo_id, "number": number, "reviewers": reviewers}) as s:
            self.repo(s, repo_id)
            pr = self.item(s, "pull_requests", repo_id, number)
            if pr["state"] != "open":
                raise ValueError("PR is closed")
            pr["requested_reviewers"] = [v for v in pr.get("requested_reviewers", []) if v not in reviewers]
            return copy.deepcopy(pr)

    def list_pull_request_files(self, repo_id: str, number: int, offset: int = 0, limit: int = 20) -> dict:
        """基于 PR 当前基线和提交列出变更路径、状态及增删行数。"""
        with self.session() as s:
            root = self.repo(s, repo_id)
            pr = self.item(s, "pull_requests", repo_id, number)
            base, head = pr.get("merged_base_sha") or self.ref(root, pr["base"]), pr.get("merged_head_sha") or self.ref(root, pr["head"])
            text = self.run(root, "diff", "--no-ext-diff", "--no-textconv", "--no-renames", "--numstat", "-z", base+"..."+head, "--")
            rows = []
            for row in text.split("\0"):
                if row:
                    added, removed, path = row.split("\t", 2)
                    rows.append({"path": path, "additions": None if added == "-" else int(added), "deletions": None if removed == "-" else int(removed)})
            return {**page(rows, offset, limit), "base_sha": base, "head_sha": head}

    def list_pull_request_commits(self, repo_id: str, number: int, offset: int = 0, limit: int = 20) -> dict:
        """列出 PR 当前分支相对基线包含的提交。"""
        with self.session() as s:
            root = self.repo(s, repo_id)
            pr = self.item(s, "pull_requests", repo_id, number)
            base, head = pr.get("merged_base_sha") or self.ref(root, pr["base"]), pr.get("merged_head_sha") or self.ref(root, pr["head"])
            rows = self.run(root, "log", "--format=%H%x09%aI%x09%s", base+".."+head, "--").splitlines()
            return {**page([dict(zip(("sha", "authored_at", "subject"), row.split("\t", 2))) for row in rows], offset, limit), "head_sha": head}

    def update_release(self, repo_id: str, tag: str, name: str | None = None, body: str | None = None, draft: bool | None = None, prerelease: bool | None = None) -> dict:
        """修改发布版本说明以及草稿、预发布状态。"""
        with self.session("update_release", {"repo_id": repo_id, "tag": tag}) as s:
            self.repo(s, repo_id)
            r = self.named(s, "releases", repo_id, "tag", tag)
            if name is not None and not name.strip():
                raise ValueError("Name is empty")
            r.update({k: v for k, v in {"name": name, "body": body, "draft": draft, "prerelease": prerelease}.items() if v is not None})
            r["updated_at"] = s["now"]
            return copy.deepcopy(r)

    def delete_release(self, repo_id: str, tag: str) -> dict:
        """删除发布记录，保留对应 Git 标签。"""
        with self.session("delete_release", {"repo_id": repo_id, "tag": tag}) as s:
            self.repo(s, repo_id)
            r = self.named(s, "releases", repo_id, "tag", tag)
            s.setdefault("release_events", []).append({"action": "delete", "release": copy.deepcopy(r), "at": s["now"]})
            s["releases"].remove(r)
            return {"deleted_release_id": r["id"], "retained_tag": tag}

    def dispatch_workflow(self, repo_id: str, workflow_id: int, ref: str, inputs: dict[str, str] | None = None) -> dict:
        """向支持手动触发的工作流提交运行请求，固定当前引用对应的提交。"""
        with self.session("dispatch_workflow", {"repo_id": repo_id, "workflow_id": workflow_id, "ref": ref, "inputs": inputs}) as s:
            root = self.repo(s, repo_id)
            workflow = self.named(s, "workflows", repo_id, "id", workflow_id)
            if workflow.get("state", "active") != "active" or "workflow_dispatch" not in workflow.get("events", []):
                raise ValueError("Workflow does not allow manual dispatch")
            schema = workflow.get("inputs", {})
            values = inputs or {}
            if set(values)-set(schema) or any(spec.get("required") and key not in values and "default" not in spec for key, spec in schema.items()):
                raise ValueError("Workflow inputs do not match declared fields")
            resolved = {key: values.get(key, spec.get("default")) for key, spec in schema.items()}
            for key, value in resolved.items():
                spec = schema[key]
                if spec.get("options") and value not in spec["options"]:
                    raise ValueError("Invalid workflow input option")
            run = {"id": self.next_id(s, "workflow_runs"), "repo_id": repo_id, "workflow_id": workflow_id, "name": workflow["name"], "branch": ref, "head_sha": self.ref(root, ref), "status": "queued", "conclusion": None, "attempt": 1, "inputs": resolved, "actor": s["current_user"], "created_at": s["now"], "logs": ""}
            s["workflow_runs"].append(run)
            return {k: v for k, v in run.items() if k != "logs"}

    def cancel_workflow_run(self, repo_id: str, run_id: int) -> dict:
        """请求取消正在排队或运行的工作流；最终结果由执行器回报。"""
        with self.session("cancel_workflow_run", {"repo_id": repo_id, "run_id": run_id}) as s:
            self.repo(s, repo_id)
            run = self.named(s, "workflow_runs", repo_id, "id", run_id)
            if run["status"] == "completed":
                raise ValueError("Run has already completed")
            run["cancel_requested_at"] = s["now"]
            return {k: v for k, v in run.items() if k != "logs"}

    def rerun_workflow(self, repo_id: str, run_id: int) -> dict:
        """重新运行已完成的工作流，保持原提交及输入，另建运行记录。"""
        with self.session("rerun_workflow", {"repo_id": repo_id, "run_id": run_id}) as s:
            self.repo(s, repo_id)
            previous = self.named(s, "workflow_runs", repo_id, "id", run_id)
            if previous["status"] != "completed":
                raise ValueError("Only completed runs can be rerun")
            run = {k: copy.deepcopy(v) for k, v in previous.items() if k not in {"logs", "completed_at", "cancel_requested_at", "started_at"}}
            run.update(id=self.next_id(s, "workflow_runs"), status="queued", conclusion=None, attempt=previous.get("attempt", 1)+1, rerun_of=run_id, logs="", actor=s["current_user"], created_at=s["now"])
            s["workflow_runs"].append(run)
            return {k: v for k, v in run.items() if k != "logs"}
