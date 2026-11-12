"""Exercise history operations in isolated copies; never reset the shared run."""
import asyncio
import json
import shutil
import tempfile
import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import sys

from harness.catalog import ROOT, SRC_ROOT, TOOLS_ROOT, load_servers
from harness.sandbox import tool_scope


class GitHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="benchmark-git-history-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "run"
        shutil.copytree(ROOT / "初始环境/综合测试", self.root)
        self.server = load_servers(self.root, ["git"])["git"]
        from local_git.backend import GitStore
        self.store = GitStore(self.root)
        self.repo = self.root / "workspace/repos/demo"
        self.base = self.store.ref(self.repo, "HEAD")

    def commit(self, path, content, message="change"):
        self.store.write_repository_file("demo", path, content, overwrite=True)
        self.store.git_add("demo", [path])
        return self.store.git_commit("demo", message)["sha"]

    def divergence(self):
        base = self.commit("shared.txt", "base\n")
        self.store.git_create_branch("demo", "topic", base)
        self.store.git_checkout("demo", "topic")
        topic = self.commit("shared.txt", "topic\n")
        self.store.git_checkout("demo", "main")
        main = self.commit("shared.txt", "main\n")
        return topic, main

    def test_merge_fast_forward_and_merge_commit(self):
        self.store.git_create_branch("demo", "topic")
        self.store.git_checkout("demo", "topic")
        target = self.commit("topic.txt", "topic\n")
        self.store.git_checkout("demo", "main")
        with tool_scope(self.root):
            result = self.store.git_merge("demo", source="topic", ff_mode="ff-only")
        self.assertEqual(result["head"], target)
        self.store.git_create_branch("demo", "more")
        self.store.git_checkout("demo", "more")
        self.commit("more.txt", "more\n")
        self.store.git_checkout("demo", "main")
        self.commit("main.txt", "main\n")
        with tool_scope(self.root):
            with self.assertRaises(ValueError):
                self.store.git_merge("demo", source="more", ff_mode="ff-only")
            result = self.store.git_merge("demo", source="more", ff_mode="no-ff", message="merge more")
        self.assertEqual(result["status"], "completed")
        parents = self.store.run(self.repo, "rev-list", "--parents", "-n", "1", "HEAD").split()
        self.assertEqual(len(parents), 3)
        self.assertTrue((self.repo / "main.txt").exists())
        self.assertTrue((self.repo / "more.txt").exists())

    def test_merge_conflict_continue(self):
        self.divergence()
        with tool_scope(self.root):
            result = self.store.git_merge("demo", source="topic")
            self.assertEqual(result["status"], "conflicts")
            self.assertEqual(result["conflicts"], ["shared.txt"])
            self.assertEqual(self.store.git_operation_status("demo")["operation"], "merge")
            with self.assertRaises(ValueError):
                self.store.git_merge("demo", operation="continue")
            self.commit_resolution()
            result = self.store.git_merge("demo", operation="continue")
        self.assertEqual(result["status"], "completed")
        self.assertIsNone(result["operation"])
        self.assertEqual((self.repo / "shared.txt").read_text(), "main and topic\n")

    def commit_resolution(self):
        self.store.write_repository_file("demo", "shared.txt", "main and topic\n", overwrite=True)
        self.store.git_add("demo", ["shared.txt"])

    def test_merge_abort_restores_original(self):
        _, main = self.divergence()
        with tool_scope(self.root):
            self.store.git_merge("demo", source="topic")
            result = self.store.git_merge("demo", operation="abort")
        self.assertEqual(result["status"], "aborted")
        self.assertEqual(result["head"], main)
        self.assertEqual((self.repo / "shared.txt").read_text(), "main\n")

    def test_rebase_conflict_continue(self):
        topic, old = self.divergence()
        with tool_scope(self.root):
            result = self.store.git_rebase("demo", upstream="topic")
            self.assertEqual(result["status"], "conflicts")
            with self.assertRaises(ValueError):
                self.store.git_rebase("demo", operation="continue")
            self.commit_resolution()
            result = self.store.git_rebase("demo", operation="continue")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["branch"], "main")
        self.assertNotEqual(result["head"], old)
        self.store.run(self.repo, "merge-base", "--is-ancestor", topic, result["head"])
        self.assertEqual((self.repo / "shared.txt").read_text(), "main and topic\n")

    def test_rebase_abort_and_skip(self):
        topic, old = self.divergence()
        with tool_scope(self.root):
            self.store.git_rebase("demo", upstream="topic")
            result = self.store.git_rebase("demo", operation="abort")
            self.assertEqual(result["head"], old)
            self.assertEqual(result["branch"], "main")
            self.assertEqual((self.repo / "shared.txt").read_text(), "main\n")
            self.store.git_rebase("demo", upstream="topic")
            result = self.store.git_rebase("demo", operation="skip")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["head"], topic)
        self.assertEqual((self.repo / "shared.txt").read_text(), "topic\n")

    def test_failed_abort_does_not_report_aborted(self):
        self.divergence()
        for operation, method, arguments in [
            ("merge", self.store.git_merge, {"source": "topic"}),
            ("rebase", self.store.git_rebase, {"upstream": "topic"}),
        ]:
            with self.subTest(operation=operation), tool_scope(self.root):
                method("demo", **arguments)
                original = self.store.run_result

                def reject_abort(root, *args, **kwargs):
                    if args == (operation, "--abort"):
                        return subprocess.CompletedProcess(["git", *args], 1, b"", b"abort failed")
                    return original(root, *args, **kwargs)

                with patch.object(self.store, "run_result", side_effect=reject_abort):
                    result = method("demo", operation="abort")
                self.assertNotEqual(result["status"], "aborted")
                self.assertEqual(result["operation"], operation)
                self.assertEqual(result["returncode"], 1)
                self.assertEqual(method("demo", operation="abort")["status"], "aborted")

    def test_rebase_onto(self):
        first = self.commit("one.txt", "one\n")
        self.commit("two.txt", "two\n")
        self.store.git_create_branch("demo", "new-base", self.base)
        self.store.git_checkout("demo", "new-base")
        onto = self.commit("base.txt", "base\n")
        self.store.git_checkout("demo", "main")
        with tool_scope(self.root):
            result = self.store.git_rebase("demo", upstream=first, onto=onto)
        self.assertEqual(result["status"], "completed")
        self.assertFalse((self.repo / "one.txt").exists())
        self.assertTrue((self.repo / "two.txt").exists())
        self.assertTrue((self.repo / "base.txt").exists())

    def test_rebase_can_preserve_merge_topology(self):
        self.commit("main-one.txt", "one\n")
        self.store.git_create_branch("demo", "side")
        self.store.git_checkout("demo", "side")
        self.commit("side.txt", "side\n")
        self.store.git_checkout("demo", "main")
        self.commit("main-two.txt", "two\n")
        self.store.git_merge("demo", source="side", ff_mode="no-ff")
        self.store.git_create_branch("demo", "upstream", self.base)
        self.store.git_checkout("demo", "upstream")
        upstream = self.commit("upstream.txt", "upstream\n")
        self.store.git_checkout("demo", "main")
        with tool_scope(self.root):
            result = self.store.git_rebase("demo", upstream=self.base, onto=upstream, rebase_merges=True)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(self.store.run(self.repo, "rev-list", "--parents", "-n", "1", "HEAD").split()), 3)
        self.store.run(self.repo, "merge-base", "--is-ancestor", upstream, "HEAD")
        for name in ("main-one.txt", "side.txt", "main-two.txt", "upstream.txt"):
            self.assertTrue((self.repo / name).exists())

    def test_squash_preserves_deletions_binary_and_file_modes(self):
        self.commit("delete-me.txt", "old\n")
        base = self.store.ref(self.repo, "HEAD")
        self.commit("keep.txt", "keep\n")
        (self.repo / "delete-me.txt").unlink()
        binary = b"\x00\xff\x01\x80payload"
        (self.repo / "image.bin").write_bytes(binary)
        self.store.git_add("demo", ["."])
        self.store.run(self.repo, "update-index", "--chmod=+x", "keep.txt")
        self.store.git_commit("demo", "delete and binary")
        tree = self.store.run(self.repo, "rev-parse", "HEAD^{tree}").strip()
        with tool_scope(self.root):
            result = self.store.git_squash("demo", base, "one combined commit")
        self.assertEqual(result["squashed_commits"], 2)
        self.assertEqual(self.store.run(self.repo, "rev-parse", "HEAD^{tree}").strip(), tree)
        self.assertEqual(self.store.run(self.repo, "rev-parse", "HEAD^").strip(), base)
        self.assertFalse((self.repo / "delete-me.txt").exists())
        self.assertEqual((self.repo / "image.bin").read_bytes(), binary)
        self.assertEqual(self.store.run(self.repo, "status", "--porcelain"), "")

    def test_reject_invalid_revisions_dirty_tree_and_wrong_lifecycle(self):
        with tool_scope(self.root):
            for function, kwargs in [(self.store.git_merge, {"source": "--help"}),
                    (self.store.git_rebase, {"upstream": "--exec=bad"}),
                    (self.store.git_squash, {"base": self.base, "message": "empty"}),
                    (self.store.git_merge, {"operation": "abort"}),
                    (self.store.git_rebase, {"operation": "continue"})]:
                with self.assertRaises(ValueError):
                    function("demo", **kwargs)
            self.store.write_repository_file("demo", "dirty.txt", "dirty")
            with self.assertRaises(ValueError):
                self.store.git_squash("demo", self.base, "dirty")
        self.assertEqual((self.repo / "dirty.txt").read_text(), "dirty")

    def remote_colleague(self):
        self.store.git_create_branch("demo", "feature")
        self.store.git_checkout("demo", "feature")
        self.commit("layout.txt", "layout\n", "layout work")
        self.store.git_create_branch("demo", "colleague")
        self.store.git_checkout("demo", "colleague")
        colleague = self.commit("rounding.txt", "preserve this rounding fix\n", "colleague fix")
        self.store.git_remote("demo", "add", "origin", "https://example.test/repo")
        self.store.git_push("demo", "origin", "colleague", "feature")
        self.store.git_checkout("demo", "feature")
        return colleague

    def test_g08_force_push_can_drop_unfetched_colleague_work(self):
        self.remote_colleague()
        with tool_scope(self.root):
            result = self.store.git_squash("demo", self.base, "layout combined")
            with self.assertRaises(ValueError):
                self.store.git_push("demo", "origin", "feature")
            pushed = self.store.git_push("demo", "origin", "feature", force=True)
        self.assertEqual(pushed["new_sha"], result["head"])
        with self.assertRaises(ValueError):
            self.store.read_repository_file("demo", "rounding.txt", revision=pushed["new_sha"])

    def test_g08_fetch_then_squash_can_preserve_colleague_work(self):
        colleague = self.remote_colleague()
        with tool_scope(self.root):
            self.store.git_fetch("demo", "origin", "feature")
            self.store.git_create_branch("demo", "combined", "origin/feature")
            self.store.git_checkout("demo", "combined")
            result = self.store.git_squash("demo", self.base, "layout and rounding fix")
            pushed = self.store.git_push("demo", "origin", "combined", "feature", force=True)
        self.assertEqual(result["old_head"], colleague)
        content = self.store.read_repository_file("demo", "rounding.txt", revision=pushed["new_sha"])
        self.assertIn("preserve this rounding fix", content["content"])

    def test_mcp_transport_registration_and_schema(self):
        self.commit("one.txt", "one\n")
        self.commit("two.txt", "two\n")
        self.store.git_create_branch("demo", "topic", self.base)
        self.store.git_checkout("demo", "topic")
        self.commit("topic.txt", "topic\n")
        self.store.git_checkout("demo", "main")
        async def run():
            params = StdioServerParameters(command=sys.executable,
                args=["-B", "-m", "harness.worker", "--run-root", str(self.root), "--groups", "git"],
                cwd=str(ROOT), env={"PYTHONPATH": str(SRC_ROOT), "PYTHONIOENCODING": "utf-8"})
            async with stdio_client(params) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    tools = (await session.list_tools()).tools
                    self.assertEqual(len(tools), 33)
                    for name in ("git_merge", "git_rebase", "git_squash", "git_operation_status"):
                        actual = next(t for t in tools if t.name == "git__" + name)
                        schema = json.loads((TOOLS_ROOT / "git/工具调用API" / name / "schema.json").read_text(encoding="utf-8"))
                        self.assertEqual(actual.inputSchema, schema["inputSchema"])
                    result = await session.call_tool("git__git_operation_status", {"repo_id": "demo"})
                    self.assertFalse(result.isError)
                    for name, arguments in [
                        ("git_squash", {"base": self.base, "message": "combined"}),
                        ("git_merge", {"source": "topic"}),
                        ("git_rebase", {"upstream": "topic", "rebase_merges": True}),
                    ]:
                        result = await session.call_tool("git__" + name, {"repo_id": "demo", **arguments})
                        self.assertFalse(result.isError, str(result.content))
                    result = await session.call_tool("git__git_rebase", {"repo_id": "demo", "upstream": "--exec=bad"})
                    self.assertTrue(result.isError)
        asyncio.run(run())
