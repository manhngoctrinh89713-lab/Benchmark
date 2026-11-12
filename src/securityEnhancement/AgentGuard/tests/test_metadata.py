"""Tests for the deterministic capability metadata classifier."""
from __future__ import annotations

import unittest
from pathlib import Path

from securityEnhancement.AgentGuard.config import CLASSIFIER_VERSION
from securityEnhancement.AgentGuard.metadata import KNOWN_GROUPS, classify

# (group, public tool name, expected capability, expected side_effect, expected risk)
CASES = [
    # mail
    ("mail", "mail__list_mailboxes", "mail.read", False, "low"),
    ("mail", "mail__read_email", "mail.read", False, "low"),
    ("mail", "mail__download_attachment", "mail.read", True, "low"),
    ("mail", "mail__send_email", "mail.send", True, "medium"),
    ("mail", "mail__reply_email", "mail.send", True, "medium"),
    ("mail", "mail__forward_email", "mail.send", True, "medium"),
    ("mail", "mail__delete_emails", "mail.delete", True, "high"),
    ("mail", "mail__empty_mailbox", "mail.delete", True, "high"),
    ("mail", "mail__create_draft", "mail.write", True, "medium"),
    ("mail", "mail__update_draft", "mail.write", True, "medium"),
    ("mail", "mail__schedule_email", "mail.send", True, "medium"),
    ("mail", "mail__update_scheduled_email", "mail.send", True, "medium"),
    ("mail", "mail__cancel_scheduled_email", "mail.write", True, "medium"),
    ("mail", "mail__list_scheduled_emails", "mail.read", False, "low"),
    # chat
    ("chat", "chat__list_chats", "chat.read", False, "low"),
    ("chat", "chat__download_media", "chat.read", True, "low"),
    ("chat", "chat__send_message", "chat.send", True, "medium"),
    ("chat", "chat__forward_messages", "chat.send", True, "medium"),
    ("chat", "chat__recall_message", "chat.delete", True, "high"),
    ("chat", "chat__clear_chat_history", "chat.delete", True, "high"),
    ("chat", "chat__save_draft", "chat.write", True, "medium"),
    ("chat", "chat__mark_read", "chat.write", True, "medium"),
    # files
    ("files", "files__read_document", "file.read", False, "low"),
    ("files", "files__list_directory", "file.read", False, "low"),
    ("files", "files__search_files", "file.read", False, "low"),
    ("files", "files__directory_tree", "file.read", False, "low"),
    ("files", "files__write_file", "file.write", True, "medium"),
    ("files", "files__append_file", "file.write", True, "medium"),
    ("files", "files__move_file", "file.write", True, "medium"),
    ("files", "files__extract_archive", "file.write", True, "medium"),
    ("files", "files__delete_file", "file.delete", True, "high"),
    ("files", "files__trash_file", "file.delete", True, "high"),
    ("files", "files__delete_trash", "file.delete", True, "high"),
    # database
    ("database", "database__read_query", "db.read", False, "low"),
    ("database", "database__list_tables", "db.read", False, "low"),
    ("database", "database__backup_database", "db.read", True, "low"),
    ("database", "database__write_query", "db.write", True, "high"),
    ("database", "database__execute_schema", "db.write", True, "high"),
    ("database", "database__import_csv", "db.write", True, "high"),
    ("database", "database__delete_database", "db.write", True, "high"),
    # code
    ("code", "code__read_code", "code.read", False, "low"),
    ("code", "code__find_references", "code.read", False, "low"),
    ("code", "code__get_diagnostics", "code.read", False, "low"),
    ("code", "code__create_code_file", "code.write", True, "medium"),
    ("code", "code__delete_code_file", "code.write", True, "medium"),
    ("code", "code__apply_workspace_edit", "code.write", True, "medium"),
    # git
    ("git", "git__git_log", "repo.read", False, "low"),
    ("git", "git__git_diff", "repo.read", False, "low"),
    ("git", "git__git_status", "repo.read", False, "low"),
    ("git", "git__git_branches", "repo.read", False, "low"),
    ("git", "git__git_file_history", "repo.read", False, "low"),
    ("git", "git__git_operation_status", "repo.read", False, "low"),
    ("git", "git__read_repository_file", "repo.read", False, "low"),
    ("git", "git__git_commit", "repo.write", True, "medium"),
    ("git", "git__git_push", "repo.write", True, "medium"),
    ("git", "git__git_merge", "repo.write", True, "medium"),
    ("git", "git__git_reset", "repo.write", True, "medium"),
    ("git", "git__git_remote", "repo.write", True, "medium"),
    # github
    ("github", "github__get_file_contents", "repo.read", False, "low"),
    ("github", "github__list_pull_requests", "repo.read", False, "low"),
    ("github", "github__pull_request_read", "repo.read", False, "low"),
    ("github", "github__issue_read", "repo.read", False, "low"),
    ("github", "github__search_code", "repo.read", False, "low"),
    ("github", "github__create_pull_request", "repo.write", True, "medium"),
    ("github", "github__merge_pull_request", "repo.write", True, "medium"),
    ("github", "github__delete_release", "repo.write", True, "medium"),
    ("github", "github__mark_notification_read", "repo.write", True, "medium"),
    ("github", "github__update_repository_visibility", "repo.write", True, "medium"),
    # pc
    ("pc", "pc__pc_read_personal_file", "file.read", False, "low"),
    ("pc", "pc__pc_list_personal_files", "file.read", False, "low"),
    ("pc", "pc__pc_list_recycle_bin", "file.read", False, "low"),
    ("pc", "pc__pc_write_personal_file", "file.write", True, "medium"),
    ("pc", "pc__pc_copy_personal_file", "file.write", True, "medium"),
    ("pc", "pc__pc_move_personal_file", "file.write", True, "medium"),
    ("pc", "pc__pc_restore_recycled_file", "file.write", True, "medium"),
    ("pc", "pc__pc_delete_personal_file", "file.delete", True, "high"),
    ("pc", "pc__pc_delete_recycled_file", "file.delete", True, "high"),
    ("pc", "pc__pc_recycle_file", "file.delete", True, "high"),
    ("pc", "pc__pc_get_system_info", "host.read", False, "low"),
    ("pc", "pc__pc_get_environment_variables", "host.read", False, "low"),
    ("pc", "pc__pc_list_processes", "host.read", False, "low"),
    ("pc", "pc__pc_set_environment_variable", "host.admin", True, "high"),
    ("pc", "pc__pc_delete_startup_item", "host.admin", True, "high"),
    ("pc", "pc__pc_save_scheduled_task", "host.admin", True, "high"),
    ("pc", "pc__pc_clean_cache", "host.admin", True, "high"),
    ("pc", "pc__pc_create_backup", "host.admin", True, "high"),
    ("pc", "pc__pc_verify_backup", "host.read", False, "low"),
    ("pc", "pc__pc_launch_application", "process.control", True, "high"),
    ("pc", "pc__pc_change_process", "process.control", True, "high"),
    # server
    ("server", "server__server_read_file", "file.read", False, "low"),
    ("server", "server__server_list_directory", "file.read", False, "low"),
    ("server", "server__server_write_file", "file.write", True, "medium"),
    ("server", "server__server_create_directory", "file.write", True, "medium"),
    ("server", "server__server_delete_file", "file.delete", True, "high"),
    ("server", "server__server_remove_directory", "file.delete", True, "high"),
    ("server", "server__server_get_disk_usage", "host.read", False, "low"),
    ("server", "server__server_query_logs", "host.read", False, "low"),
    ("server", "server__server_read_service_config", "host.read", False, "low"),
    ("server", "server__server_get_permissions", "host.read", False, "low"),
    ("server", "server__server_set_environment_variable", "host.admin", True, "high"),
    ("server", "server__server_prune_logs", "host.admin", True, "high"),
    ("server", "server__server_write_service_config", "host.admin", True, "high"),
    ("server", "server__server_validate_service_config", "host.read", False, "low"),
    ("server", "server__server_verify_backup", "host.read", False, "low"),
    ("server", "server__server_reboot", "host.admin", True, "high"),
    ("server", "server__server_signal_process", "process.control", True, "high"),
    ("server", "server__server_change_service", "process.control", True, "high"),
    # merchant
    ("merchant", "merchant__list_merchant_orders", "commerce.read", False, "low"),
    ("merchant", "merchant__get_merchant_order", "commerce.read", False, "low"),
    ("merchant", "merchant__export_orders", "commerce.read", True, "low"),
    ("merchant", "merchant__update_product", "commerce.write", True, "medium"),
    ("merchant", "merchant__adjust_inventory", "commerce.write", True, "medium"),
    ("merchant", "merchant__cancel_merchant_order", "commerce.write", True, "medium"),
    ("merchant", "merchant__resolve_aftersale", "commerce.write", True, "medium"),
    ("merchant", "merchant__refund_payment", "commerce.transaction", True, "high"),
    ("merchant", "merchant__resolve_refund_request", "commerce.transaction", True, "high"),
    ("merchant", "merchant__process_subscription_renewals", "commerce.transaction", True, "high"),
    # buyer
    ("buyer", "buyer__get_cart", "commerce.read", False, "low"),
    ("buyer", "buyer__list_my_orders", "commerce.read", False, "low"),
    ("buyer", "buyer__download_receipt", "commerce.read", True, "low"),
    ("buyer", "buyer__set_cart_item", "commerce.write", True, "medium"),
    ("buyer", "buyer__request_refund", "commerce.write", True, "medium"),
    ("buyer", "buyer__confirm_shipment_receipt", "commerce.write", True, "medium"),
    ("buyer", "buyer__checkout_cart", "commerce.transaction", True, "high"),
    ("buyer", "buyer__pay_order", "commerce.transaction", True, "high"),
    ("buyer", "buyer__place_order_from_quote", "commerce.transaction", True, "high"),
    ("buyer", "buyer__subscribe_plan", "commerce.transaction", True, "high"),
    ("buyer", "buyer__reorder", "commerce.write", True, "medium"),
]


