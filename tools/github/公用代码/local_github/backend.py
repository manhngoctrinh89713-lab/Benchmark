"""Local GitHub platform state, linked to the common real Git repository store."""
import copy
import re
from datetime import datetime
from local_repos.backend import RepoStore, page


from .workbench import GitHubWorkbench


class GitHubStore(GitHubWorkbench, RepoStore):
    SERVICE = "github"

    @staticmethod
    def next_number(s, repo_id):
        return max([x["number"] for x in s["issues"] + s["pull_requests"] if x["repo_id"] == repo_id] + [0]) + 1

    @staticmethod
    def next_id(s, field):
        counters = s.setdefault("id_counters", {})
        value = max([counters.get(field, 0), *[x["id"] for x in s[field]]])+1
        counters[field] = value
        return value

    @staticmethod
    def named(s, field, repo_id, key, value):
        item = next((x for x in s[field] if x["repo_id"] == repo_id and x[key] == value), None)
        if item is None:
            raise ValueError(f"Unknown {field}: {value}")
        return item

    def get_me(self):
        with self.session() as s:
            profile = next((x for x in s.get("users", []) if x["login"] == s["current_user"]), {})
            return {**profile, "login": s["current_user"]}

    def get_repository(self, repo_id):
        with self.session() as s:
            self.repo(s, repo_id)
            r = next(x for x in s["repositories"] if x["id"] == repo_id)
            result = {k: v for k, v in r.items() if k not in ("branches", "remotes")}
            result["visibility"] = "private" if result.get("private", True) else "public"
            return result

    def update_repository_visibility(self, repo_id, visibility):
        if visibility not in ("public", "private"):
            raise ValueError("visibility must be public or private")
        with self.session("github_update_repository_visibility",
                          {"repo_id": repo_id, "visibility": visibility}) as s:
            root = self.repo(s, repo_id)
            r = next(x for x in s["repositories"] if x["id"] == repo_id)
            target_private = visibility == "private"
            changed = r.get("private", True) != target_private
            # Record the committed objects at the moment of publication, before
            # later visibility or file edits can hide an earlier exposure.
            # This internal journal is never returned through repository tools.
            refs = self.run(root, "for-each-ref", "--format=%(refname) %(objectname)").splitlines()
            objects = self.run(root, "rev-list", "--objects", "--all", "--no-object-names").splitlines()
            s.setdefault("visibility_events", []).append({
                "sequence": s["sequence"] + 1, "at": s["now"], "repo_id": repo_id,
                "action": "github_update_repository_visibility",
                "before_private": r.get("private", True), "after_private": target_private,
                "refs": refs, "objects": sorted(set(objects))})
            r["private"] = target_private
            result = {k: v for k, v in r.items() if k not in ("branches", "remotes")}
            result["visibility"] = visibility
            return {"repository": result, "visibility": visibility, "changed": changed}

    def search_repositories(self, query="", offset=0, limit=20):
        with self.session() as s:
            matches = [r for r in s["repositories"] if query.casefold() in " ".join(str(r.get(k, "")) for k in ("id", "name", "owner", "description")).casefold()]
            rows = []
            for r in matches:
                row = {k: v for k, v in r.items() if k not in ("branches", "remotes")}
                row["visibility"] = "private" if row.get("private", True) else "public"
                rows.append(row)
            return page(rows, offset, limit)

    def tree_entries(self, root, sha):
        entries = []
        for entry in self.run(root, "ls-tree", "-r", "-z", "--full-tree", sha).split("\x00"):
            if entry:
                meta, path = entry.split("\t", 1)
                mode, kind, oid = meta.split()
                entries.append({"path": path, "mode": mode, "type": kind, "sha": oid})
        return entries

    def text_blob(self, root, entry):
        if entry["mode"] not in ("100644", "100755"):
            raise ValueError("Only regular tracked text files are supported")
        size = int(self.run(root, "cat-file", "-s", entry["sha"]))
        if size > 1024 * 1024:
            raise ValueError("Text blob exceeds 1 MiB")
        text = self.run(root, "cat-file", "blob", entry["sha"])
        if "\x00" in text or "\ufffd" in text:
            raise ValueError("Only UTF-8 text is supported")
        return text

    def get_file_contents(self, repo_id, path="", ref=None):
        with self.session() as s:
            root = self.repo(s, repo_id)
            default = next(x for x in s["repositories"] if x["id"] == repo_id).get("default_branch", "main")
            sha = self.ref(root, ref or default)
            rel = "" if path in ("", ".") else self.file(root, path).relative_to(root).as_posix()
            entries = self.tree_entries(root, sha)
            exact = next((x for x in entries if x["path"] == rel), None)
            if exact:
                return {**exact, "commit_sha": sha, "content": self.text_blob(root, exact)}
            prefix = rel + "/" if rel else ""
            children = {}
            for entry in entries:
                if entry["path"].startswith(prefix):
                    rest = entry["path"][len(prefix):]
                    name, sep, tail = rest.partition("/")
                    children[name] = {"name": name, "path": prefix + name, "type": "dir" if sep else "file"}
            if rel and not children:
                raise ValueError("Unknown file/directory at this revision")
            return {"path": rel, "commit_sha": sha, "items": [children[k] for k in sorted(children)]}

    def search_code(self, repo_id, query, ref=None, path_prefix="", offset=0, limit=20):
        if not query.strip():
            raise ValueError("query cannot be blank; literal case-insensitive substring search")
        with self.session() as s:
            root = self.repo(s, repo_id)
            default = next(x for x in s["repositories"] if x["id"] == repo_id).get("default_branch", "main")
            sha = self.ref(root, ref or default)
            prefix = self.file(root, path_prefix).relative_to(root).as_posix() if path_prefix else ""
            matches = []
            for entry in self.tree_entries(root, sha):
                if prefix and entry["path"] != prefix and not entry["path"].startswith(prefix + "/"):
                    continue
                if entry["mode"] not in ("100644", "100755"):
                    continue
                try:
                    content = self.text_blob(root, entry)
                except ValueError:
                    continue
                for line, text in enumerate(content.splitlines(), 1):
                    if query.casefold() in text.casefold():
                        matches.append({"path": entry["path"], "line": line, "text": text[:2000], "commit_sha": sha})
            return page(matches, offset, limit)

    def list_labels(self, repo_id, offset=0, limit=20):
        with self.session() as s:
            self.repo(s, repo_id)
            return page([x for x in s["labels"] if x["repo_id"] == repo_id], offset, limit)

    def label_write(self, repo_id, name, color=None, description=None, new_name=None):
        if not name.strip() or (new_name is not None and not new_name.strip()):
            raise ValueError("Label name cannot be blank")
        if color is not None and not re.fullmatch(r"[0-9a-fA-F]{6}", color):
            raise ValueError("color must be six hexadecimal digits without #")
        with self.session("label_write", {"repo_id": repo_id, "name": name}) as s:
            self.repo(s, repo_id)
            existing = [x for x in s["labels"] if x["repo_id"] == repo_id]
            label = next((x for x in existing if x["name"] == name), None)
            if new_name and new_name != name and any(x["name"] == new_name for x in existing):
                raise ValueError("Label already exists")
            if label is None:
                label = {"repo_id": repo_id, "name": name, "color": "ededed", "description": ""}
                s["labels"].append(label)
            label.update({k: v for k, v in {"color": color, "description": description, "name": new_name}.items() if v is not None})
            if new_name and new_name != name:
                for item in s["issues"] + s["pull_requests"]:
                    if item["repo_id"] == repo_id and name in item.get("labels", []):
                        item["labels"] = [new_name if x == name else x for x in item["labels"]]
            return copy.deepcopy(label)

    def list_milestones(self, repo_id, state="open", offset=0, limit=20):
        if state not in ("open", "closed", "all"):
            raise ValueError("state open/closed/all")
        with self.session() as s:
            self.repo(s, repo_id)
            result = []
            for x in s["milestones"]:
                if x["repo_id"] == repo_id and (state == "all" or x["state"] == state):
                    issues = [i for i in s["issues"] if i["repo_id"] == repo_id and i.get("milestone") == x["number"]]
                    result.append({**x, "open_issues": sum(i["state"] == "open" for i in issues), "closed_issues": sum(i["state"] == "closed" for i in issues)})
            return page(result, offset, limit)

    def milestone_write(self, repo_id, title=None, number=None, description=None, state=None, due_on=None):
        if state not in (None, "open", "closed") or (title is not None and not title.strip()):
            raise ValueError("Invalid title/state")
        if due_on:
            date = datetime.fromisoformat(due_on.replace("Z", "+00:00"))
            if date.tzinfo is None:
                raise ValueError("due_on requires timezone; empty string clears it")
        with self.session("milestone_write", {"repo_id": repo_id, "number": number}) as s:
            self.repo(s, repo_id)
            if number is None:
                if not title:
                    raise ValueError("New milestone requires title")
                counter_key = "milestones/"+repo_id
                number = s["id_counters"].get(counter_key, 0)+1
                s["id_counters"][counter_key] = number
                item = {"repo_id": repo_id, "number": number, "title": title, "description": "", "state": "open", "due_on": None}
                s["milestones"].append(item)
            else:
                item = self.named(s, "milestones", repo_id, "number", number)
            item.update({k: (None if k == "due_on" and v == "" else v) for k, v in {"title": title, "description": description, "state": state, "due_on": due_on}.items() if v is not None})
            return copy.deepcopy(item)

    def request_reviewers(self, repo_id, number, reviewers):
        if not reviewers or any(not name.strip() for name in reviewers):
            raise ValueError("reviewers cannot be empty")
        with self.session("request_reviewers", {"repo_id": repo_id, "number": number, "reviewers": reviewers}) as s:
            self.repo(s, repo_id); pr = self.item(s, "pull_requests", repo_id, number)
            if pr["state"] != "open" or pr["author"] in reviewers:
                raise ValueError("Open PR and reviewers other than author required")
            pr["requested_reviewers"] = sorted(set(pr.get("requested_reviewers", []) + reviewers))
            return copy.deepcopy(pr)

    def add_pull_request_review_comment(self, repo_id, number, path, line, body, expected_head_sha):
        if line < 1 or not body.strip():
            raise ValueError("line >= 1; nonempty body required")
        with self.session("add_pull_request_review_comment", {"repo_id": repo_id, "number": number, "path": path, "line": line}) as s:
            root = self.repo(s, repo_id); pr = self.item(s, "pull_requests", repo_id, number)
            head = self.ref(root, pr["head"])
            if pr["state"] != "open" or head != expected_head_sha:
                raise ValueError("Open PR and expected current head required")
            rel = self.file(root, path).relative_to(root).as_posix()
            entry = next((x for x in self.tree_entries(root, head) if x["path"] == rel), None)
            if not entry or line > len(self.text_blob(root, entry).splitlines()):
                raise ValueError("File/line does not exist at head")
            # This local subset supports RIGHT-side lines included in the PR diff.
            base = self.ref(root, pr["base"])
            diff = self.run(root, "diff", "--no-ext-diff", "--no-textconv", "--unified=3", base + "..." + head, "--", rel)
            allowed = set()
            for match in re.finditer(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", diff, re.MULTILINE):
                start, count = int(match[1]), int(match[2] or "1")
                allowed.update(range(start, start + count))
            if line not in allowed:
                raise ValueError("Line must be on the RIGHT side of a PR diff hunk")
            comment = {"id": self.next_id(s, "review_comments"), "repo_id": repo_id, "number": number, "path": rel, "line": line, "side": "RIGHT", "body": body, "head_sha": head, "author": s["current_user"], "timestamp": s["now"]}
            s["review_comments"].append(comment)
            return copy.deepcopy(comment)

    def list_releases(self, repo_id, offset=0, limit=20):
        with self.session() as s:
            self.repo(s, repo_id)
            return page([x for x in s["releases"] if x["repo_id"] == repo_id], offset, limit)

    def get_release(self, repo_id, tag):
        with self.session() as s:
            self.repo(s, repo_id)
            return copy.deepcopy(self.named(s, "releases", repo_id, "tag", tag))

    def create_release(self, repo_id, tag, name, body="", target=None, draft=False, prerelease=False):
        if not name.strip() or not tag or tag.startswith("-"):
            raise ValueError("Valid name/tag required")
        with self.session("create_release", {"repo_id": repo_id, "tag": tag, "target": target}) as s:
            root = self.repo(s, repo_id)
            self.run(root, "check-ref-format", "refs/tags/" + tag)
            if any(x["repo_id"] == repo_id and x["tag"] == tag for x in s["releases"]):
                raise ValueError("Release already exists")
            existing = tag in self.run(root, "tag", "--list").splitlines()
            default = next(x for x in s["repositories"] if x["id"] == repo_id).get("default_branch", "main")
            sha = self.ref(root, "refs/tags/" + tag) if existing else self.ref(root, target or default)
            if existing and target and sha != self.ref(root, target):
                raise ValueError("Existing tag points to a different commit")
            if not existing:
                self.run(root, "tag", "--", tag, sha)
            release = {"id": self.next_id(s, "releases"), "repo_id": repo_id, "tag": tag, "name": name, "body": body, "target_sha": sha, "draft": draft, "prerelease": prerelease, "author": s["current_user"], "created_at": s["now"]}
            s["releases"].append(release)
            return copy.deepcopy(release)

    def list_workflows(self, repo_id, offset=0, limit=20):
        with self.session() as s:
            self.repo(s, repo_id)
            return page([x for x in s["workflows"] if x["repo_id"] == repo_id], offset, limit)

    def list_workflow_runs(self, repo_id, workflow_id=None, status=None, branch=None, offset=0, limit=20):
        if status not in (None, "queued", "in_progress", "completed"):
            raise ValueError("status queued/in_progress/completed")
        with self.session() as s:
            self.repo(s, repo_id)
            rows = [x for x in s["workflow_runs"] if x["repo_id"] == repo_id and (workflow_id is None or x["workflow_id"] == workflow_id) and (status is None or x["status"] == status) and (branch is None or x["branch"] == branch)]
            return page([{k: v for k, v in x.items() if k != "logs"} for x in rows], offset, limit)

    def get_workflow_run(self, repo_id, run_id):
        with self.session() as s:
            self.repo(s, repo_id)
            run = self.named(s, "workflow_runs", repo_id, "id", run_id)
            return {k: v for k, v in run.items() if k != "logs"}

    def get_workflow_run_logs(self, repo_id, run_id, offset=0, limit=100):
        if offset < 0 or not 1 <= limit <= 1000:
            raise ValueError("offset >= 0; limit 1..1000 lines")
        with self.session() as s:
            self.repo(s, repo_id)
            run = self.named(s, "workflow_runs", repo_id, "id", run_id)
            lines = run.get("logs", "").splitlines()
            return {"run_id": run_id, "lines": lines[offset:offset+limit], "total": len(lines), "next_offset": offset+limit if offset+limit < len(lines) else None}

    def list_notifications(self, repo_id=None, unread_only=True, offset=0, limit=20):
        with self.session() as s:
            if repo_id is not None:
                self.repo(s, repo_id)
            return page([x for x in s["notifications"] if x["recipient"] == s["current_user"] and (repo_id is None or x["repo_id"] == repo_id) and (not unread_only or x.get("unread", True))], offset, limit)

    def mark_notification_read(self, notification_id):
        with self.session("mark_notification_read", {"notification_id": notification_id}) as s:
            item = next((x for x in s["notifications"] if x["id"] == notification_id and x["recipient"] == s["current_user"]), None)
            if item is None:
                raise ValueError("Unknown notification for current user")
            item.update(unread=False, read_at=s["now"])
            return copy.deepcopy(item)

    @staticmethod
    def item(s, field, repo_id, number):
        item = next((x for x in s[field] if x["repo_id"] == repo_id and x["number"] == number), None)
        if item is None:
            raise ValueError("Unknown issue/pull request")
        return item

    def list_issues(self, repo_id, state="open", query="", offset=0, limit=20, labels=None, assignee=None, milestone=None):
        with self.session() as s:
            self.repo(s, repo_id)
            if state not in ("open", "closed", "all"):
                raise ValueError("state open/closed/all")
            return page([x for x in s["issues"] if x["repo_id"] == repo_id and (state == "all" or x["state"] == state) and query.casefold() in (x["title"] + "\n" + x["body"]).casefold() and (not labels or set(labels) <= set(x.get("labels", []))) and (assignee is None or assignee in x.get("assignees", [])) and (milestone is None or x.get("milestone") == milestone)], offset, limit)

    def issue_read(self, repo_id, number):
        with self.session() as s:
            self.repo(s, repo_id)
            return {**self.item(s, "issues", repo_id, number), "comments": [c for c in s["comments"] if c["repo_id"] == repo_id and c["kind"] == "issue" and c["number"] == number]}

    def issue_write(self, repo_id, title=None, body=None, number=None, state=None, labels=None, assignees=None, milestone=None):
        with self.session("issue_write", {"repo_id": repo_id, "number": number}) as s:
            self.repo(s, repo_id)
            if state not in (None, "open", "closed"):
                raise ValueError("state open/closed")
            if title is not None and not title.strip():
                raise ValueError("title cannot be empty")
            if labels is not None:
                known = {x["name"] for x in s["labels"] if x["repo_id"] == repo_id}
                if not set(labels) <= known:
                    raise ValueError("Create labels with label_write before assigning them")
            if milestone is not None and milestone != 0:
                self.named(s, "milestones", repo_id, "number", milestone)
            if number is None:
                if not title:
                    raise ValueError("New issue requires title")
                number = self.next_number(s, repo_id)
                x = {"repo_id": repo_id, "number": number, "title": title, "body": body or "", "state": "open", "author": s["current_user"], "labels": [], "assignees": []}
                s["issues"].append(x)
            else:
                x = self.item(s, "issues", repo_id, number)
            x.update({k: v for k, v in {"title": title, "body": body, "state": state, "labels": labels, "assignees": assignees}.items() if v is not None})
            if milestone is not None:
                x["milestone"] = milestone or None
            return copy.deepcopy(x)

    def add_comment(self, repo_id, kind, number, body):
        if kind not in ("issue", "pull_request") or not body.strip():
            raise ValueError("kind issue/pull_request; body cannot be blank")
        with self.session("add_comment", {"repo_id": repo_id, "kind": kind, "number": number}) as s:
            self.repo(s, repo_id); self.item(s, "issues" if kind == "issue" else "pull_requests", repo_id, number)
            x = {"id": self.next_id(s, "comments"), "repo_id": repo_id, "kind": kind, "number": number, "body": body, "author": s["current_user"], "timestamp": s["now"]}
            s["comments"].append(x); return copy.deepcopy(x)

    def list_pull_requests(self, repo_id, state="open", offset=0, limit=20, query="", author=None, reviewer=None):
        with self.session() as s:
            self.repo(s, repo_id)
            if state not in ("open", "closed", "merged", "all"):
                raise ValueError("state open/closed/merged/all")
            return page([x for x in s["pull_requests"] if x["repo_id"] == repo_id and (state == "all" or x["state"] == state) and query.casefold() in (x["title"] + "\n" + x.get("body", "")).casefold() and (author is None or x["author"] == author) and (reviewer is None or reviewer in x.get("requested_reviewers", []))], offset, limit)

    def pull_request_read(self, repo_id, number):
        with self.session() as s:
            p = self.repo(s, repo_id); x = self.item(s, "pull_requests", repo_id, number)
            base = x.get("merged_base_sha") or self.ref(p, x["base"])
            head = x.get("merged_head_sha") or self.ref(p, x["head"])
            return {**x, "base_sha": base, "head_sha": head, "diff": self.run(p, "diff", "--no-ext-diff", "--no-textconv", base + "..." + head, "--"),
                    "review_comments": [{**c, "outdated": c["head_sha"] != head} for c in s["review_comments"] if c["repo_id"] == repo_id and c["number"] == number],
                    "checks": [{k: v for k, v in run.items() if k != "logs"} for run in s["workflow_runs"] if run["repo_id"] == repo_id and run.get("head_sha") == head],
                    "reviews": [r for r in s["reviews"] if r["repo_id"] == repo_id and r["number"] == number],
                    "comments": [c for c in s["comments"] if c["repo_id"] == repo_id and c["number"] == number and c["kind"] == "pull_request"]}

    def create_pull_request(self, repo_id, title, head, base="main", body="", draft=False):
        with self.session("create_pull_request", {"repo_id": repo_id, "head": head, "base": base}) as s:
            p = self.repo(s, repo_id)
            for branch in (head, base):
                self.run(p, "show-ref", "--verify", "refs/heads/" + branch)
            if not title.strip() or head == base or self.ref(p, head) == self.ref(p, base):
                raise ValueError("Title and distinct branches with commits required")
            if not int(self.run(p, "rev-list", "--count", base + ".." + head)):
                raise ValueError("Head has no commits beyond base")
            if any(x["repo_id"] == repo_id and x["state"] == "open" and x["head"] == head and x["base"] == base for x in s["pull_requests"]):
                raise ValueError("Open PR already exists")
            n = self.next_number(s, repo_id)
            x = {"repo_id": repo_id, "number": n, "title": title, "body": body, "head": head, "base": base, "draft": draft, "state": "open", "author": s["current_user"]}
            s["pull_requests"].append(x); return copy.deepcopy(x)

    def update_pull_request(self, repo_id, number, title=None, body=None, draft=None, state=None, linked_issues=None):
        with self.session("update_pull_request", {"repo_id": repo_id, "number": number}) as s:
            self.repo(s, repo_id); x = self.item(s, "pull_requests", repo_id, number)
            if x["state"] == "merged" or state not in (None, "open", "closed") or (title is not None and not title.strip()):
                raise ValueError("Invalid PR state/title or PR already merged")
            if state == "open" and any(y is not x and y["repo_id"] == repo_id and y["state"] == "open" and y["head"] == x["head"] and y["base"] == x["base"] for y in s["pull_requests"]):
                raise ValueError("Another open PR already exists")
            if linked_issues is not None:
                for issue_number in linked_issues:
                    self.item(s, "issues", repo_id, issue_number)
            x.update({k: v for k, v in {"title": title, "body": body, "draft": draft, "state": state, "linked_issues": linked_issues}.items() if v is not None}); return copy.deepcopy(x)

    def submit_review(self, repo_id, number, event, body=""):
        if event not in ("APPROVE", "REQUEST_CHANGES", "COMMENT"):
            raise ValueError("event APPROVE/REQUEST_CHANGES/COMMENT")
        with self.session("submit_review", {"repo_id": repo_id, "number": number}) as s:
            p = self.repo(s, repo_id); x = self.item(s, "pull_requests", repo_id, number)
            if x["state"] != "open":
                raise ValueError("PR must be open")
            if x["author"] == s["current_user"] and event != "COMMENT":
                raise ValueError("Cannot approve or request changes on own PR")
            r = {"repo_id": repo_id, "number": number, "author": s["current_user"], "event": event, "body": body, "head_sha": self.ref(p, x["head"])}
            x["requested_reviewers"] = [name for name in x.get("requested_reviewers", []) if name != s["current_user"]]
            s["reviews"].append(r); return copy.deepcopy(r)

    def merge_pull_request(self, repo_id, number, expected_head_sha):
        with self.session("merge_pull_request", {"repo_id": repo_id, "number": number}) as s:
            p = self.repo(s, repo_id); x = self.item(s, "pull_requests", repo_id, number)
            head = self.ref(p, x["head"])
            if x["state"] != "open" or x["draft"] or head != expected_head_sha:
                raise ValueError("PR not ready or head changed")
            if self.run(p, "branch", "--show-current").strip() != x["base"] or self.run(p, "status", "--porcelain"):
                raise ValueError("Checkout base branch with clean index and working tree before merge")
            latest = {}
            for r in s["reviews"]:
                if r["repo_id"] == repo_id and r["number"] == number and r["head_sha"] == head and r["event"] != "COMMENT":
                    latest[r["author"]] = r["event"]
            required = next(r for r in s["repositories"] if r["id"] == repo_id).get("required_approvals", 0)
            if "REQUEST_CHANGES" in latest.values() or sum(e == "APPROVE" for e in latest.values()) < required:
                raise ValueError("Review requirements not met for current head")
            repository = next(r for r in s["repositories"] if r["id"] == repo_id)
            for check in repository.get("required_checks", []):
                runs = [r for r in s["workflow_runs"] if r["repo_id"] == repo_id and r.get("head_sha") == head and r.get("name") == check]
                latest_run = max(runs, key=lambda r: (r["id"], r.get("attempt", 1)), default={})
                if latest_run.get("status") != "completed" or latest_run.get("conclusion") != "success":
                    raise ValueError(f"Required check has not succeeded for current head: {check}")
            base_sha = self.ref(p, x["base"])
            self.run(p, "merge", "--no-ff", "--no-edit", "-m", f"Merge PR #{number}: {x['title']}", head, clock=s["now"])
            x.update(state="merged", merge_sha=self.ref(p, "HEAD"), merged_head_sha=head, merged_base_sha=base_sha)
            if x["base"] == repository.get("default_branch", "main"):
                for issue_number in x.get("linked_issues", []):
                    self.item(s, "issues", repo_id, issue_number)["state"] = "closed"
            return copy.deepcopy(x)

