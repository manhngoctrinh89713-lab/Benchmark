import asyncio
import json
import os
import shutil
import sys
import unittest
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from filelock import FileLock

from harness.catalog import ROOT, SRC_ROOT, SUITES
from harness.environment import initial_case, manifest, model_lock, reset_environment, save_environment
from harness.transport import write_json
from harness.sandbox import tool_scope, validate_tree


def with_mcp(method):
    def wrapped(self):
        async def run():
            params = StdioServerParameters(command=sys.executable,
                args=["-B", "-m", "harness.worker", "--run-root", str(self.root), "--groups", *SUITES],
                cwd=str(ROOT), env={"PYTHONPATH": str(SRC_ROOT), "PYTHONIOENCODING": "utf-8"})
            async with stdio_client(params) as streams:
                async with ClientSession(*streams) as session:
                    self.session = session
                    await session.initialize()
                    await method(self)
        asyncio.run(run())
    return wrapped


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.lock = model_lock()
        self.lock.acquire()
        self.addCleanup(self.lock.release)
        self.initial = initial_case("综合测试")
        self.before = manifest(self.initial)
        self.record = ROOT / "运行记录" / ("test-" + uuid4().hex)
        self.record.mkdir(parents=True)
        write_json(self.record / "initial_manifest.json", self.before)
        self.root = reset_environment(self.initial)
        self.events = 0

    def tearDown(self):
        save_environment(self.root, self.record)
        write_json(self.record / "run.json", {"kind": "integration_test", "test": self.id(),
            "run_root": str(self.root), "finished_at": datetime.now().astimezone().isoformat()})
        self.assertEqual(self.before, manifest(self.initial))

    async def call(self, name, args=None):
        result = await self.session.call_tool(name, args or {}, read_timeout_seconds=timedelta(seconds=20))
        self.events += 1
        write_json(self.record / f"tool-{self.events:03d}.json", {
            "name": name, "arguments": args or {}, "result": result.model_dump(mode="json")})
        self.assertFalse(result.isError, str(result.content))
        return result

    @with_mcp
    async def test_all_groups_on_one_environment(self):
        tools = (await self.session.list_tools()).tools
        self.assertEqual(len(tools), 442)
        self.assertEqual(len({t.name for t in tools}), 442)
        for name in ["mail__list_accounts", "chat__list_chats", "files__list_allowed_directories",
                     "database__list_databases", "code__list_projects", "git__list_repositories",
                     "github__get_me", "pc__pc_get_system_info", "server__server_get_system_info",
                     "merchant__get_merchant_profile", "buyer__get_buyer_profile"]:
            with self.subTest(name=name):
                await self.call(name)
        await self.call("git__git_status", {"repo_id": "demo"})
        await self.call("code__get_symbols_overview", {"project_id": "python_demo", "path": "calc.py"})

    @with_mcp
    async def test_cross_group_shared_files(self):
        await self.call("files__write_file", {"path": "output/check.txt", "content": "shared bytes"})
        await self.call("chat__send_file", {"chat_id": "c_project", "file_path": "output/check.txt"})
        self.assertEqual((self.root / "workspace/output/check.txt").read_text(), "shared bytes")

    @with_mcp
    async def test_documents(self):
        for suffix in (".xlsx", ".docx", ".pdf", ".pptx"):
            files = list((self.root / "workspace").rglob("*" + suffix))
            for path in files:
                with self.subTest(path=path.name):
                    await self.call("files__read_document", {"path": str(path.relative_to(self.root / "workspace"))})

    @with_mcp
    async def test_boundaries_and_invalid_arguments(self):
        for name, args in [
            ("files__read_document", {"path": str(ROOT / "README.md")}),
            ("files__write_file", {"path": "../../escape.txt", "content": "bad"}),
            ("chat__send_file", {"chat_id": "c_project", "file_path": str(ROOT / "README.md")}),
            ("files__write_file", {"path": "repos/demo/.git/config", "content": "bad", "overwrite": True}),
            ("chat__list_chats", {"limit": "bad"}),
            ("missing__tool", {}),
        ]:
            with self.subTest(name=name, args=args):
                self.assertTrue((await self.session.call_tool(name, args, read_timeout_seconds=timedelta(seconds=20))).isError)


class BoundaryTests(unittest.TestCase):
    def test_reset_replaces_state_and_preserves_recorded_environment(self):
        source = initial_case("综合测试")
        before = manifest(source)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            record = base / "record"
            record.mkdir()
            with patch("harness.environment.ROOT", base):
                root = reset_environment(source)
                old_file = root / "workspace/previous-result.txt"
                old_file.write_text("previous final state", encoding="utf-8")
                (root / "services/chat/state.json").write_text("changed", encoding="utf-8")
                save_environment(root, record)
                self.assertEqual(reset_environment(source), root)
                self.assertFalse(old_file.exists())
                self.assertEqual(manifest(root), before)
                self.assertEqual((record / "final_environment/workspace/previous-result.txt").read_text(),
                                 "previous final state")
                self.assertEqual((record / "final_environment/services/chat/state.json").read_text(), "changed")
        self.assertEqual(manifest(source), before)

    def test_case_directory_cannot_escape(self):
        for name in ("..", "../快照", str(ROOT)):
            with self.assertRaises(ValueError):
                initial_case(name)

    def test_dispatch_guard_rejects_host_io(self):
        root = initial_case("综合测试")
        with tool_scope(root):
            with self.assertRaises(PermissionError):
                (ROOT / "README.md").read_text()
            with self.assertRaises(PermissionError):
                (ROOT / "escape.txt").write_text("bad")
            with self.assertRaises(PermissionError):
                os.listdir(ROOT)
            self.assertTrue((root / "services/chat/state.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
