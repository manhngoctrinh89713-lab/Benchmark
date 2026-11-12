"""Local machine models. No operating-system process or service APIs are used."""
import copy
from contextlib import contextmanager
from datetime import datetime, timedelta
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import tempfile
from zipfile import ZipFile, ZIP_STORED

from filelock import FileLock
from .upstream_helpers import format_bytes

MAX_FILE = 8*1024*1024
MAX_TREE = 64*1024*1024
MAX_ENTRIES = 2000


def digest(data):
    return hashlib.sha256(data).hexdigest()


def integer(value, minimum=0, maximum=10**15):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"Expected integer in {minimum}..{maximum}")
    return value


def text(value, maximum=2000, empty=False):
    if not isinstance(value,str) or (not empty and not value.strip()) or len(value)>maximum or "\x00" in value:
        raise ValueError(f"Invalid text (maximum {maximum})")
    return value


def boolean(value):
    if type(value) is not bool:
        raise ValueError("Expected boolean")
    return value


def moment(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamp must include a timezone")
    return result


def page(items, offset=0, limit=20):
    integer(offset,0,100000); integer(limit,1,100)
    return {"items":copy.deepcopy(items[offset:offset+limit]), "total":len(items), "next_offset":offset+limit if offset+limit<len(items) else None}


def within(path, root):
    return path == root or path.startswith(root.rstrip("/")+"/")


class MaintenanceStore:
    platform = None
    prefix = None

    def __init__(self, run_root):
        self.root = Path(run_root).resolve()
        self.workspace = self.root / "workspace"
        self.service = self.root / "services" / self.prefix
        self.files = (self.workspace / "pc") if self.prefix == "pc" else (self.service / "files")
        if self.prefix=="server" and (self.service/"state.json").exists():
            mount=json.loads((self.service/"state.json").read_text(encoding="utf-8")).get("server_workspace_mount")
            if mount:self.files=self.workspace/mount

        self.state_path = self.service / "state.json"
        self.lock = FileLock(str(self.service / "state.lock"), timeout=20)
        self.files.mkdir(parents=True, exist_ok=True)
        (self.service / "backups").mkdir(parents=True, exist_ok=True)
        with self.lock:
            if not self.state_path.exists():
                raise ValueError(f"Missing services/{self.prefix}/state.json; copy the initial environment into the run root first")
            state = self.load_json(self.state_path)
            if state.get("platform") != self.platform:
                raise ValueError("State belongs to another platform")
            state.setdefault("sequence", 0)
            state.setdefault("backups", {})
            state.setdefault("next_backup", 0)
            state.setdefault("idempotency", {})
            state.setdefault("file_times", {})
            files = self.read_files()
            if "process_snapshot" in state or "next_pid" not in state:
                self.prepare(state, files)
            self.validate(state, files)
            self.atomic_json(self.state_path, state)

    def prepare(self,state,files):
        pass

    @staticmethod
    def check_entry(path):
        if path.is_symlink() or path.is_junction() or (path.is_file() and path.stat().st_nlink>1):
            raise ValueError("Links, junctions and hardlinks are not supported")

    @classmethod
    def load_json(cls,path):
        cls.check_entry(path)
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def atomic_bytes(path,raw):
        path.parent.mkdir(parents=True,exist_ok=True)
        fd,name = tempfile.mkstemp(dir=path.parent,suffix=".tmp")
        try:
            with os.fdopen(fd,"wb") as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            os.replace(name,path)
        finally:
            Path(name).unlink(missing_ok=True)

    @staticmethod
    def json_bytes(data):
        return (json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode()

    @classmethod
    def atomic_json(cls,path,data):
        cls.check_entry(path)
        cls.atomic_bytes(path,cls.json_bytes(data))

    @classmethod
    def read_tree(cls,root,prefix):
        cls.check_entry(root)
        result,stack = {},[root] if root.exists() else []
        count,total = 0,0
        while stack:
            parent = stack.pop()
            for path in sorted(parent.iterdir()):
                cls.check_entry(path); count += 1
                if count>MAX_ENTRIES:
                    raise ValueError("File tree exceeds 2000 entries")
                if path.is_dir():
                    stack.append(path)
                elif path.is_file():
                    if path.stat().st_size>MAX_FILE:
                        raise ValueError("File exceeds 8 MiB")
                    raw = path.read_bytes(); total += len(raw)
                    if total>MAX_TREE:
                        raise ValueError("File tree exceeds 64 MiB")
                    result[prefix+"/"+path.relative_to(root).as_posix()] = raw
                else:
                    raise ValueError("Only regular files and directories are supported")
        return result

    def read_files(self):
        files = self.read_tree(self.files,"files")
        files.update(self.read_tree(self.service/"backups","backups"))
        files.update(self.read_tree(self.service/"recycle","recycle"))
        if sum(map(len,files.values()))>MAX_TREE or len(files)>MAX_ENTRIES:
            raise ValueError("Combined run exceeds file limits")
        return files

    def local_path(self,relative):
        if not isinstance(relative,str) or not relative or "\\" in relative or ":" in relative:
            raise ValueError("Invalid internal file path")
        parts = relative.split("/")
        if parts[0] not in ("files","backups","recycle") or any(p in ("",".","..") or p.endswith((" ",".")) for p in parts):
            raise ValueError("File path must stay inside managed areas")
        root = self.files if parts[0]=="files" else self.service/parts[0]
        target = root
        self.check_entry(target)
        for part in parts[1:]:
            target = target/part; self.check_entry(target)
            if target != root.joinpath(*parts[1:]) and target.exists() and not target.is_dir():
                raise NotADirectoryError(str(target))
        return target

    def commit(self, state, files, before):
        if len(self.json_bytes(state)) > 5 * 1024 * 1024:
            raise ValueError("State exceeds 5 MiB")
        puts = {name: raw for name, raw in files.items() if before.get(name) != raw}
        deletes = sorted(before.keys() - files.keys())
        for name, raw in puts.items():
            self.atomic_bytes(self.local_path(name), raw)
        for name in deletes:
            self.local_path(name).unlink(missing_ok=True)
        self.atomic_json(self.state_path, state)

    @contextmanager
    def session(self):
        with self.lock:
            state = self.load_json(self.state_path)
            if state["platform"] != self.platform:
                raise ValueError("Run/platform mismatch")
            yield state,self.read_files()

    def mutate(self,action,arguments,handler,idempotency_key=None):
        with self.session() as (old,before):
            state,files = copy.deepcopy(old),dict(before)
            fingerprint = digest(json.dumps(arguments,sort_keys=True,ensure_ascii=False,allow_nan=False).encode())
            cache_key = None
            if idempotency_key is not None:
                if not isinstance(idempotency_key,str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}",idempotency_key):
                    raise ValueError("Invalid idempotency key")
                cache_key = action+"/"+idempotency_key
                if cache_key in state["idempotency"]:
                    prior = state["idempotency"][cache_key]
                    if prior["fingerprint"] != fingerprint:
                        raise ValueError("Idempotency key reused with different arguments")
                    return {**copy.deepcopy(prior["result"]),"replayed":True}
            result = handler(state,files)
            self.validate(state,files)
            state["sequence"] += 1
            state["now"] = (moment(state["now"])+timedelta(microseconds=1)).isoformat()
            for name in before.keys() | files.keys():
                if before.get(name)!=files.get(name) and name.startswith("files/"):
                    if name in files:
                        state["file_times"][name]=state["now"]
                    else:
                        state["file_times"].pop(name,None)
            result = {**copy.deepcopy(result),"sequence":state["sequence"],"replayed":False}
            if cache_key:
                state["idempotency"][cache_key] = {"fingerprint":fingerprint,"result":copy.deepcopy(result)}
            if "mutation_events" in state:
                import base64
                state["mutation_events"].append({"sequence":state["sequence"],"action":action,"puts":{k:base64.b64encode(v).decode() for k,v in files.items() if before.get(k)!=v},"deletes":[k for k in before if k not in files]})
            self.commit(state, files, before)
            return result

    def canonical(self,path):
        text(path,1000)
        value = path.replace("\\","/") if self.platform=="windows" else path
        if self.platform=="windows":
            if not re.match(r"^[A-Za-z]:/",value):
                raise ValueError("Windows path must be an absolute drive path")
            head,tail = value[0].upper()+":/",value[3:]
        else:
            if not value.startswith("/") or "\\" in value:
                raise ValueError("Linux path must be absolute and use /")
            head,tail = "/",value[1:]
        tail = tail.rstrip("/")
        parts = tail.split("/") if tail else []
        for part in parts:
            if not part or part in (".","..") or any(c in part for c in ':<>|?*\x00') or part.endswith((" ",".")):
                raise ValueError("Invalid path component")
            if re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?",part):
                raise ValueError("Reserved file name")
        return head+"/".join(p.casefold() if self.platform=="windows" else p for p in parts)

    def disk_for(self,state,path):
        choices = [d for d in state["disks"] if within(path,d["mount"])]
        if not choices:
            raise ValueError("Path is outside registered disks")
        return max(choices,key=lambda d:len(d["mount"]))

    def file_key(self,state,path):
        path = self.canonical(path); disk = self.disk_for(state,path)
        suffix = path[len(disk["mount"]):].lstrip("/")
        if not suffix:
            raise ValueError("A file cannot replace the disk root")
        return f'files/volumes/{disk["id"]}/'+suffix

    def virtual_path(self,state,name):
        parts = name.split("/",3)
        if len(parts)!=4 or parts[:2]!=["files","volumes"]:
            raise ValueError("Unexpected file tree layout")
        disk = next((d for d in state["disks"] if d["id"]==parts[2]),None)
        if disk is None:
            raise ValueError("Unregistered disk in files tree")
        path = self.canonical(disk["mount"].rstrip("/")+"/"+parts[3])
        if self.file_key(state,path)!=name:
            raise ValueError("File belongs to a different mounted disk or spelling")
        return path

    def ensure_scope(self,state,path,scope):
        path = self.canonical(path)
        if not any(within(path,root) for root in state[scope]):
            raise ValueError("Path is outside the registered operation scope")
        self.disk_for(state,path)
        return path

    def ensure_unlocked(self,state,path):
        if any(self.canonical(opened)==path for p in state["processes"].values() if p["status"]!="terminated" for opened in p.get("open_files",[])):
            raise ValueError("File is in use by a simulated process")

    def write_checked(self,state,files,key,raw,expected_sha256):
        path = self.virtual_path(state,key)
        if any(within(directory, path) for directory in state.get("directories", [])):
            raise IsADirectoryError(path)
        self.ensure_unlocked(state,path)
        if key in files:
            if expected_sha256 is None or digest(files[key])!=expected_sha256:
                raise ValueError("Existing file requires its current SHA-256")
        elif expected_sha256 is not None:
            raise ValueError("Expected existing file is absent")
        if self.local_path(key).is_dir() or any(k!=key and (k.startswith(key+"/") or key.startswith(k+"/")) for k in files):
            raise ValueError("File conflicts with a directory or parent file")
        files[key]=raw

    def disk_usage(self,state,files):
        rows = []
        for disk in state["disks"]:
            managed = sum(len(v) for k,v in files.items() if k.startswith(f'files/volumes/{disk["id"]}/'))
            archives = sum(len(v) for k,v in files.items() if k.startswith("backups/")) if disk["id"]==state["backup_disk_id"] else 0
            apps = sum(a["versions"][a["installed_version"]]["size_bytes"] for a in state.get("applications",{}).values() if a["installed_version"] and a["disk_id"]==disk["id"])
            recycled = sum(len(files.get(r["stored_path"], b"")) for r in state.get("recycle_bin", {}).values() if self.disk_for(state, r["original_path"])["id"] == disk["id"])
            used = disk["base_used_bytes"]+managed+archives+apps+recycled
            rows.append({**disk,"managed_bytes":managed,"backup_bytes":archives,"application_bytes":apps,"used_bytes":used,"free_bytes":disk["total_bytes"]-used,"used_percent":round(used/disk["total_bytes"]*100,2),"used_human":format_bytes(used)})
        return rows

    def system_info(self,state,files):
        active = [p for p in state["processes"].values() if p["status"]!="terminated"]
        memory = state["machine"]["base_memory_bytes"]+sum(p["memory_bytes"] for p in active)
        return {"machine":copy.deepcopy(state["machine"]),"platform":self.platform,"logical_time":state["now"],"memory_used_bytes":memory,"memory_available_bytes":state["machine"]["memory_total_bytes"]-memory,"cpu_percent_sum":round(sum(p["cpu_percent"] for p in active if p["status"]=="running"),2),"active_process_count":len(active),"disks":self.disk_usage(state,files)}

    @staticmethod
    def get(state,collection,key):
        if key not in state[collection]:
            raise ValueError("Unknown "+collection+" ID")
        return state[collection][key]

    def directory_rows(self,state,files,path):
        path = self.canonical(path); self.disk_for(state,path)
        rows = []
        for name,raw in files.items():
            if name.startswith("files/"):
                virtual = self.virtual_path(state,name)
                if within(virtual,path):
                    rows.append({"path":virtual,"size_bytes":len(raw),"sha256":digest(raw),"modified_at":state["file_times"].get(name,state["now"])})
        return sorted(rows,key=lambda r:r["path"])

    def analyze_directory(self,path,limit=20):
        integer(limit,1,100)
        with self.session() as (s,f):
            rows = self.directory_rows(s,f,path)
            return {"path":self.canonical(path),"file_count":len(rows),"total_bytes":sum(r["size_bytes"] for r in rows),"largest_files":sorted(rows,key=lambda r:(-r["size_bytes"],r["path"]))[:limit]}

    def backup_scope(self):
        return "personal_roots" if self.platform=="windows" else "backup_roots"

    def create_backup(self,paths,label,idempotency_key):
        def apply(s,f):
            text(label,200)
            if not isinstance(paths,list) or not 1<=len(paths)<=20:
                raise ValueError("Backup requires 1..20 paths")
            normalized = [self.ensure_scope(s,p,self.backup_scope()) for p in paths]
            selected = {}
            for path in normalized:
                rows = self.directory_rows(s,f,path)
                if not rows:
                    raise FileNotFoundError(path)
                for row in rows:
                    selected[row["path"]] = self.file_key(s,row["path"])
            if len(selected)>200:
                raise ValueError("Backup exceeds 200 files")
            entries = []
            stream = io.BytesIO()
            with ZipFile(stream,"w",compression=ZIP_STORED) as archive:
                for i,(path,key) in enumerate(sorted(selected.items())):
                    raw = f[key]; member = f"payload/{i:04d}.bin"
                    entries.append({"path":path,"member":member,"size":len(raw),"sha256":digest(raw)})
                    archive.writestr(member,raw)
                manifest = {"format_version":1,"platform":self.platform,"machine_id":s["machine"]["id"],"created_at":s["now"],"files":entries}
                archive.writestr("manifest.json",self.json_bytes(manifest))
            raw = stream.getvalue()
            if len(raw)>MAX_FILE:
                raise ValueError("Backup exceeds 8 MiB")
            s["next_backup"] += 1; backup_id = f'bak_{s["next_backup"]:06d}'
            archive_path = f"backups/{backup_id}.zip"; f[archive_path]=raw
            info = {"id":backup_id,"label":label,"archive_path":archive_path,"size_bytes":len(raw),"sha256":digest(raw),"file_count":len(entries),"created_at":s["now"]}
            s["backups"][backup_id]=info
            return {"backup":info}
        return self.mutate(self.prefix+"_create_backup",{"paths":paths,"label":label},apply,idempotency_key)

    def open_backup(self,state,files,backup_id):
        info = self.get(state,"backups",backup_id)
        raw = files.get(info["archive_path"])
        if raw is None or len(raw)!=info["size_bytes"] or digest(raw)!=info["sha256"]:
            raise ValueError("Backup is missing or its archive hash has changed")
        restored = {}
        with ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries)>201 or len({e.filename for e in entries})!=len(entries) or sum(e.file_size for e in entries)>MAX_FILE:
                raise ValueError("Invalid backup members or size")
            manifest = json.loads(archive.read("manifest.json"))
            if manifest["format_version"]!=1 or manifest["platform"]!=self.platform or manifest["machine_id"]!=state["machine"]["id"] or len(manifest["files"])!=info["file_count"]:
                raise ValueError("Backup manifest does not match machine/platform")
            expected = {"manifest.json"}
            for index,item in enumerate(manifest["files"]):
                if item["member"]!=f"payload/{index:04d}.bin":
                    raise ValueError("Unexpected backup member name")
                path = self.ensure_scope(state,item["path"],self.backup_scope()); key = self.file_key(state,path)
                if key in restored:
                    raise ValueError("Duplicate backup target")
                content = archive.read(item["member"])
                if len(content)!=item["size"] or digest(content)!=item["sha256"]:
                    raise ValueError("Backup payload hash mismatch")
                expected.add(item["member"]); restored[key]=content
            if expected!={e.filename for e in entries}:
                raise ValueError("Unexpected archive entries")
        return info,restored

    def list_backups(self,offset=0,limit=20):
        with self.session() as (s,f):
            return page(list(s["backups"].values()),offset,limit)

    def verify_backup(self,backup_id):
        with self.session() as (s,f):
            info,restored = self.open_backup(s,f,backup_id)
            return {"verified":True,"backup":info,"files":[{"path":self.virtual_path(s,k),"size_bytes":len(v),"sha256":digest(v)} for k,v in restored.items()]}

    def restore_backup(self,backup_id,idempotency_key,overwrite=False):
        boolean(overwrite)
        def apply(s,f):
            info,restored = self.open_backup(s,f,backup_id)
            if not overwrite and any(k in f for k in restored):
                raise FileExistsError("Restore would overwrite an existing file")
            for key,raw in restored.items():
                self.write_checked(s,f,key,raw,digest(f[key]) if key in f else None)
            return {"backup_id":backup_id,"restored_paths":[self.virtual_path(s,k) for k in restored]}
        return self.mutate(self.prefix+"_restore_backup",{"backup_id":backup_id,"overwrite":overwrite},apply,idempotency_key)

    def delete_backup(self,backup_id):
        def apply(s,f):
            info = self.get(s,"backups",backup_id); f.pop(info["archive_path"],None); del s["backups"][backup_id]
            return {"deleted_backup":info}
        return self.mutate(self.prefix+"_delete_backup",{"backup_id":backup_id},apply)

    def validate(self,state,files):
        if state["platform"]!=self.platform:
            raise ValueError("Wrong platform")
        moment(state["now"])
        for directory in state.get("directories", []):
            if self.canonical(directory) != directory:
                raise ValueError("Invalid directory path")
            key = self.file_key(state, directory)
            if key in files or any(key.startswith(k+"/") for k in files if k.startswith("files/")):
                raise ValueError("Directory conflicts with a file")
        for rid, item in state.get("recycle_bin", {}).items():
            if item["id"] != rid or item["stored_path"] != "recycle/"+rid or item["stored_path"] not in files or digest(files[item["stored_path"]]) != item["sha256"]:
                raise ValueError("Invalid recycle item")
            self.ensure_scope(state, item["original_path"], "personal_roots")
        machine = state["machine"]
        text(machine["id"],100); integer(machine["cpu_count"],1,1024)
        integer(machine["memory_total_bytes"],1); integer(machine["base_memory_bytes"])
        ids,mounts = set(),set()
        for d in state["disks"]:
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}",d["id"]) or d["id"] in ids or d["mount"] in mounts or self.canonical(d["mount"])!=d["mount"]:
                raise ValueError("Invalid or duplicate disk")
            ids.add(d["id"]); mounts.add(d["mount"])
            integer(d["total_bytes"],1); integer(d["base_used_bytes"])
        if not ids or state["backup_disk_id"] not in ids:
            raise ValueError("Missing backup disk")
        if sum(map(len,files.values()))>MAX_TREE or len(files)>MAX_ENTRIES:
            raise ValueError("Run exceeds 64 MiB/2000 files")
        for name,raw in files.items():
            self.local_path(name)
            if len(raw)>MAX_FILE:
                raise ValueError("File exceeds 8 MiB")
            if name.startswith("files/"):
                self.virtual_path(state,name)
        for scope in (self.backup_scope(),):
            roots = state[scope]
            if not isinstance(roots,list) or not roots:
                raise ValueError("Operation scope cannot be empty")
            for path in roots:
                if self.canonical(path)!=path:
                    raise ValueError("Scope paths must use canonical spelling")
                self.disk_for(state,path)
        processes = state["processes"]
        if len(processes)>1000:
            raise ValueError("Too many processes")
        for key,p in processes.items():
            integer(p["pid"],1,2**31-1)
            if key!=str(p["pid"]) or p["status"] not in ("running","suspended","terminated"):
                raise ValueError("Invalid process identity/status")
            text(p["name"],200); text(p["user"],100); moment(p["started_at"])
            integer(p["memory_bytes"])
            if type(p["cpu_percent"]) not in (int,float) or not math.isfinite(p["cpu_percent"]) or not 0<=p["cpu_percent"]<=machine["cpu_count"]*100:
                raise ValueError("Invalid CPU sample")
            boolean(p["protected"])
            for path in p.get("open_files",[]):
                self.disk_for(state,self.canonical(path))
        for row in self.disk_usage(state,files):
            if row["free_bytes"]<0:
                raise ValueError("Insufficient simulated disk space")
        if self.system_info(state,files)["memory_available_bytes"]<0:
            raise ValueError("Insufficient simulated memory")
        for name,stamp in state["file_times"].items():
            if name not in files:
                # Deleted entries are removed after the successful handler validation.
                continue
            moment(stamp)
        for key,info in state["backups"].items():
            if key!=info["id"] or info["archive_path"]!=f"backups/{key}.zip" or not re.fullmatch(r"bak_[0-9]{6,}",key):
                raise ValueError("Invalid backup metadata")
