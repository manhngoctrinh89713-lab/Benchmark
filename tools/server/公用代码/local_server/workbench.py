"""Service startup policy, files, networking observations and scheduled work."""
from local_maintenance.core import digest, page, text, within
from local_maintenance.settings import Settings


class ServerWorkbench(Settings):
    def server_copy_file(self, source: str, destination: str, expected_sha256: str) -> dict:
        """复制常规文件到新路径，保留源文件且不覆盖目标。"""
        def apply(s, files):
            src, a = self._regular_path(s, source)
            dst, b = self._regular_path(s, destination)
            if a not in files or digest(files[a]) != expected_sha256:
                raise ValueError("Source file changed")
            if b in files:
                raise FileExistsError(destination)
            self.write_checked(s, files, b, files[a], None)
            return {"source": src, "destination": dst, "sha256": expected_sha256}
        return self.mutate("server_copy_file", {"source": source, "destination": destination, "expected_sha256": expected_sha256}, apply)

    def server_write_file(self, path: str, content: str, expected_sha256: str | None = None) -> dict:
        """在登记挂载点创建或修改文本文件；服务配置沿用专用配置入口。"""
        text(content, 200000, True)
        def apply(s, files):
            target, key = self._regular_path(s, path)
            self.write_checked(s, files, key, content.encode(), expected_sha256)
            return {"path": target, "size_bytes": len(files[key]), "sha256": digest(files[key])}
        return self.mutate("server_write_file", {"path": path, "content": content, "expected_sha256": expected_sha256}, apply)

    def _regular_path(self, s, path):
        target = self.canonical(path)
        key = self.file_key(s, target)
        if target == self.canonical(s["journal_path"]) or any(target == self.canonical(v["config_path"]) for v in s["services"].values()):
            raise ValueError("Use the service configuration or journal operation for this file")
        return target, key

    def server_delete_file(self, path: str, expected_sha256: str) -> dict:
        """删除常规文件，核对当前内容并检查进程占用。"""
        def apply(s, files):
            target, key = self._regular_path(s, path)
            if key not in files or digest(files[key]) != expected_sha256:
                raise ValueError("File missing or changed")
            self.ensure_unlocked(s, target)
            del files[key]
            return {"deleted_path": target, "sha256": expected_sha256}
        return self.mutate("server_delete_file", {"path": path, "expected_sha256": expected_sha256}, apply)

    def server_move_file(self, source: str, destination: str, expected_sha256: str) -> dict:
        """移动常规文件，不覆盖目标；服务配置和日志通过各自入口管理。"""
        def apply(s, files):
            src, a = self._regular_path(s, source)
            dst, b = self._regular_path(s, destination)
            if a not in files or digest(files[a]) != expected_sha256:
                raise ValueError("Source file changed")
            if b in files:
                raise FileExistsError(destination)
            self.ensure_unlocked(s, src)
            self.write_checked(s, files, b, files[a], None)
            del files[a]
            return {"source": src, "destination": dst, "sha256": expected_sha256}
        return self.mutate("server_move_file", {"source": source, "destination": destination, "expected_sha256": expected_sha256}, apply)

    def server_list_directory(self, path: str = "/", offset: int = 0, limit: int = 20) -> dict:
        """列出挂载点下的直接文件和目录，包括已登记的空目录。"""
        with self.session() as (s, files):
            target = self.canonical(path)
            self.disk_for(s, target)
            prefix = target.rstrip("/")+"/"
            result = {}
            paths = [self.virtual_path(s, k) for k in files if k.startswith("files/")] + list(s.get("directories", []))
            for candidate in paths:
                if not candidate.startswith(prefix):
                    continue
                suffix = candidate[len(prefix):]
                first = suffix.split("/", 1)[0]
                if not first:
                    continue
                child = prefix+first
                isdir = "/" in suffix or candidate in s.get("directories", [])
                if isdir:
                    result[child] = {"path": child, "type": "directory"}
                elif child not in result:
                    raw = files[self.file_key(s, child)]
                    result[child] = {"path": child, "type": "file", "size_bytes": len(raw), "sha256": digest(raw)}
            return page([result[k] for k in sorted(result)], offset, limit)

    def server_create_directory(self, path: str) -> dict:
        """登记空目录，后续文件可写入该目录。"""
        def apply(s, files):
            target = self.canonical(path)
            key = self.file_key(s, target)
            if key in files or any(key.startswith(k+"/") for k in files):
                raise FileExistsError(path)
            directories = s.setdefault("directories", [])
            if target not in directories:
                directories.append(target)
            return {"directory": target}
        return self.mutate("server_create_directory", {"path": path}, apply)

    def server_remove_directory(self, path: str) -> dict:
        """删除已登记的空目录。"""
        def apply(s, files):
            target = self.canonical(path)
            self.file_key(s, target)
            directories = s.setdefault("directories", [])
            if target not in directories:
                raise ValueError("Directory is not registered")
            if any(within(self.virtual_path(s, k), target) for k in files if k.startswith("files/")) or any(v != target and within(v, target) for v in directories):
                raise ValueError("Directory is not empty")
            directories.remove(target)
            return {"removed_directory": target}
        return self.mutate("server_remove_directory", {"path": path}, apply)

    def server_list_network_connections(self, state: str | None = None, port: int | None = None, offset: int = 0, limit: int = 20) -> dict:
        """查询环境最近记录的网络连接和监听端口，返回观测时间与所属进程。"""
        with self.session() as (s, files):
            return {**page([r for r in s.get("network_connections", []) if (state is None or r["state"] == state) and (port is None or r.get("local_port") == port or r.get("remote_port") == port)], offset, limit), "observed_at": s.get("network_observed_at")}

    def server_get_environment_variables(self, scope: str = "user") -> dict:
        """读取目标机器的用户或系统环境变量。"""
        return self._environment(scope)

    def server_set_environment_variable(self, name: str, value: str | None, scope: str = "user") -> dict:
        """设置环境变量，null 删除变量；修改影响后续新建进程。"""
        return self._set_environment(name, value, scope)

    def server_list_scheduled_tasks(self, offset: int = 0, limit: int = 20) -> dict:
        """列出目标机器的计划任务和下次执行时间。"""
        return self._list_tasks(offset, limit)

    def server_save_scheduled_task(self, name: str, action: str, target_id: str, run_at: str, interval_seconds: int = 0, enabled: bool = True, task_id: str | None = None) -> dict:
        """新增或修改计划任务。电脑支持 application.launch；服务器支持 service.start/stop/restart/reload。零间隔为一次性任务。"""
        return self._save_task(name, action, target_id, run_at, interval_seconds, enabled, task_id)

    def server_delete_scheduled_task(self, task_id: str) -> dict:
        """删除计划任务，保留既有执行记录。"""
        return self._delete_task(task_id)

    def server_list_task_runs(self, task_id: str | None = None, offset: int = 0, limit: int = 20) -> dict:
        """查询计划任务的真实模型执行结果和失败信息。"""
        return self._task_runs(task_id, offset, limit)
