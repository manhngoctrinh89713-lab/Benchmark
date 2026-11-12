"""Machine environment and scheduled resource operations."""
import copy
import re
from .core import boolean, integer, moment, page, text


class Settings:
    def _environment(self, scope):
        if scope not in {"user", "system"}:
            raise ValueError("scope: user/system")
        with self.session() as (s, files):
            return {"scope": scope, "variables": copy.deepcopy(s.get("environment_variables", {}).get(scope, {})), "effective_for": "new processes"}

    def _set_environment(self, name, value, scope):
        if scope not in {"user", "system"} or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", name):
            raise ValueError("Invalid scope or variable name")
        if value is not None:
            text(value, 8192, True)
        def apply(s, files):
            values = s.setdefault("environment_variables", {}).setdefault(scope, {})
            if value is not None and name not in values and len(values) >= 100:
                raise ValueError("At most 100 variables per scope")
            key = next((k for k in values if k.casefold() == name.casefold()), name) if self.platform == "windows" else name
            if value is None:
                values.pop(key, None)
            else:
                values[key] = value
            return {"scope": scope, "name": key, "value": value, "effective_for": "new processes"}
        return self.mutate(self.prefix+"_set_environment_variable", {"name": name, "value": value, "scope": scope}, apply)

    def _list_tasks(self, offset, limit):
        with self.session() as (s, files):
            return page(list(s.get("scheduled_tasks", {}).values()), offset, limit)

    def _save_task(self, name, action, target_id, run_at, interval_seconds, enabled, task_id):
        text(name, 200)
        at = moment(run_at)
        integer(interval_seconds, 0, 31536000)
        if interval_seconds and interval_seconds < 60:
            raise ValueError("Recurring tasks require an interval of at least 60 seconds")
        boolean(enabled)
        def apply(s, files):
            allowed = {"application.launch"} if self.platform == "windows" else {"service.start", "service.stop", "service.restart", "service.reload"}
            if action not in allowed:
                raise ValueError("Action is not supported by this task scheduler")
            resource = self.get(s, "applications" if self.platform == "windows" else "services", target_id)
            if self.platform == "windows" and resource["installed_version"] is None or self.platform == "linux" and resource["protected"]:
                raise ValueError("Target is unavailable for scheduling")
            if at <= moment(s["now"]):
                raise ValueError("run_at must be in the future")
            tasks = s.setdefault("scheduled_tasks", {})
            if task_id is None and len(tasks) >= 100:
                raise ValueError("At most 100 scheduled tasks")
            if task_id is not None and task_id not in tasks:
                raise ValueError("Unknown scheduled task")
            rid = task_id or "task_"+str(s["sequence"]+1)
            t = {"id": rid, "name": name, "action": action, "target_id": target_id, "next_run_at": at.isoformat(), "interval_seconds": interval_seconds, "enabled": enabled, "version": tasks.get(rid, {}).get("version", 0)+1}
            tasks[rid] = t
            return {"scheduled_task": t}
        return self.mutate(self.prefix+"_save_scheduled_task", {"name": name, "action": action, "target_id": target_id, "run_at": run_at, "interval_seconds": interval_seconds, "enabled": enabled, "task_id": task_id}, apply)

    def _delete_task(self, task_id):
        def apply(s, files):
            tasks = s.setdefault("scheduled_tasks", {})
            if task_id not in tasks:
                raise ValueError("Unknown scheduled task")
            old = tasks.pop(task_id)
            return {"deleted_task": old}
        return self.mutate(self.prefix+"_delete_scheduled_task", {"task_id": task_id}, apply)

    def _task_runs(self, task_id, offset, limit):
        with self.session() as (s, files):
            return page([r for r in s.get("task_runs", []) if task_id is None or r["task_id"] == task_id], offset, limit)
