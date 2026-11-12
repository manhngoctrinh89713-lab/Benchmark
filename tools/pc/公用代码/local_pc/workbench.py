"""Desktop startup, application settings and recycle bin."""
import copy
from local_maintenance.core import digest, page, text, boolean
from local_maintenance.settings import Settings


class PCWorkbench(Settings):
    def pc_copy_personal_file(self, source: str, destination: str, expected_sha256: str) -> dict:
        """复制个人文件到新位置，核对源文件且不覆盖目标。"""
        def apply(s, files):
            src = self.ensure_scope(s, source, "personal_roots")
            dst = self.ensure_scope(s, destination, "personal_roots")
            a, b = self.file_key(s, src), self.file_key(s, dst)
            if a not in files or digest(files[a]) != expected_sha256:
                raise ValueError("Source file changed")
            if b in files:
                raise FileExistsError(destination)
            self.write_checked(s, files, b, files[a], None)
            return {"source": src, "destination": dst, "sha256": expected_sha256}
        return self.mutate("pc_copy_personal_file", {"source": source, "destination": destination, "expected_sha256": expected_sha256}, apply)

    def pc_save_startup_item(self, name: str, app_id: str, enabled: bool = True, item_id: str | None = None) -> dict:
        """新增或修改应用开机启动项。"""
        def apply(s, files):
            app = self.get(s, "applications", app_id)
            if enabled and app["installed_version"] is None:
                raise ValueError("Startup app is not installed")
            items = s["startup_items"]
            old = self.get(s, "startup_items", item_id) if item_id else None
            if old and old["protected"]:
                raise PermissionError("Startup item is protected")
            rid = item_id or "startup_"+str(s["sequence"]+1)
            item = {"id": rid, "name": text(name, 200), "app_id": app_id, "enabled": enabled, "protected": False}
            items[rid] = item
            return {"startup_item": item}
        return self.mutate("pc_save_startup_item", {"name": name, "app_id": app_id, "enabled": enabled, "item_id": item_id}, apply)

    def pc_delete_startup_item(self, item_id: str) -> dict:
        """删除一个非系统保护的开机启动项。"""
        def apply(s, files):
            item = self.get(s, "startup_items", item_id)
            if item["protected"]:
                raise PermissionError("Startup item is protected")
            del s["startup_items"][item_id]
            return {"deleted_item_id": item_id}
        return self.mutate("pc_delete_startup_item", {"item_id": item_id}, apply)

    def pc_get_application_settings(self, app_id: str) -> dict:
        """读取应用设置及环境提供的可修改设置定义。"""
        with self.session() as (s, files):
            app = self.get(s, "applications", app_id)
            return {"app_id": app_id, "settings": copy.deepcopy(app.get("settings", {})), "settings_schema": copy.deepcopy(app.get("settings_schema", {}))}

    def pc_update_application_settings(self, app_id: str, values: dict) -> dict:
        """修改应用声明支持的设置，按类型、选项和数值范围校验。"""
        def apply(s, files):
            app = self.get(s, "applications", app_id)
            if app["installed_version"] is None or app["protected"]:
                raise ValueError("Application settings are unavailable")
            schema = app.get("settings_schema", {})
            if not values or not set(values) <= set(schema):
                raise ValueError("Use declared application settings")
            for key, value in values.items():
                spec = schema[key]
                kind = spec["type"]
                if kind == "boolean":
                    boolean(value)
                elif kind == "integer":
                    from local_maintenance.core import integer
                    integer(value, spec.get("min", 0), spec.get("max", 1000000000))
                elif kind == "string":
                    text(value, spec.get("max_length", 2000), True)
                else:
                    raise ValueError("Unsupported setting type")
                if "options" in spec and value not in spec["options"]:
                    raise ValueError("Invalid setting option")
            app.setdefault("settings", {}).update(copy.deepcopy(values))
            return {"app_id": app_id, "settings": app["settings"]}
        return self.mutate("pc_update_application_settings", {"app_id": app_id, "values": values}, apply)

    def pc_move_personal_file(self, source: str, destination: str, expected_sha256: str) -> dict:
        """移动或重命名个人文件，核对源文件且不覆盖目标。"""
        def apply(s, files):
            src = self.ensure_scope(s, source, "personal_roots")
            dst = self.ensure_scope(s, destination, "personal_roots")
            a, b = self.file_key(s, src), self.file_key(s, dst)
            if a not in files or digest(files[a]) != expected_sha256:
                raise ValueError("Source file changed")
            if b in files:
                raise FileExistsError(destination)
            self.ensure_unlocked(s, src)
            self.write_checked(s, files, b, files[a], None)
            del files[a]
            return {"source": src, "destination": dst, "sha256": expected_sha256}
        return self.mutate("pc_move_personal_file", {"source": source, "destination": destination, "expected_sha256": expected_sha256}, apply)

    def pc_recycle_file(self, path: str, expected_sha256: str) -> dict:
        """将个人文件移入回收站，保留内容和原始路径。"""
        def apply(s, files):
            target = self.ensure_scope(s, path, "personal_roots")
            key = self.file_key(s, target)
            if key not in files or digest(files[key]) != expected_sha256:
                raise ValueError("File changed")
            self.ensure_unlocked(s, target)
            rid = "recycle_"+str(s["sequence"]+1)
            stored = "recycle/"+rid
            files[stored] = files.pop(key)
            item = {"id": rid, "original_path": target, "stored_path": stored, "sha256": expected_sha256, "size_bytes": len(files[stored]), "deleted_at": s["now"]}
            s.setdefault("recycle_bin", {})[rid] = item
            return {"recycle_item": item}
        return self.mutate("pc_recycle_file", {"path": path, "expected_sha256": expected_sha256}, apply)

    def pc_list_recycle_bin(self, offset: int = 0, limit: int = 20) -> dict:
        """列出可恢复的个人文件。"""
        with self.session() as (s, files):
            return page(list(s.get("recycle_bin", {}).values()), offset, limit)

    def pc_restore_recycled_file(self, item_id: str, destination: str | None = None) -> dict:
        """从回收站恢复文件，已有目标不覆盖。"""
        def apply(s, files):
            r = self.get(s, "recycle_bin", item_id)
            target = self.ensure_scope(s, destination or r["original_path"], "personal_roots")
            key = self.file_key(s, target)
            if key in files:
                raise FileExistsError(target)
            self.write_checked(s, files, key, files[r["stored_path"]], None)
            del files[r["stored_path"]]
            del s["recycle_bin"][item_id]
            return {"restored_path": target, "sha256": r["sha256"]}
        return self.mutate("pc_restore_recycled_file", {"item_id": item_id, "destination": destination}, apply)

    def pc_delete_recycled_file(self, item_id: str) -> dict:
        """永久删除回收站文件并释放空间。"""
        def apply(s, files):
            r = self.get(s, "recycle_bin", item_id)
            del files[r["stored_path"]]
            del s["recycle_bin"][item_id]
            return {"deleted_item_id": item_id}
        return self.mutate("pc_delete_recycled_file", {"item_id": item_id}, apply)

    def pc_get_environment_variables(self, scope: str = "user") -> dict:
        """读取目标机器的用户或系统环境变量。"""
        return self._environment(scope)

    def pc_set_environment_variable(self, name: str, value: str | None, scope: str = "user") -> dict:
        """设置环境变量，null 删除变量；修改影响后续新建进程。"""
        return self._set_environment(name, value, scope)

    def pc_list_scheduled_tasks(self, offset: int = 0, limit: int = 20) -> dict:
        """列出目标机器的计划任务和下次执行时间。"""
        return self._list_tasks(offset, limit)

    def pc_save_scheduled_task(self, name: str, action: str, target_id: str, run_at: str, interval_seconds: int = 0, enabled: bool = True, task_id: str | None = None) -> dict:
        """新增或修改计划任务。电脑支持 application.launch；服务器支持 service.start/stop/restart/reload。零间隔为一次性任务。"""
        return self._save_task(name, action, target_id, run_at, interval_seconds, enabled, task_id)

    def pc_delete_scheduled_task(self, task_id: str) -> dict:
        """删除计划任务，保留既有执行记录。"""
        return self._delete_task(task_id)

    def pc_list_task_runs(self, task_id: str | None = None, offset: int = 0, limit: int = 20) -> dict:
        """查询计划任务的真实模型执行结果和失败信息。"""
        return self._task_runs(task_id, offset, limit)
