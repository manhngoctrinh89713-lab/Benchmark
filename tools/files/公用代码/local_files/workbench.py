"""Binary files, archives and recoverable deletion."""
import base64
import difflib
import io
import json
from pathlib import PurePosixPath
import zipfile


from .spreadsheet import SpreadsheetWorkbench


class FileWorkbench(SpreadsheetWorkbench):
    def read_binary_file(self, path: str, offset: int = 0, length: int = 65536) -> dict:
        """分段读取文件二进制内容，以 Base64 返回，并提供完整文件校验值。"""
        from .backend import digest
        if type(offset) is not int or offset < 0 or not 1 <= length <= 1048576:
            raise ValueError("offset >= 0; length 1..1048576")
        with self.session():
            p = self.path(path, False)
            raw = self.read_bytes(p)
            chunk = raw[offset:offset+length]
            return {"path": self.rel(p), "content_base64": self.encode(chunk), "size": len(raw), "sha256": digest(raw), "next_offset": offset+len(chunk) if offset+len(chunk) < len(raw) else None}

    def write_binary_file(self, path: str, content_base64: str, overwrite: bool = False, expected_sha256: str | None = None) -> dict:
        """将 Base64 内容写入文件，支持按已有文件校验值覆盖。"""
        from .backend import MAX_FILE
        if len(content_base64) > (MAX_FILE+2)//3*4:
            raise ValueError("File exceeds 25 MiB")
        raw = base64.b64decode(content_base64, validate=True)
        with self.session() as s:
            return self._write(s, self.path(path, False), raw, overwrite, "write_binary_file", expected_sha256)

    def append_file(self, path: str, content: str, expected_sha256: str) -> dict:
        """在现有 UTF-8 文件末尾追加文本，并核对修改前的校验值。"""
        with self.session() as s:
            p = self.path(path, False)
            raw = self.read_bytes(p)
            raw.decode("utf-8-sig")
            return self._write(s, p, raw+content.encode(), True, "append_file", expected_sha256)

    def compare_files(self, source: str, destination: str, include_diff: bool = False) -> dict:
        """比较两份文件的字节内容，可返回 UTF-8 文本差异。"""
        from .backend import digest
        with self.session():
            a, b = self.read_bytes(self.path(source, False)), self.read_bytes(self.path(destination, False))
            result = {"equal": a == b, "source_sha256": digest(a), "destination_sha256": digest(b), "source_size": len(a), "destination_size": len(b)}
            if include_diff:
                diff = "".join(difflib.unified_diff(a.decode("utf-8-sig").splitlines(True), b.decode("utf-8-sig").splitlines(True), fromfile=source, tofile=destination))
                if len(diff) > 200000:
                    raise ValueError("Diff exceeds 200000 characters")
                result["diff"] = diff
            return result

    def create_archive(self, paths: list[str], save_path: str) -> dict:
        """将选定文件或目录打包为 ZIP，归档内保留工作区相对路径。"""
        from .backend import MAX_TRANSACTION
        if not 1 <= len(paths) <= 100:
            raise ValueError("Choose 1..100 paths")
        with self.session() as s:
            target = self.path(save_path, False)
            entries = {}
            for value in paths:
                source = self.path(value, False)
                if target == source or target.is_relative_to(source):
                    raise ValueError("Archive destination cannot be among source paths")
                for entry in self.manifest(source):
                    entries[entry["path"]] = entry
            if sum(len(base64.b64decode(v.get("content_base64", ""))) for v in entries.values()) > MAX_TRANSACTION:
                raise ValueError("Archive input exceeds 100 MiB")
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, entry in sorted(entries.items()):
                    archive.writestr(name+"/" if entry["type"] == "directory" else name, b"" if entry["type"] == "directory" else base64.b64decode(entry["content_base64"]))
            return self._write(s, target, stream.getvalue(), False, "create_archive")

    def list_archive(self, path: str, offset: int = 0, limit: int = 100) -> dict:
        """列出 ZIP 归档中的文件、目录和解压大小。"""
        from .backend import page, MAX_ENTRIES
        with self.session():
            with zipfile.ZipFile(io.BytesIO(self.read_bytes(self.path(path, False)))) as archive:
                rows = [{"path": i.filename, "size": i.file_size, "compressed_size": i.compress_size, "directory": i.is_dir()} for i in archive.infolist()]
                if len(rows) > MAX_ENTRIES:
                    raise ValueError("Archive has too many entries")
                return page(rows, offset, limit)

    def extract_archive(self, path: str, destination: str, overwrite: bool = False) -> dict:
        """将 ZIP 解压到指定目录；预先检查全部目标、重复项和大小后统一提交。"""
        from .backend import MAX_FILE, MAX_ENTRIES, MAX_TRANSACTION
        with self.session() as s:
            target = self.path(destination, False)
            plan = self.empty_plan()
            if target.exists() and not target.is_dir():
                raise NotADirectoryError(destination)
            plan["mkdirs"].append(self.rel(target))
            with zipfile.ZipFile(io.BytesIO(self.read_bytes(self.path(path, False)))) as archive:
                entries = archive.infolist()
                if len(entries) > MAX_ENTRIES or sum(i.file_size for i in entries) > MAX_TRANSACTION:
                    raise ValueError("Archive exceeds extraction limits")
                seen = set()
                for entry in entries:
                    name = PurePosixPath(entry.filename)
                    if name.is_absolute() or ".." in name.parts or "\\" in entry.filename or ":" in entry.filename or not name.parts or entry.file_size > MAX_FILE or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValueError("Invalid archive member")
                    dest = self.path(str(target.joinpath(*name.parts)), False)
                    key = str(dest).casefold()
                    if key in seen:
                        raise ValueError("Duplicate archive destination")
                    seen.add(key)
                    if entry.is_dir():
                        if dest.exists() and not dest.is_dir():
                            raise FileExistsError(str(dest))
                        plan["mkdirs"].append(self.rel(dest))
                    else:
                        if dest.exists() and (not overwrite or not dest.is_file()):
                            raise FileExistsError(str(dest))
                        plan["puts"][self.rel(dest)] = self.encode(archive.read(entry))
            # Files may not also be parents of other files/directories.
            all_names = set(plan["puts"]) | set(plan["mkdirs"])
            if any(other.startswith(name+"/") for name in plan["puts"] for other in all_names):
                raise ValueError("Archive contains conflicting paths")
            return {**self.mutate(s, "extract_archive", plan), "extracted_entries": len(entries), "destination": self.rel(target)}

    def trash_file(self, path: str) -> dict:
        """将文件或目录移入服务回收站，保存原始路径以便恢复。"""
        from .backend import digest
        with self.session() as s:
            p = self.path(path, False)
            if not p.exists():
                raise FileNotFoundError(path)
            manifest = self.manifest(p)
            tid = "trash_"+str(s["sequence"]+1)
            record = {"id": tid, "original_path": self.rel(p), "deleted_at": s["now"], "entries": manifest}
            archive = self.service/"trash"/(tid+".json")
            archive.parent.mkdir(exist_ok=True)
            # Save recovery bytes before deleting the originals.
            self.atomic_json(archive, record)
            plan = self.empty_plan()
            for e in manifest:
                plan["rmdirs" if e["type"] == "directory" else "deletes"].append(e["path"])
            return {**self.mutate(s, "trash_file", plan), "trash_id": tid, "original_path": record["original_path"]}

    def list_trash(self, offset: int = 0, limit: int = 20) -> dict:
        """列出可恢复的回收站项目。"""
        from .backend import page
        with self.session():
            return page([{k: v for k, v in self.load_json(p).items() if k != "entries"} for p in sorted((self.service/"trash").glob("*.json"))], offset, limit)

    def restore_trash(self, trash_id: str, destination: str | None = None) -> dict:
        """恢复回收站项目到原路径或新路径，已有文件不覆盖。"""
        import re
        if not re.fullmatch(r"trash_[0-9]+", trash_id):
            raise ValueError("Invalid trash ID")
        with self.session() as s:
            record_path = self.service/"trash"/(trash_id+".json")
            record = self.load_json(record_path)
            source = PurePosixPath(record["original_path"])
            target = self.path(destination or str(source), False)
            if target.exists():
                raise FileExistsError(str(target))
            plan = self.empty_plan()
            for entry in record["entries"]:
                dest = self.path(str(target.joinpath(*PurePosixPath(entry["path"]).relative_to(source).parts)), False)
                if entry["type"] == "directory":
                    plan["mkdirs"].append(self.rel(dest))
                else:
                    plan["puts"][self.rel(dest)] = entry["content_base64"]
            result = self.mutate(s, "restore_trash", plan)
            record_path.unlink()
            return {**result, "restored_path": self.rel(target), "trash_id": trash_id}

    def delete_trash(self, trash_id: str) -> dict:
        """永久删除一个回收站项目。"""
        import re
        if not re.fullmatch(r"trash_[0-9]+", trash_id):
            raise ValueError("Invalid trash ID")
        with self.session() as s:
            p = self.service/"trash"/(trash_id+".json")
            record = self.load_json(p)
            result = self.mutate(s, "delete_trash", self.empty_plan())
            p.unlink()
            return {**result, "deleted_trash_id": trash_id}
