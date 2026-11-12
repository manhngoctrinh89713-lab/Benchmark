"""Project inspection and explicit file lifecycle operations."""
import difflib
from pathlib import Path


class CodeWorkbench:
    def get_project_info(self, project_id: str) -> dict:
        """读取项目文件数量、语言分布和配置文件位置。"""
        with self.session():
            root = self.project(project_id)
            files = self.code_files(project_id)
            languages = {}
            config_names = {"pyproject.toml", "package.json", "Cargo.toml", "go.mod", "pom.xml", "Makefile", "CMakeLists.txt", "tsconfig.json"}
            for p in files:
                extension = p.suffix or "(none)"
                languages[extension] = languages.get(extension, 0)+1
            return {"project_id": project_id, "path": self.rel(root), "file_count": len(files), "extensions": languages, "configuration_files": [p.relative_to(root).as_posix() for p in files if p.name in config_names]}

    def diagnose_project(self, project_id: str, pattern: str = "*", offset: int = 0, limit: int = 20) -> dict:
        """对匹配文件分页进行静态语法诊断，不运行项目代码。"""
        import fnmatch
        from . import analysis
        from .state_core import digest, page
        with self.session():
            root = self.project(project_id)
            files = [p for p in self.code_files(project_id) if p.suffix in analysis.EXTENSIONS and fnmatch.fnmatchcase(p.relative_to(root).as_posix(), pattern)]
            selected = page(files, offset, limit)
            rows = []
            for p in selected["items"]:
                raw, content = self.text(p)
                rows.append({"path": p.relative_to(root).as_posix(), "sha256": digest(raw), **analysis.diagnostics(p, content)})
            return {**selected, "items": rows}

    def move_code_file(self, project_id: str, source: str, destination: str, expected_sha256: str, dry_run: bool = False) -> dict:
        """在项目内移动代码文件，保留文本内容；返回删除与新增的统一预览。"""
        with self.session() as s:
            src = self.code_path(project_id, source)
            dest = self.code_path(project_id, destination)
            if src == dest or dest.exists():
                raise FileExistsError(destination)
            raw, content = self.text(src)
            return self._apply(s, project_id, [{"path": source, "content": None, "expected_sha256": expected_sha256}, {"path": destination, "content": content}], "move_code_file", dry_run)

    def delete_code_file(self, project_id: str, path: str, expected_sha256: str, dry_run: bool = False) -> dict:
        """按当前校验值删除代码文件，可先预览差异。"""
        with self.session() as s:
            return self._apply(s, project_id, [{"path": path, "content": None, "expected_sha256": expected_sha256}], "delete_code_file", dry_run)

    def compare_code_files(self, project_id: str, source: str, destination: str) -> dict:
        """比较项目中两份代码的文本及校验值。"""
        from .state_core import digest, MAX_TEXT
        with self.session():
            a, before = self.text(self.code_path(project_id, source))
            b, after = self.text(self.code_path(project_id, destination))
            delta = "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile=source, tofile=destination))
            if len(delta) > MAX_TEXT:
                raise ValueError("Diff too large")
            return {"equal": a == b, "source_sha256": digest(a), "destination_sha256": digest(b), "diff": delta}

    def search_project_files(self, project_id: str, pattern: str, extension: str | None = None, offset: int = 0, limit: int = 50) -> dict:
        """按相对路径通配符和扩展名查询项目文件。"""
        import fnmatch
        from .state_core import page
        with self.session():
            root = self.project(project_id)
            return page([{"path": p.relative_to(root).as_posix(), "size": p.stat().st_size} for p in self.code_files(project_id) if fnmatch.fnmatchcase(p.relative_to(root).as_posix(), pattern) and (extension is None or p.suffix == extension)], offset, limit)
