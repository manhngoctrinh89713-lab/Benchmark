from datetime import timedelta

from local_maintenance.core import MaintenanceStore, boolean, digest, integer, moment, page, text, within
from local_maintenance.upstream_helpers import filter_windows_processes


from .workbench import PCWorkbench


class PCStore(PCWorkbench, MaintenanceStore):
    platform = "windows"
    prefix = "pc"

    @staticmethod
    def process_view(process, *, detail=False):
        # Task state is simulator truth, not operating-system telemetry.
        fields = ("pid", "name", "user", "status", "cpu_percent", "memory_bytes",
                  "protected", "app_id", "parent_pid", "started_at", "terminated_at")
        if detail:
            fields += ("command_line", "window_title", "open_files", "environment")
        return {key: process[key] for key in fields if key in process}

    def prepare(self,s,f):
        s["next_pid"] = max((p["pid"] for p in s["processes"].values()),default=1000)+1
        for name in f:
            s["file_times"].setdefault(name,s["now"])

    def pc_get_system_info(self):
        """读取场景Windows电脑的系统信息、内存、进程和磁盘概况。"""
        with self.session() as (s,f):
            return self.system_info(s,f)

    def pc_list_applications(self, query: str = "", installed_only: bool = True, offset: int = 0, limit: int = 20):
        """搜索应用目录；默认只看已安装应用，可查询可安装版本和占用。"""
        boolean(installed_only); text(query,200,True)
        with self.session() as (s,f):
            return page([a for a in s["applications"].values() if (not installed_only or a["installed_version"] is not None) and query.casefold() in (a["name"]+" "+a["id"]).casefold()],offset,limit)

    def pc_manage_application(self, app_id: str, operation: str, version: str | None = None):
        """在本地状态中安装、更新或卸载登记应用；运行中应用须先退出，磁盘占用同步变化。"""
        def apply(s,f):
            app = self.get(s,"applications",app_id)
            if app["protected"] or operation not in ("install","update","uninstall"):
                raise ValueError("Protected application or invalid operation")
            if operation == "uninstall":
                if version is not None or app["installed_version"] is None:
                    raise ValueError("Uninstall requires an installed app and no version")
            else:
                chosen = version or app["latest_version"]
                if chosen not in app["versions"]:
                    raise ValueError("Version is not present in the local package catalog")
                if (operation=="install") != (app["installed_version"] is None):
                    raise ValueError("Install requires absent app; update requires installed app")
                if operation=="update" and chosen==app["installed_version"]:
                    raise ValueError("Application already has this version")
            if any(p.get("app_id")==app_id and p["status"]!="terminated" for p in s["processes"].values()):
                raise ValueError("Exit associated processes before changing this app")
            app["installed_version"] = None if operation=="uninstall" else chosen
            if operation=="uninstall":
                for item in s["startup_items"].values():
                    if item.get("app_id")==app_id:
                        item["enabled"]=False
            return {"application":app,"operation":operation}
        return self.mutate("pc_manage_application",{"app_id":app_id,"operation":operation,"version":version},apply)

    def pc_launch_application(self, app_id: str):
        """为已安装应用创建本地模拟进程；不执行其命令或程序。"""
        def apply(s,f):
            app = self.get(s,"applications",app_id)
            if app["installed_version"] is None:
                raise ValueError("Application is not installed")
            pid = s["next_pid"]; s["next_pid"]+=1
            p = {"pid":pid,"name":app["process_name"],"user":s["machine"]["user"],"status":"running","cpu_percent":0.0,"memory_bytes":app["launch_memory_bytes"],"protected":False,"app_id":app_id,"started_at":s["now"],"open_files":[]}
            p["environment"] = {**s.get("environment_variables", {}).get("system", {}), **s.get("environment_variables", {}).get("user", {})}
            s["processes"][str(pid)]=p
            return {"process":self.process_view(p, detail=True)}
        return self.mutate("pc_launch_application",{"app_id":app_id},apply)

    def pc_list_processes(self, query: str = "", sort_by: str = "memory", offset: int = 0, limit: int = 20):
        """按名称搜索当前进程并按内存、CPU或PID排序；使用提取的上游进程过滤逻辑。"""
        text(query,200,True)
        if sort_by not in ("memory","cpu","pid"):
            raise ValueError("sort_by must be memory/cpu/pid")
        with self.session() as (s,f):
            rows = filter_windows_processes(query,[p for p in s["processes"].values() if p["status"]!="terminated"])
            key = {"memory":"memory_bytes","cpu":"cpu_percent","pid":"pid"}[sort_by]
            ordered = sorted(rows,key=lambda p:((-p[key]) if sort_by!="pid" else p[key],p["pid"]))
            return page([self.process_view(p) for p in ordered],offset,limit)

    def pc_get_process(self, pid: int):
        """读取指定场景PID的状态、应用关联、资源和打开文件；含已终止记录。"""
        integer(pid,1,2**31-1)
        with self.session() as (s,f):
            return {"process":self.process_view(self.get(s,"processes",str(pid)), detail=True)}

    def pc_change_process(self, pid: int, operation: str):
        """挂起、恢复或终止指定模拟进程；保护系统进程，不使用宿主机PID。"""
        integer(pid,1,2**31-1)
        def apply(s,f):
            p = self.get(s,"processes",str(pid))
            if p["protected"] or p["status"]=="terminated":
                raise ValueError("Protected or terminated process")
            before_status = p["status"]
            if operation=="terminate":
                p.update(status="terminated",cpu_percent=0.0,terminated_at=s["now"])
            elif operation=="suspend" and p["status"]=="running":
                p.update(status="suspended",cpu_percent=0.0)
            elif operation=="resume" and p["status"]=="suspended":
                p["status"]="running"
            else:
                raise ValueError("Invalid process operation/state")
            # 场景任务随原进程存活；重新启动应用不会恢复该任务。
            task = p.get("current_task")
            if task:
                task["status"] = {"terminate":"interrupted", "suspend":"paused", "resume":"running"}[operation]
                if operation == "terminate":
                    task["interrupted_at"] = s["now"]
                    task["interruption_reason"] = "owner_process_terminated"
            # 仅为声明事件存储的场景记录成功变更；与状态在同一事务提交。
            if "process_events" in s:
                s["process_events"].append({"sequence":s["sequence"]+1, "at":s["now"],
                    "action":"pc_change_process", "pid":pid, "operation":operation,
                    "before_status":before_status, "after_status":p["status"],
                    "task_id":task["id"] if task else None})
            return {"process":self.process_view(p, detail=True)}
        return self.mutate("pc_change_process",{"pid":pid,"operation":operation},apply)

    def pc_list_startup_items(self, offset: int = 0, limit: int = 20):
        """列出模拟Windows开机启动项、来源、应用和启用状态。"""
        with self.session() as (s,f):
            return page(list(s["startup_items"].values()),offset,limit)

    def pc_set_startup_item(self, item_id: str, enabled: bool):
        """启用或禁用登记启动项；不修改真实注册表或启动文件夹。"""
        boolean(enabled)
        def apply(s,f):
            item = self.get(s,"startup_items",item_id)
            if item["protected"]:
                raise ValueError("Startup item is protected")
            if enabled and item.get("app_id") and self.get(s,"applications",item["app_id"])["installed_version"] is None:
                raise ValueError("Startup application is not installed")
            item["enabled"]=enabled
            return {"startup_item":item}
        return self.mutate("pc_set_startup_item",{"item_id":item_id,"enabled":enabled},apply)

    def pc_get_disk_usage(self):
        """按模拟卷统计系统基础占用、应用、真实场景文件和ZIP备份占用。"""
        with self.session() as (s,f):
            return {"disks":self.disk_usage(s,f)}

    def pc_analyze_directory(self, path: str, limit: int = 20):
        """分析登记磁盘内目录的真实场景文件大小、数量和大文件。"""
        return self.analyze_directory(path,limit)

    def pc_list_cache_locations(self):
        """列出可清理的登记缓存位置、实际文件数量和占用。"""
        with self.session() as (s,f):
            rows = []
            for cache in s["caches"].values():
                entries = self.directory_rows(s,f,cache["path"])
                rows.append({**cache,"file_count":len(entries),"size_bytes":sum(e["size_bytes"] for e in entries)})
            return {"items":rows}

    def pc_clean_cache(self, cache_id: str, older_than_days: int = 0, dry_run: bool = True):
        """预览或清理登记缓存中的过期文件，跳过模拟进程正在使用的文件。"""
        integer(older_than_days,0,36500); boolean(dry_run)
        def apply(s,f):
            cache = self.get(s,"caches",cache_id)
            cutoff = moment(s["now"])-timedelta(days=older_than_days)
            locked = {self.canonical(path) for p in s["processes"].values() if p["status"]!="terminated" for path in p.get("open_files",[])}
            selected,skipped = [],[]
            for row in self.directory_rows(s,f,cache["path"]):
                if moment(row["modified_at"])>cutoff:
                    continue
                if row["path"] in locked:
                    skipped.append(row["path"])
                else:
                    selected.append(row)
            if not dry_run:
                for row in selected:
                    del f[self.file_key(s,row["path"])]
            return {"dry_run":dry_run,"files":selected,"skipped_locked":skipped,"reclaimed_bytes":sum(r["size_bytes"] for r in selected)}
        if dry_run:
            with self.session() as (s,f):
                return apply(s,f)
        return self.mutate("pc_clean_cache",{"cache_id":cache_id,"older_than_days":older_than_days,"dry_run":False},apply)

    def pc_list_personal_files(self, path: str | None = None, offset: int = 0, limit: int = 20):
        """在登记个人文件根内分页列出真实文件、大小和哈希。"""
        with self.session() as (s,f):
            paths = [self.ensure_scope(s,path,"personal_roots")] if path is not None else s["personal_roots"]
            rows = {r["path"]:r for p in paths for r in self.directory_rows(s,f,p)}
            return page([rows[k] for k in sorted(rows)],offset,limit)

    def pc_read_personal_file(self, path: str):
        """读取登记个人文件中的UTF-8文本及原始字节SHA-256。"""
        with self.session() as (s,f):
            path = self.ensure_scope(s,path,"personal_roots"); key = self.file_key(s,path)
            if key not in f:
                raise FileNotFoundError(path)
            if len(f[key])>200000:
                raise ValueError("Text exceeds 200000 bytes")
            return {"path":path,"content":f[key].decode("utf-8-sig"),"sha256":digest(f[key])}

    def pc_write_personal_file(self, path: str, content: str, expected_sha256: str | None = None):
        """创建或更新个人文本文件；更新必须提供原字节哈希以防覆盖其他修改。"""
        text(content,200000,True)
        def apply(s,f):
            target = self.ensure_scope(s,path,"personal_roots"); key = self.file_key(s,target)
            self.write_checked(s,f,key,content.encode(),expected_sha256)
            return {"path":target,"size_bytes":len(f[key]),"sha256":digest(f[key])}
        return self.mutate("pc_write_personal_file",{"path":path,"content":content,"expected_sha256":expected_sha256},apply)

    def pc_delete_personal_file(self, path: str, expected_sha256: str):
        """按预期哈希删除一个个人文件；模拟进程使用中的文件不能删除。"""
        def apply(s,f):
            target = self.ensure_scope(s,path,"personal_roots"); key = self.file_key(s,target)
            if key not in f or digest(f[key])!=expected_sha256:
                raise ValueError("File missing or hash changed")
            self.ensure_unlocked(s,target)
            raw = f.pop(key)
            return {"path":target,"deleted_bytes":len(raw),"sha256":digest(raw)}
        return self.mutate("pc_delete_personal_file",{"path":path,"expected_sha256":expected_sha256},apply)

    def pc_create_backup(self, paths: list[str], label: str, idempotency_key: str):
        """将登记个人文件备份为真实ZIP及校验清单；支持幂等重试。"""
        return self.create_backup(paths,label,idempotency_key)

    def pc_list_backups(self, offset: int = 0, limit: int = 20):
        """分页列出当前电脑的备份记录及归档哈希。"""
        return self.list_backups(offset,limit)

    def pc_verify_backup(self, backup_id: str):
        """校验ZIP整体哈希、清单、逐文件内容和恢复路径范围。"""
        return self.verify_backup(backup_id)

    def pc_restore_backup(self, backup_id: str, idempotency_key: str, overwrite: bool = False):
        """从已校验ZIP恢复原个人文件；默认拒绝覆盖，可幂等重试。"""
        return self.restore_backup(backup_id,idempotency_key,overwrite)

    def pc_delete_backup(self, backup_id: str):
        """删除一个本地ZIP备份和记录，释放模拟备份磁盘空间。"""
        return self.delete_backup(backup_id)

    def validate(self,s,f):
        super().validate(s,f)
        for key,app in s["applications"].items():
            if key!=app["id"] or app["disk_id"] not in {d["id"] for d in s["disks"]} or app["latest_version"] not in app["versions"] or (app["installed_version"] is not None and app["installed_version"] not in app["versions"]):
                raise ValueError("Invalid application catalog/version/disk")
            text(app["name"],200); text(app["process_name"],200); boolean(app["protected"]); integer(app["launch_memory_bytes"])
            for version,data in app["versions"].items():
                text(version,100); integer(data["size_bytes"],1)
        for key,item in s["startup_items"].items():
            if key!=item["id"]:
                raise ValueError("Startup identity does not match its key")
            boolean(item["enabled"]); boolean(item["protected"])
            if item.get("app_id"):
                app = self.get(s,"applications",item["app_id"])
                if item["enabled"] and app["installed_version"] is None:
                    raise ValueError("Enabled startup app is not installed")
        roots = []
        for key,cache in s["caches"].items():
            if key!=cache["id"] or self.canonical(cache["path"])!=cache["path"]:
                raise ValueError("Invalid cache path")
            self.disk_for(s,cache["path"])
            for root in s["personal_roots"]+roots:
                if within(cache["path"],root) or within(root,cache["path"]):
                    raise ValueError("Cache roots must not overlap personal roots or each other")
            roots.append(cache["path"])
        for p in s["processes"].values():
            if p.get("app_id"):
                app = self.get(s,"applications",p["app_id"])
                if p["status"]!="terminated" and app["installed_version"] is None:
                    raise ValueError("Active process references an absent application")
