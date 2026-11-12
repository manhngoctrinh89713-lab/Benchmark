import asyncio
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import AsyncMock, patch

from filelock import Timeout

from harness.runner import execute, execute_all_variants
from harness.environment import environment_directory, model_directory, model_lock, reset_environment


class ModelEnvironmentTests(unittest.TestCase):
    def test_reset_only_replaces_selected_model(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            source = base / "initial"
            source.mkdir()
            (source / "state.txt").write_text("initial")
            with patch("harness.environment.ROOT", base):
                first = reset_environment(source, "deepseek-flash")
                second = reset_environment(source, "qwen-plus")
                self.assertEqual(first, environment_directory("deepseek-flash", source.name))
                (first / "leftover.txt").write_text("old")
                (second / "state.txt").write_text("other model")
                reset_environment(source, "deepseek-flash")
                self.assertFalse((first / "leftover.txt").exists())
                self.assertEqual((second / "state.txt").read_text(), "other model")

    def test_reset_preserves_other_cases_on_same_model(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            sources = [base / name for name in ("seed1", "seed2")]
            for source in sources:
                source.mkdir()
                (source / "state.txt").write_text(source.name)
            with patch("harness.environment.ROOT", base):
                first = reset_environment(sources[0])
                second = reset_environment(sources[1])
                (second / "state.txt").write_text("running other case")
                (first / "leftover.txt").write_text("old")
                reset_environment(sources[0])
                self.assertFalse((first / "leftover.txt").exists())
                self.assertEqual((second / "state.txt").read_text(), "running other case")

    def test_execute_blocks_same_pair_but_allows_other_pairs(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("harness.environment.ROOT", Path(directory)), patch(
                "harness.runner.ROOT", Path(directory)
            ), patch(
                "harness.runner.initial_case", side_effect=lambda case: Path(case)
            ), patch("harness.runner._execute_locked", new_callable=AsyncMock) as run:
                with model_lock("deepseek-flash", "seed1"):
                    with self.assertRaises(Timeout):
                        asyncio.run(execute(Namespace(model="deepseek-flash", case="seed1")))
                    run.assert_not_awaited()
                    asyncio.run(execute(Namespace(model="deepseek-flash", case="seed2")))
                    asyncio.run(execute(Namespace(model="qwen-plus", case="seed1")))
                    self.assertEqual(run.await_count, 2)
                asyncio.run(execute(Namespace(model="deepseek-flash", case="seed1")))
                self.assertEqual(run.await_count, 3)

    def test_all_variants_holds_case_lock_for_entire_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            case_dir = base / "prompt/cases/seed1"
            case_dir.mkdir(parents=True)
            variants = {name: {"category": "test", "instruction_type": name}
                        for name in ("primary", "secondary")}
            (case_dir / "config.json").write_text(json.dumps({"variants": variants}))
            async def check_locks(args):
                with self.assertRaises(Timeout):
                    with model_lock(args.model, args.case):
                        pass
                with model_lock(args.model, "seed2"):
                    pass
                record = base / "运行记录" / args.run_id
                record.mkdir()
                (record / "run.json").write_text('{"status": "completed"}')
            with patch("harness.environment.ROOT", base), patch(
                "harness.runner.ROOT", base
            ), patch(
                "harness.runner.initial_case", return_value=Path("seed1")
            ), patch("harness.runner._execute_locked", side_effect=check_locks) as run:
                asyncio.run(execute_all_variants(Namespace(model="deepseek-flash", case="seed1")))
                self.assertEqual(run.await_count, 2)
                with model_lock("deepseek-flash", "seed1"):
                    pass

    def test_model_ids_are_safe_single_directory_names(self):
        for model in ("../escape", "vendor/model", "CON", "a:b", "..", "a."):
            name = model_directory(model)
            self.assertEqual(Path(name).name, name)
            self.assertNotIn("/", name)
            self.assertNotIn(":", name)
        self.assertNotEqual(model_directory("vendor/model"), model_directory("vendor:model"))
        self.assertEqual(model_directory("DeepSeek-Flash"), "deepseek-flash")
