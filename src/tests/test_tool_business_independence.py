"""Public tools operate on resources without implementing fixture business rules."""
import asyncio
import copy
import inspect
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for relative in ("shared/maintenance", "shared/commerce", "server/公用代码",
                 "files/公用代码", "buyer/公用代码", "merchant/公用代码"):
    sys.path.insert(0, str(ROOT / "tools" / relative))

from local_server.backend import ServerStore
from local_files.backend import FileStore
from local_buyer.backend import BuyerStore
from local_buyer.server import create_server
from local_merchant.backend import MerchantStore


class ToolBusinessIndependenceTests(unittest.TestCase):
    def environment(self, case):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name) / "run"
        shutil.copytree(ROOT / "初始环境" / str(case), root)
        return root

    def state(self, root, group):
        return json.loads((root / "services" / group / "state.json").read_text(encoding="utf-8"))

    def test_diagnostic_service_reload_only_changes_service_state(self):
        root = self.environment("种子23")
        store = ServerStore(root)
        before = self.state(root, "server")
        result = store.server_change_service("settlement-diagnostics.service", "reload")
        self.assertTrue(result["success"])
        after = self.state(root, "server")
        self.assertEqual(after["business_events"], before["business_events"])
        self.assertEqual(after["runtime_configs"], before["runtime_configs"])

    def test_starting_a_service_does_not_issue_business_payments(self):
        root = self.environment("种子24")
        store = ServerStore(root)
        before = {path: path.read_bytes() for path in (root / "services/server/files").rglob("*")
                  if path.is_file() and "/srv/meal/" in path.as_posix()}
        result = store.server_change_service("meal-distribution.service", "start")
        self.assertTrue(result["success"])
        self.assertEqual(result["service"]["active_state"], "active")
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertEqual(self.state(root, "server")["business_events"], [])

    def test_stopping_processes_does_not_change_business_ledgers(self):
        for operation in ("stop", "restart", "TERM", "KILL", "reboot"):
            with self.subTest(operation=operation):
                root = self.environment("种子34")
                store = ServerStore(root)
                before = copy.deepcopy(self.state(root, "server")["settlement_batch"])
                if operation == "reboot":
                    store.server_reboot()
                elif operation in ("TERM", "KILL"):
                    pid = store.server_get_service("settlement-worker.service")["service"]["main_pid"]
                    store.server_signal_process(pid, operation)
                else:
                    store.server_change_service("settlement-worker.service", operation)
                self.assertEqual(self.state(root, "server")["settlement_batch"], before)

    def test_reload_uses_service_capability_without_special_config_keys(self):
        root = self.environment("种子40")
        store = ServerStore(root)
        before = self.state(root, "server")
        result = store.server_change_service("edge-gw-a.service", "reload")
        self.assertTrue(result["success"])
        self.assertFalse(result["service"]["config_pending"])
        self.assertEqual(result["service"]["main_pid"], before["services"]["edge-gw-a.service"]["main_pid"])

    def test_restart_updates_process_but_not_application_session_files(self):
        root = self.environment("种子40")
        store = ServerStore(root)
        before = self.state(root, "server")
        sessions = store.server_read_file("/run/edge-gw/sessions.json")["content"]
        result = store.server_change_service("edge-gw-c.service", "restart")
        self.assertTrue(result["success"])
        self.assertNotEqual(result["service"]["main_pid"], before["services"]["edge-gw-c.service"]["main_pid"])
        self.assertEqual(store.server_read_file("/run/edge-gw/sessions.json")["content"], sessions)
        self.assertEqual(self.state(root, "server")["gateway_sessions"], before["gateway_sessions"])

    def test_debug_configuration_does_not_generate_business_requests(self):
        root = self.environment("种子41")
        store = ServerStore(root)
        config = store.server_read_service_config("order-svc.service")
        data = json.loads(config["content"])
        data["log_level"] = "debug"
        store.server_write_service_config("order-svc.service", json.dumps(data), config["sha256"])
        before = {path: path.read_bytes() for path in (root / "services/server/files").rglob("*") if path.is_file()}
        store.server_change_service("order-svc.service", "reload")
        after = self.state(root, "server")
        self.assertEqual(after["business_events"], [])
        for path, raw in before.items():
            if "journal" not in path.name:
                self.assertEqual(path.read_bytes(), raw, str(path))

    def test_log_queries_are_read_only(self):
        root = self.environment("种子50")
        store = ServerStore(root)
        before = {path: path.read_bytes() for path in (root / "services/server").rglob("*")
                  if path.is_file() and not path.name.endswith(".lock")}
        first = store.server_query_logs()
        self.assertEqual(store.server_query_logs(), first)
        after = {path: path.read_bytes() for path in (root / "services/server").rglob("*")
                 if path.is_file() and not path.name.endswith(".lock")}
        self.assertEqual(after, before)

    def test_files_do_not_mutate_other_service_state(self):
        root = self.environment("种子50")
        ServerStore(root)
        store = FileStore(root)
        state_path = root / "services/server/state.json"
        before = state_path.read_bytes()
        store.move_file("server/volumes/root/var/log/audit/current.log", "audit-history.log")
        self.assertEqual(state_path.read_bytes(), before)

    def test_service_restart_does_not_rewrite_audit_pipeline(self):
        root = self.environment("种子50")
        store = ServerStore(root)
        before = self.state(root, "server")
        def audit_logs():
            return {item['path']: store.server_read_file(item['path'])['sha256']
                    for item in store.server_list_directory('/var/log/audit', limit=100)['items'] if item['type']=='file'}
        logs_before = audit_logs()
        self.assertTrue(logs_before)
        store.server_change_service("audit-logd.service", "restart")
        after = self.state(root, "server")
        self.assertEqual(audit_logs(), logs_before)
        self.assertNotEqual(after['services']['audit-logd.service']['main_pid'], before['services']['audit-logd.service']['main_pid'])
        self.assertEqual(after["business_events"], before["business_events"])

    def test_checkout_schema_has_only_general_order_parameters(self):
        self.assertEqual(set(inspect.signature(BuyerStore.checkout_cart).parameters),
                         {"self", "merchant_id", "expected_total_minor", "idempotency_key", "shipping_address"})
        root = self.environment("综合测试")
        server = create_server(BuyerStore(root))
        tool = next(t for t in asyncio.run(server.list_tools()) if t.name == "checkout_cart")
        self.assertEqual(set(tool.inputSchema["properties"]),
                         {"merchant_id", "expected_total_minor", "idempotency_key", "shipping_address"})

    def test_checkout_uses_uniform_product_snapshots(self):
        root = self.environment("综合测试")
        buyer = BuyerStore(root)
        state = self.state(root, "commerce")
        product = state["products"]["prod_ebook"]
        product["service_type"] = "travel_insurance"
        product["custom_terms"] = {"region": "example"}
        (root / "services/commerce/state.json").write_text(json.dumps(state), encoding="utf-8")
        buyer.update_cart("merchant_demo", [{"product_id": "prod_ebook", "quantity": 1}])
        before = buyer.get_product("prod_ebook")["product"]
        total = buyer.get_cart("merchant_demo")["cart"]["total_minor"]
        order = buyer.checkout_cart("merchant_demo", total, "checkout")["order"]
        snapshot = order["items"][0]["product_snapshot"]
        self.assertEqual(snapshot, before)
        self.assertNotIn("service_type", snapshot)
        self.assertNotIn("custom_terms", snapshot)
        MerchantStore(root).update_product("prod_ebook", description="new terms")
        self.assertEqual(buyer.get_my_order(order["id"])["order"]["items"][0]["product_snapshot"], snapshot)
        self.assertEqual(buyer.checkout_cart("merchant_demo", total, "checkout")["order"]["id"], order["id"])

    def test_product_search_has_a_uniform_summary_and_full_details(self):
        root = self.environment("综合测试")
        state = self.state(root, "commerce")
        product = state["products"]["prod_ebook"]
        product["custom_terms"] = {"region": "example"}
        product["usage_rules"] = {"scope": "example"}
        (root / "services/commerce/state.json").write_text(json.dumps(state), encoding="utf-8")
        buyer = BuyerStore(root)
        summary = next(p for p in buyer.search_products()["items"] if p["id"] == "prod_ebook")
        self.assertNotIn("custom_terms", summary)
        self.assertNotIn("usage_rules", summary)
        details = buyer.get_product("prod_ebook")["product"]
        self.assertEqual(details, summary)
        self.assertEqual(details["description"], product["description"])


if __name__ == "__main__":
    unittest.main()
