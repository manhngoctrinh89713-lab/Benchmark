import configparser
import json
import re

from local_maintenance.core import MaintenanceStore, boolean, digest, integer, moment, page, text
from local_maintenance.upstream_helpers import parse_ps_output

from .workbench import ServerWorkbench


class ServerStore(ServerWorkbench, MaintenanceStore):
    platform = "linux"
    prefix = "server"

    def prepare(self,s,f):
        parsed = parse_ps_output(s.pop("process_snapshot"))
        if not parsed or len({p.pid for p in parsed})!=len(parsed):
            raise ValueError("Initial ps snapshot requires distinct valid processes")
        metadata = s.pop("process_metadata",{})
        if set(metadata)-{str(p.pid) for p in parsed}:
            raise ValueError("Process metadata references an absent PID")
        s["processes"]={}
        for p in parsed:
            extra = metadata.get(str(p.pid),{})
            row = {"pid":p.pid,"name":p.command.split()[0].rsplit("/",1)[-1],"command":p.command,"user":p.user,"status":"suspended" if p.stat.startswith("T") else "running","cpu_percent":p.cpu_percent,"memory_bytes":p.rss*1024,"protected":extra.get("protected",p.pid==1),"started_at":extra.get("started_at",s["now"]),"open_files":extra.get("open_files",[])}
            s["processes"][str(p.pid)]=row
        s["next_pid"] = max(p.pid for p in parsed)+1
        for service in s["services"].values():
            key = self.file_key(s,service["config_path"])
            service.setdefault("applied_config_sha256",digest(f[key]) if service["active_state"]=="active" else None)
            if service["main_pid"] is not None:
                self.get(s,"processes",str(service["main_pid"]))["service_id"]=service["id"]
        f.setdefault(self.file_key(s,s["journal_path"]),b"")
        for key in f:
            s["file_times"].setdefault(key,s["now"])

    def journal(self,s,f):
        raw = f[self.file_key(s,s["journal_path"])]
        return [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]

    def log(self,s,f,service_id,priority,message):
        key = self.file_key(s,s["journal_path"])
        row = {"timestamp":s["now"],"service_id":service_id,"priority":priority,"message":message}
        prefix=f.get(key,b"")
        if prefix and not prefix.endswith(b"\n"):
            prefix+=b"\n"
        f[key] = prefix+(json.dumps(row,ensure_ascii=False)+"\n").encode()

    def write_checked(self,state,files,key,raw,expected_sha256):
        if any(v["protected"] and self.file_key(state,v["config_path"])==key for v in state["services"].values()):
            raise ValueError("Service configuration is protected")
        return super().write_checked(state,files,key,raw,expected_sha256)

    def config_values(self,service,raw):
        """Parse a service configuration body into flat values."""
        values={}
        body = raw.decode("utf-8-sig") if isinstance(raw,(bytes,bytearray)) else raw
        if service["config_format"]=="json":
            obj = json.loads(body)
            if not isinstance(obj,dict):
                raise ValueError("JSON root must be an object")
            def flatten(value,prefix=""):
                for key,item in value.items():
                    name = prefix+key
                    if isinstance(item,dict):
                        flatten(item,name+".")
                    else:
                        values[name]=item
            flatten(obj)
        elif service["config_format"]=="ini":
            parser = configparser.ConfigParser(interpolation=None,strict=True)
            parser.optionxform=str
            parser.read_string(body)
            values = {section+"."+key:value for section in parser.sections() for key,value in parser.items(section)}
        elif service["config_format"]=="env":
            for line in body.splitlines():
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                if "=" not in line:
                    raise ValueError("Environment line needs KEY=VALUE")
                key,value = line.split("=",1); key=key.strip(); value=value.strip()
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*",key) or key in values:
                    raise ValueError("Invalid or duplicate environment key")
                values[key]=value
        else:
            raise ValueError("Unsupported configuration format")
        return values

    def config_result(self,s,f,service):
        raw = f[self.file_key(s,service["config_path"])]; errors=[]; values={}
        try:
            values = self.config_values(service,raw)
            for rule in service["config_rules"]:
                key=rule["key"]
                if key not in values:
                    errors.append(f"Missing key: {key}"); continue
                value=values[key]
                if rule["type"]=="integer":
                    if type(value) is bool or not re.fullmatch(r"-?[0-9]+",str(value)):
                        errors.append(f"{key}: expected integer"); continue
                    value=int(value)
                    if not rule.get("min",-10**15)<=value<=rule.get("max",10**15):
                        errors.append(f"{key}: outside configured range")
                elif rule["type"]=="boolean":
                    if type(value) is not bool and value not in ("true","false"):
                        errors.append(f"{key}: expected boolean")
                elif rule["type"]=="text":
                    if not isinstance(value,str) or not value.strip():
                        errors.append(f"{key}: expected nonempty text")
                else:
                    raise ValueError("Unknown config rule type")
        except (ValueError,UnicodeError,configparser.Error) as error:
            errors.append(str(error))
        return {"service_id":service["id"],"path":service["config_path"],"sha256":digest(raw),"valid":not errors,"errors":errors,"validator":"local declared JSON/INI/ENV rules"}

    def service_view(self,s,f,service):
        key = self.file_key(s,service["config_path"])
        return {**service,"config_sha256":digest(f[key]),"config_pending":digest(f[key])!=service["applied_config_sha256"],"unavailable_dependencies":[d for d in service["requires"] if s["services"][d]["active_state"]!="active"]}

    def server_get_system_info(self):
        """读取模拟Linux系统、资源、磁盘及失败服务概况。"""
        with self.session() as (s,f):
            return {**self.system_info(s,f),"failed_services":[v["id"] for v in s["services"].values() if v["active_state"]=="failed"]}

    def server_list_services(self, state: str | None = None, query: str = "", offset: int = 0, limit: int = 20):
        """按active/inactive/failed和名称搜索本服务器的systemd服务。"""
        if state not in (None,"active","inactive","failed"):
            raise ValueError("Invalid service state")
        text(query,200,True)
        with self.session() as (s,f):
            return page([self.service_view(s,f,v) for v in s["services"].values() if (state is None or v["active_state"]==state) and query.casefold() in (v["id"]+" "+v["description"]).casefold()],offset,limit)

    def server_get_service(self, service_id: str):
        """读取服务启用/运行状态、主PID、依赖及磁盘配置与生效配置的哈希差异。"""
        with self.session() as (s,f):
            return {"service":self.service_view(s,f,self.get(s,"services",service_id))}

    def server_change_service(self, service_id: str, operation: str):
        """模拟start/stop/restart/reload/enable/disable，联动进程和日志；启动校验配置及依赖。"""
        def apply(s,f):
            service = self.get(s,"services",service_id)
            if service["protected"] or operation not in ("start","stop","restart","reload","enable","disable"):
                raise ValueError("Protected service or invalid operation")
            if operation in ("enable","disable"):
                service["enabled"]=operation=="enable"
            elif operation=="stop":
                self.stop_process(s,service)
                service["active_state"]="inactive"
            else:
                if operation=="start" and service["active_state"]=="active":
                    return {"success":True,"changed":False,"service":self.service_view(s,f,service)}
                if operation=="reload" and (service["active_state"]!="active" or not service["supports_reload"]):
                    raise ValueError("Reload requires an active reload-capable service")
                if operation=="reload":
                    current_raw = f[self.file_key(s,service["config_path"])]
                    applied_raw = service.get("applied_config")
                    if applied_raw is None and service.get("applied_config_sha256"):
                        # Older fixtures only carry the applied hash; do not block reloads
                        # when the current file still matches it.
                        applied_raw = current_raw if digest(current_raw)==service["applied_config_sha256"] else None
                    if applied_raw is not None:
                        try:
                            current_values = self.config_values(service,current_raw)
                            applied_values = self.config_values(service,applied_raw)
                        except (ValueError,UnicodeError,configparser.Error):
                            current_values = applied_values = None
                        if current_values is not None:
                            restart_only = [rule["key"] for rule in service["config_rules"]
                                            if rule.get("restart_required") and current_values.get(rule["key"]) != applied_values.get(rule["key"])]
                            if restart_only:
                                raise ValueError("Configuration requires restart for key(s): "+", ".join(restart_only))
                validation = self.config_result(s,f,service)
                absent = [d for d in service["requires"] if s["services"][d]["active_state"]!="active"]
                if operation=="restart":
                    self.stop_process(s,service)
                if not validation["valid"] or absent:
                    if operation!="reload":
                        service["active_state"]="failed"
                    self.log(s,f,service_id,3,"Service operation failed: invalid configuration or unavailable dependency")
                    return {"success":False,"service":self.service_view(s,f,service),"validation":validation,"unavailable_dependencies":absent}
                if operation!="reload":
                    pid=s["next_pid"]; s["next_pid"]+=1
                    s["processes"][str(pid)]={"pid":pid,"name":service["process_name"],"command":service["command"],"user":service["user"],"status":"running","cpu_percent":0.0,"memory_bytes":service["memory_bytes"],"protected":False,"started_at":s["now"],"open_files":[],"service_id":service_id}
                    s["processes"][str(pid)]["environment"] = dict(s.get("environment_variables", {}).get("system", {}))
                    service.update(main_pid=pid,active_state="active")
                service["applied_config_sha256"]=validation["sha256"]
                service["applied_config"]=f[self.file_key(s,service["config_path"])].decode("utf-8-sig")
                s.setdefault("config_load_events", []).append({
                    "sequence": s["sequence"] + 1, "at": s["now"],
                    "service_id": service_id, "operation": operation,
                    "sha256": validation["sha256"],
                    "content": f[self.file_key(s,service["config_path"])].decode("utf-8-sig")})
            self.log(s,f,service_id,6,"Service operation: "+operation)
            return {"success":True,"service":self.service_view(s,f,service)}
        return self.mutate("server_change_service",{"service_id":service_id,"operation":operation},apply)

    @staticmethod
    def stop_process(s,service):
        if service["main_pid"] is not None:
            p=s["processes"][str(service["main_pid"])]; p.update(status="terminated",cpu_percent=0.0,terminated_at=s["now"])
        service["main_pid"]=None

    def permission_path(self,s,path):
        path=self.canonical(path)
        self.disk_for(s,path)
        return path

    @staticmethod
    def mode_text(value):
        return format(value,"04o")

    @staticmethod
    def parse_mode(value):
        if not isinstance(value,str) or not re.fullmatch(r"0?[0-7]{3,4}",value.strip()):
            raise ValueError("mode must be an octal string such as 0755")
        return int(value.strip(),8)&0o7777

    def server_get_permissions(self, path: str, recursive: bool = False):
        """读取服务器路径的所有者、用户组和权限模式；可选包含整棵子树。"""
        with self.session() as (s,f):
            path=self.permission_path(s,path)
            entries=[]
            for name,perm in s.get("path_permissions",{}).items():
                if name==path or (recursive and name.startswith(path.rstrip("/")+"/")):
                    entries.append({"path":name,"owner":perm["owner"],"group":perm["group"],
                                    "mode":self.mode_text(perm["mode"])})
            if not entries and path in {self.virtual_path(s,k) for k in f if k.startswith("files/")}:
                entries=[{"path":path,"owner":"root","group":"root","mode":"0644"}]
            if not entries:
                raise FileNotFoundError(path)
            return {"path":path,"entries":sorted(entries,key=lambda x:x["path"])}

    def server_set_permissions(self, path: str, owner: str | None = None,
                               group: str | None = None, mode: str | None = None,
                               recursive: bool = False):
        """调整服务器路径的所有者、用户组和权限模式；可递归应用于子树。"""
        if owner is None and group is None and mode is None:
            raise ValueError("At least one of owner/group/mode is required")
        for value,label in ((owner,"owner"),(group,"group")):
            if value is not None and (not isinstance(value,str) or not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}",value)):
                raise ValueError("Invalid "+label)
        parsed_mode=self.parse_mode(mode) if mode is not None else None
        def apply(s,f):
            target=self.permission_path(s,path)
            perms=s.setdefault("path_permissions",{})
            selected=[name for name in perms if name==target or (recursive and name.startswith(target.rstrip("/")+"/"))]
            if not selected:
                raise FileNotFoundError(target)
            changes={}
            for name in sorted(selected):
                before=dict(perms[name])
                after=dict(before)
                if owner is not None: after["owner"]=owner
                if group is not None: after["group"]=group
                if parsed_mode is not None: after["mode"]=parsed_mode
                perms[name]=after
                changes[name]={"before":before,"after":after}
            s.setdefault("permission_events",[]).append({
                "sequence":s["sequence"]+1,"action":"server_set_permissions",
                "path":target,"recursive":recursive,"changes":changes})
            return {"path":target,"recursive":recursive,"changed":changes,
                    "entries":[{"path":name,"owner":perms[name]["owner"],
                                "group":perms[name]["group"],
                                "mode":self.mode_text(perms[name]["mode"])}
                               for name in sorted(selected)]}
        return self.mutate("server_set_permissions",
                           {"path":path,"owner":owner,"group":group,"mode":mode,"recursive":recursive},apply)

    def server_reboot(self, reason: str = ""):
        """模拟重启整机：停止所有服务并记录重启事件。"""
        text(reason,200,True)
        def apply(s,f):
            for service in s["services"].values():
                if service["main_pid"] is not None:
                    self.stop_process(s,service)
                service["active_state"]="inactive"
                service["main_pid"]=None
            for pid,proc in s["processes"].items():
                if pid!="1" and proc["status"]=="running":
                    proc.update(status="terminated",cpu_percent=0.0,terminated_at=s["now"])
            s.setdefault("reboot_events",[]).append({
                "sequence":s["sequence"]+1,"at":s["now"],"reason":reason or "requested"})
            return {"rebooted":True}
        return self.mutate("server_reboot",{"reason":reason},apply)

    def server_read_service_config(self, service_id: str):
        """读取登记服务配置的真实UTF-8文本和SHA-256，不读取宿主机/etc。"""
        with self.session() as (s,f):
            service=self.get(s,"services",service_id); raw=f[self.file_key(s,service["config_path"])]
            return {"service_id":service_id,"path":service["config_path"],"content":raw.decode("utf-8-sig"),"sha256":digest(raw),"applied_sha256":service["applied_config_sha256"]}

    def server_write_service_config(self, service_id: str, content: str, expected_sha256: str):
        """按原文件哈希保存待生效配置；允许先保存错误配置，校验及reload/restart另行调用。"""
        text(content,200000,True)
        def apply(s,f):
            service=self.get(s,"services",service_id)
            if service["protected"]:
                raise ValueError("Service configuration is protected")
            key=self.file_key(s,service["config_path"])
            self.write_checked(s,f,key,content.encode(),expected_sha256)
            return {"service":self.service_view(s,f,service),"validation":self.config_result(s,f,service)}
        return self.mutate("server_write_service_config",{"service_id":service_id,"content":content,"expected_sha256":expected_sha256},apply)

    def server_validate_service_config(self, service_id: str):
        """按场景声明的JSON/INI/ENV语法和必填字段规则校验真实配置；不运行服务二进制。"""
        with self.session() as (s,f):
            return self.config_result(s,f,self.get(s,"services",service_id))

    def server_list_processes(self, query: str = "", sort_by: str = "memory", offset: int = 0, limit: int = 20):
        """搜索当前进程命令并排序；初始进程由提取的Linux MCP ps解析器读入。"""
        text(query,200,True)
        if sort_by not in ("memory","cpu","pid"):
            raise ValueError("sort_by must be memory/cpu/pid")
        with self.session() as (s,f):
            key={"memory":"memory_bytes","cpu":"cpu_percent","pid":"pid"}[sort_by]
            rows=[p for p in s["processes"].values() if p["status"]!="terminated" and query.casefold() in p["command"].casefold()]
            return page(sorted(rows,key=lambda p:((-p[key]) if sort_by!="pid" else p[key],p["pid"])),offset,limit)

    def server_get_process(self, pid: int):
        """读取场景PID详情、服务关联及资源，包含已终止进程。"""
        integer(pid,1,2**31-1)
        with self.session() as (s,f):
            return {"process":self.get(s,"processes",str(pid))}

    def server_signal_process(self, pid: int, signal: str = "TERM"):
        """向模拟进程发送TERM/KILL/STOP/CONT；主进程终止会使关联服务失败并写日志。"""
        integer(pid,1,2**31-1)
        def apply(s,f):
            p=self.get(s,"processes",str(pid))
            if p["protected"] or p["status"]=="terminated" or (p.get("service_id") and s["services"][p["service_id"]]["protected"]):
                raise ValueError("Protected or terminated process")
            if signal in ("TERM","KILL"):
                p.update(status="terminated",cpu_percent=0.0,terminated_at=s["now"])
                if p.get("service_id"):
                    service=self.get(s,"services",p["service_id"])
                    if service["protected"]:
                        raise ValueError("Service is protected")
                    service.update(active_state="failed",main_pid=None)
                    self.log(s,f,service["id"],3,"Main process terminated by "+signal)
            elif signal=="STOP" and p["status"]=="running":
                p.update(status="suspended",cpu_percent=0.0)
            elif signal=="CONT" and p["status"]=="suspended":
                p["status"]="running"
            else:
                raise ValueError("Invalid signal/process state")
            return {"process":p}
        return self.mutate("server_signal_process",{"pid":pid,"signal":signal},apply)

    def server_query_logs(self, service_id: str | None = None, max_priority: int = 7, since: str | None = None, until: str | None = None, query: str = "", offset: int = 0, limit: int = 20):
        """查询真实场景JSONL日志；优先级0最严重，筛选0..max_priority，结果按时间倒序。"""
        integer(max_priority,0,7); text(query,200,True)
        start,end=moment(since) if since else None,moment(until) if until else None
        if start and end and start>end:
            raise ValueError("since must not exceed until")
        with self.session() as (s,f):
            if service_id is not None:
                self.get(s,"services",service_id)
            rows=[r for r in self.journal(s,f) if (service_id is None or r["service_id"]==service_id) and r["priority"]<=max_priority and (start is None or moment(r["timestamp"])>=start) and (end is None or moment(r["timestamp"])<=end) and query.casefold() in r["message"].casefold()]
            return page(sorted(rows,key=lambda r:moment(r["timestamp"]),reverse=True),offset,limit)

    def server_prune_logs(self, service_id: str, keep_last: int = 100, dry_run: bool = True):
        """预览或删除指定服务较早的日志，保留最新keep_last条；其他服务日志保持不变。"""
        integer(keep_last,0,10000); boolean(dry_run)
        def apply(s,f):
            self.get(s,"services",service_id)
            key=self.file_key(s,s["journal_path"])
            old=f[key]; lines=old.splitlines(keepends=True)
            rows={i:json.loads(line) for i,line in enumerate(lines) if line.strip()}
            selected=sorted([i for i,r in rows.items() if r["service_id"]==service_id],key=lambda i:(moment(rows[i]["timestamp"]),i),reverse=True)
            removed=set(selected[keep_last:])
            raw=b"".join(line for i,line in enumerate(lines) if i not in removed)
            if not dry_run:
                f[key]=raw
            return {"dry_run":dry_run,"removed_count":len(removed),"remaining_count":len(rows)-len(removed),"reclaimed_bytes":len(old)-len(raw)}
        if dry_run:
            with self.session() as (s,f):
                return apply(s,f)
        return self.mutate("server_prune_logs",{"service_id":service_id,"keep_last":keep_last,"dry_run":False},apply)

    def server_get_disk_usage(self):
        """读取模拟挂载点的基础、真实配置/日志/数据文件及备份占用。"""
        with self.session() as (s,f):
            return {"disks":self.disk_usage(s,f)}

    def server_analyze_directory(self, path: str, limit: int = 20):
        """按Linux绝对路径分析真实场景文件的大小、数量和大文件。"""
        return self.analyze_directory(path,limit)

    def server_read_file(self, path: str):
        """读取登记挂载点内的UTF-8场景文件、大小和哈希；最多200000字节。"""
        with self.session() as (s,f):
            path=self.canonical(path); key=self.file_key(s,path)
            if key not in f:
                raise FileNotFoundError(path)
            if len(f[key])>200000:
                raise ValueError("Text exceeds 200000 bytes")
            return {"path":path,"content":f[key].decode("utf-8-sig"),"size_bytes":len(f[key]),"sha256":digest(f[key])}

    def server_create_backup(self, paths: list[str], label: str, idempotency_key: str):
        """将登记备份范围内的服务配置或数据文件写入真实ZIP与清单。"""
        return self.create_backup(paths,label,idempotency_key)

    def server_list_backups(self, offset: int = 0, limit: int = 20):
        """分页列出当前服务器的本地备份记录。"""
        return self.list_backups(offset,limit)

    def server_verify_backup(self, backup_id: str):
        """验证ZIP整体及逐文件哈希、机器身份和恢复路径。"""
        return self.verify_backup(backup_id)

    def server_restore_backup(self, backup_id: str, idempotency_key: str, overwrite: bool = False):
        """从校验后的ZIP恢复原路径；覆盖需显式指定，配置恢复后仍须重新加载服务。"""
        return self.restore_backup(backup_id,idempotency_key,overwrite)

    def server_delete_backup(self, backup_id: str):
        """删除本地备份归档及登记，释放模拟磁盘空间。"""
        return self.delete_backup(backup_id)

    def validate(self,s,f):
        super().validate(s,f)
        configs,pids=set(),set()
        for key,v in s["services"].items():
            if key!=v["id"] or not re.fullmatch(r"[A-Za-z0-9_@.-]+\.service",key) or v["active_state"] not in ("active","inactive","failed"):
                raise ValueError("Invalid service identity/state")
            boolean(v["enabled"]); boolean(v["protected"]); boolean(v["supports_reload"])
            text(v["description"],500); text(v["command"]); text(v["process_name"],200); text(v["user"],100); integer(v["memory_bytes"])
            config=self.file_key(s,v["config_path"])
            if config not in f or config in configs or len(f[config])>200000 or v["config_format"] not in ("json","ini","env"):
                raise ValueError("Missing/duplicate/oversized configuration or invalid format")
            configs.add(config)
            seen=set()
            for rule in v["config_rules"]:
                if rule["key"] in seen or rule["type"] not in ("integer","boolean","text"):
                    raise ValueError("Duplicate/invalid configuration rule")
                seen.add(text(rule["key"],200))
                if rule["type"]=="integer":
                    low,high=rule.get("min",-10**15),rule.get("max",10**15)
                    integer(low,-10**15,10**15); integer(high,-10**15,10**15)
                    if low>high:
                        raise ValueError("Configuration rule minimum exceeds maximum")
            for dependency in v["requires"]:
                if dependency==key or dependency not in s["services"]:
                    raise ValueError("Invalid service dependency")
            if v["active_state"]=="active":
                p=self.get(s,"processes",str(v["main_pid"]))
                if v["main_pid"] in pids or p["status"]=="terminated" or p.get("service_id")!=key:
                    raise ValueError("Active service requires its distinct live main process")
                pids.add(v["main_pid"])
            elif v["main_pid"] is not None:
                raise ValueError("Inactive/failed service cannot retain a main PID")
        journal_key=self.file_key(s,s["journal_path"])
        if journal_key in configs or journal_key not in f:
            raise ValueError("Invalid journal path")
        for row in self.journal(s,f):
            moment(row["timestamp"]); integer(row["priority"],0,7); text(row["message"],10000)
            if row["service_id"] not in s["services"]:
                raise ValueError("Journal references an absent service")