class MetadataTests(unittest.TestCase):
    def test_representative_tools_per_group(self):
        for group, name, capability, side_effect, risk in CASES:
            with self.subTest(tool=name):
                metadata = classify(group, name)
                self.assertEqual(metadata.capabilities, [capability])
                self.assertEqual(metadata.side_effect, side_effect)
                self.assertEqual(metadata.risk_level, risk)
                self.assertFalse(metadata.fallback)
                self.assertEqual(metadata.group, group)
                self.assertEqual(metadata.tool_name, name)
                self.assertEqual(metadata.classifier_version, CLASSIFIER_VERSION)

    def test_all_groups_are_covered(self):
        groups = {case[0] for case in CASES}
        self.assertEqual(groups, set(KNOWN_GROUPS))

    def test_refund_capability_uses_description_context(self):
        cases = [
            ("merchant", "merchant__complete_aftersale",
             "收到退件后按成交金额发起退款，或为原规格创建换货包裹。", "commerce.transaction"),
            ("merchant", "merchant__resolve_cancellation_request",
             "审批取消申请；同意后取消未履约订单并发起退款，退款到账另行记录。", "commerce.transaction"),
            ("merchant", "merchant__resolve_aftersale",
             "审批退换货申请，同意时提供退件地址。", "commerce.write"),
            ("buyer", "buyer__request_refund",
             "向商家申请退还指定支付的部分或全部可退金额。", "commerce.write"),
            ("buyer", "buyer__withdraw_refund_request",
             "撤回待审批的退款申请。", "commerce.write"),
        ]
        for group, name, description, expected in cases:
            with self.subTest(tool=name):
                metadata = classify(group, name, description)
                self.assertEqual(metadata.capabilities, [expected])
                self.assertFalse(metadata.fallback)

    def test_unknown_tool_has_stable_low_risk_fallback(self):
        metadata = classify("files", "files__frobnicate_widget")
        self.assertEqual(metadata.capabilities, ["unknown.read"])
        self.assertTrue(metadata.fallback)
        self.assertEqual(metadata.risk_level, "low")
        self.assertFalse(metadata.side_effect)
        self.assertEqual(metadata.basis, "fallback:unknown.read")
        self.assertEqual(classify("files", "files__frobnicate_widget"), metadata)

    def test_unknown_tool_write_hint_from_description(self):
        metadata = classify("files", "files__frobnicate_widget", "创建并写入一个新文件")
        self.assertEqual(metadata.capabilities, ["unknown.write"])
        self.assertTrue(metadata.fallback)
        self.assertTrue(metadata.side_effect)

    def test_unknown_tool_write_hint_from_schema(self):
        schema = {"type": "object", "properties": {"content": {"type": "string"}}}
        metadata = classify("mystery", "mystery__widget", "", schema)
        self.assertEqual(metadata.capabilities, ["unknown.write"])

    def test_unknown_group_never_raises(self):
        for name in ("", "widget", "工具__读取", "a__b__c"):
            metadata = classify("mystery", name)
            self.assertEqual(metadata.classifier_version, CLASSIFIER_VERSION)
            self.assertTrue(metadata.capabilities)

    def test_classification_does_not_depend_on_seed_numbers(self):
        plain = classify("files", "files__write_file")
        seeded = classify("files", "files__seed42_write_file")
        self.assertEqual(plain.capabilities, seeded.capabilities)
        self.assertEqual(plain.side_effect, seeded.side_effect)
        self.assertFalse(seeded.fallback)

    def test_every_published_tool_is_classified_without_fallback(self):
        tools_root = Path(__file__).resolve().parents[4] / "tools"
        api = tools_root
        if not api.is_dir():
            self.skipTest("benchmark tools directory not available")
        missing = []
        checked = 0
        for group in sorted(KNOWN_GROUPS):
            directory = api / group / "工具调用API"
            if not directory.is_dir():
                continue
            for entry in sorted(directory.iterdir()):
                if not entry.is_dir():
                    continue
                checked += 1
                metadata = classify(group, f"{group}__{entry.name}")
                if metadata.fallback:
                    missing.append((group, entry.name, metadata.basis))
        self.assertGreater(checked, 0)
        self.assertEqual(missing, [], "public tools fell back to unknown metadata")


if __name__ == "__main__":
    unittest.main()
