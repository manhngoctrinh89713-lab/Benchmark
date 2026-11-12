"""Finite inbox rules and automatic replies, driven only by inbound events."""
import copy

from .common import addresses, check_version, date, identifier, matches, page, text, touch, unique, validate_filters
from .types import Condition, RuleAction

RULE_ACTIONS = {"move", "mark_read", "star", "add_category", "trash", "forward"}


class AutomationMixin:
    def list_rules(self, account_name: str, offset: int = 0, limit: int = 20) -> dict:
        with self.state() as s:
            self.require(s, account_name)
            rows = sorted([copy.deepcopy(r) for r in s["rules"] if r["account_name"] == account_name], key=lambda r: (r["priority"], r["id"]))
            return page(rows, offset, limit)

    def write_rule(self, account_name: str, name: str, conditions: list[Condition], actions: list[RuleAction],
                   rule_id: str | None = None, exceptions: list[Condition] | None = None,
                   priority: int = 100, enabled: bool = True, stop_processing: bool = False,
                   expected_version: int | None = None) -> dict:
        text(name, "name")
        validate_filters(conditions)
        validate_filters(exceptions or [])
        if any(c["field"] == "bcc" for c in conditions + (exceptions or [])):
            raise ValueError("Inbound rules cannot inspect blind recipients")
        if not actions or len(actions) > 10 or priority < 0:
            raise ValueError("Provide 1..10 actions and nonnegative priority")
        with self.state(mutate=True) as s:
            a = self.require(s, account_name, "write")
            normalized = []
            for action in actions:
                kind = action.get("type")
                if kind not in RULE_ACTIONS:
                    raise ValueError("Unsupported rule action")
                allowed = {"type"} | ({"mailbox"} if kind == "move" else {"category_id"} if kind == "add_category" else {"recipients"} if kind == "forward" else {"value"} if kind in {"mark_read", "star"} else set())
                if set(action) - allowed:
                    raise ValueError("Unsupported action fields")
                item = copy.deepcopy(action)
                if kind == "move":
                    item["mailbox"] = self.folder(a, action.get("mailbox"))["id"]
                elif kind == "add_category":
                    if action.get("category_id") not in {c["id"] for c in a["categories"]}:
                        raise ValueError("Unknown category")
                elif kind == "forward":
                    self.require(s, account_name, "send_as")
                    item["recipients"] = self._resolve_recipients(s, action.get("recipients", []))
                    if not item["recipients"]:
                        raise ValueError("Forward action requires recipients")
                elif kind in {"mark_read", "star"}:
                    if type(action.get("value", True)) is not bool:
                        raise ValueError("Action value must be boolean")
                    item["value"] = action.get("value", True)
                normalized.append(item)
            r = self.resource(s, "rules", rule_id) if rule_id else None
            if r and r["account_name"] != account_name:
                raise ValueError("Unknown rule in selected account")
            before = copy.deepcopy(r)
            if r is None:
                r = {"id": identifier("rule"), "account_name": account_name, "version": 1}
                s["rules"].append(r)
            else:
                check_version(r, expected_version)
                touch(r, s["now"])
            r.update(name=name, conditions=copy.deepcopy(conditions), exceptions=copy.deepcopy(exceptions or []),
                     actions=normalized, priority=priority, enabled=enabled, stop_processing=stop_processing,
                     created_by=s["current_actor"])
            self.event(s, "write_rule", account_name, r["id"], before, r)
            return copy.deepcopy(r)

    def delete_rule(self, account_name: str, rule_id: str, expected_version: int | None = None) -> dict:
        with self.state(mutate=True) as s:
            self.require(s, account_name, "write")
            r = self.resource(s, "rules", rule_id)
            if r["account_name"] != account_name:
                raise ValueError("Unknown rule in selected account")
            check_version(r, expected_version)
            s["rules"].remove(r)
            self.event(s, "delete_rule", account_name, rule_id, before=r)
            return {"deleted_id": rule_id}

    def get_auto_reply(self, account_name: str) -> dict:
        with self.state() as s:
            return copy.deepcopy(self.require(s, account_name)["auto_reply"])

    def set_auto_reply(self, account_name: str, enabled: bool, body: str = "",
                       external_body: str = "", external_audience: str = "none",
                       start_at: str | None = None, end_at: str | None = None,
                       expected_version: int | None = None) -> dict:
        if external_audience not in {"none", "contacts", "all"}:
            raise ValueError("external_audience must be none, contacts or all")
        if start_at:
            date(start_at)
        if end_at:
            date(end_at)
        if start_at and end_at and date(start_at) >= date(end_at):
            raise ValueError("start_at must precede end_at")
        text(body, "body", True)
        text(external_body, "external_body", True)
        with self.state(mutate=True) as s:
            a = self.require(s, account_name, "write")
            if enabled:
                self.require(s, account_name, "send_as")
            settings = a["auto_reply"]
            check_version(settings, expected_version)
            before = copy.deepcopy(settings)
            settings.update(enabled=enabled, body=body, external_body=external_body,
                            external_audience=external_audience, start_at=start_at, end_at=end_at,
                            created_by=s["current_actor"])
            touch(settings, s["now"])
            a["auto_reply_history"] = []
            self.event(s, "set_auto_reply", account_name, before=before, after=settings)
            return copy.deepcopy(settings)

    def _apply_incoming(self, s, received, automated=False):
        account_name, email_id = received["account_name"], received["id"]
        rules = sorted([copy.deepcopy(r) for r in s["rules"] if r["account_name"] == account_name and r["enabled"]],
                       key=lambda r: (r["priority"], r["id"]))
        for r in rules:
            received = next(m for m in s["messages"] if m["account_name"] == account_name and m["id"] == email_id)
            view = self.public(received, True)
            if not matches(view, r["conditions"]) or r["exceptions"] and matches(view, r["exceptions"], "any"):
                continue
            savepoint = copy.deepcopy(s)
            try:
                a = self.require(s, account_name, "write", r["created_by"])
                for action in r["actions"]:
                    a = self.account(s, account_name)
                    received = next(m for m in s["messages"] if m["account_name"] == account_name and m["id"] == email_id)
                    kind = action["type"]
                    before = copy.deepcopy(received)
                    if kind == "forward":
                        if automated:
                            continue
                        prepared = self._forward_prepared(s, received, action["recipients"])
                        self._submit(s, prepared, actor=r["created_by"], automatic=True)
                        received = next(m for m in s["messages"] if m["account_name"] == account_name and m["id"] == email_id)
                    elif kind == "move":
                        received["mailbox"] = self.folder(a, action["mailbox"])["path"]
                        if received["mailbox"] != "Trash":
                            received.pop("deleted_from", None)
                            received.pop("deleted_at", None)
                    elif kind == "mark_read":
                        received["is_read"] = action["value"]
                    elif kind == "star":
                        received["starred"] = action["value"]
                    elif kind == "add_category":
                        if action["category_id"] not in {c["id"] for c in a["categories"]}:
                            raise ValueError("Rule category no longer exists")
                        received["categories"] = sorted(set(received["categories"]) | {action["category_id"]})
                    elif kind == "trash":
                        if received["mailbox"] != "Trash":
                            received.update(deleted_from=received["mailbox"], deleted_at=s["now"], mailbox="Trash")
                    touch(received, s["now"])
                    self.event(s, "apply_rule_action", account_name, email_id, before,
                               {"rule_id": r["id"], "action": action, "message": received}, actor="mail-system")
            except (ValueError, PermissionError) as error:
                s.clear()
                s.update(savepoint)
                self.event(s, "rule_failed", account_name, email_id,
                           after={"rule_id": r["id"], "error": str(error)}, actor="mail-system")
            if r["stop_processing"]:
                break
        if automated:
            return
        a = self.account(s, account_name)
        received = next(m for m in s["messages"] if m["account_name"] == account_name and m["id"] == email_id)
        settings = a["auto_reply"]
        if not settings["enabled"] or received["mailbox"] in {"Trash", "Junk"}:
            return
        if settings.get("start_at") and date(s["now"]) < date(settings["start_at"]):
            return
        if settings.get("end_at") and date(s["now"]) >= date(settings["end_at"]):
            return
        if next((value for key, value in received.get("headers", {}).items() if key.casefold() == "auto-submitted"), "no").lower() != "no":
            return
        address = (received.get("reply_to") or [received["from"]])[0]
        own = {v.casefold() for v in [a["email_address"], *a["aliases"]]}
        if address.casefold() in own or address.casefold() in a["auto_reply_history"]:
            return
        internal = address.rpartition("@")[2].casefold() == a["email_address"].rpartition("@")[2].casefold()
        if not internal:
            audience = settings["external_audience"]
            contacts = {e.casefold() for c in s["contacts"] if c.get("owner_id") == a["owner_id"] for e in c["emails"]}
            if audience == "none" or audience == "contacts" and address.casefold() not in contacts:
                return
        body = settings["body"] if internal else settings["external_body"]
        if not body:
            return
        savepoint = copy.deepcopy(s)
        try:
            prepared = self._prepare(s, account_name, [address], "Automatic reply: " + received["subject"], body)
            prepared.update(in_reply_to=received["message_id"],
                            references=unique([*received.get("references", []), received["message_id"]]),
                            thread_id=received["thread_id"])
            self._submit(s, prepared, actor=settings["created_by"], automatic=True)
            self.account(s, account_name)["auto_reply_history"].append(address.casefold())
        except (ValueError, PermissionError) as error:
            s.clear()
            s.update(savepoint)
            self.event(s, "auto_reply_failed", account_name, email_id, after={"error": str(error)}, actor="mail-system")
