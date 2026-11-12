"""Personal contacts, readable organization directory and mailbox delegation."""
import copy
import json

from .common import addresses, check_version, identifier, page, text, touch, unique
from .core import PERMISSIONS


class DirectoryMixin:
    @staticmethod
    def contact_visible(s, c):
        return (c.get("scope", "personal") == "personal" and c["owner_id"] == s["current_actor"] or
                c.get("scope") == "organization" and (c.get("visible_to") is None or s["current_actor"] in c["visible_to"]))

    @staticmethod
    def group_visible(s, g):
        if g.get("kind", "organization") == "personal":
            return g["owner_id"] == s["current_actor"]
        return g.get("visible_to") is None or s["current_actor"] in g["visible_to"]

    def search_contacts(self, query: str = "", offset: int = 0, limit: int = 20,
                        scope: str = "all") -> dict:
        if scope not in {"all", "personal", "organization"}:
            raise ValueError("Invalid directory scope")
        with self.state() as s:
            rows = [copy.deepcopy(c) for c in s["contacts"] if self.contact_visible(s, c)
                    and (scope == "all" or c.get("scope", "personal") == scope)
                    and query.casefold() in json.dumps({k: c.get(k) for k in ("id", "name", "emails", "organization", "remark")}, ensure_ascii=False).casefold()]
            return page(rows, offset, limit)

    def get_contact(self, contact_id: str) -> dict:
        with self.state() as s:
            c = self.resource(s, "contacts", contact_id)
            if not self.contact_visible(s, c):
                raise PermissionError("Contact is not visible")
            return copy.deepcopy(c)

    def write_contact(self, name: str, emails: list[str], contact_id: str | None = None,
                      default_email: str | None = None, organization: str = "", remark: str = "",
                      expected_version: int | None = None) -> dict:
        text(name, "name")
        emails = unique(addresses(emails))
        if not emails or default_email is not None and default_email not in emails:
            raise ValueError("Provide emails and a default_email belonging to them")
        with self.state(mutate=True) as s:
            c = self.resource(s, "contacts", contact_id) if contact_id else None
            if c and (c.get("scope", "personal") != "personal" or c["owner_id"] != s["current_actor"]):
                raise PermissionError("Only your personal contacts are editable")
            before = copy.deepcopy(c)
            if c is None:
                c = {"id": identifier("contact"), "owner_id": s["current_actor"], "scope": "personal", "version": 1}
                s["contacts"].append(c)
            else:
                check_version(c, expected_version)
                touch(c, s["now"])
            c.update(name=name, emails=emails, default_email=default_email or emails[0],
                     organization=organization, remark=remark)
            self.event(s, "write_contact", target=c["id"], before=before, after=c)
            return copy.deepcopy(c)

    def delete_contact(self, contact_id: str, expected_version: int | None = None) -> dict:
        with self.state(mutate=True) as s:
            c = self.resource(s, "contacts", contact_id)
            if c.get("scope", "personal") != "personal" or c["owner_id"] != s["current_actor"]:
                raise PermissionError("Only your personal contacts are editable")
            check_version(c, expected_version)
            s["contacts"].remove(c)
            self.event(s, "delete_contact", target=c["id"], before=c)
            return {"deleted_id": contact_id}

    def list_groups(self, query: str = "", offset: int = 0, limit: int = 20) -> dict:
        with self.state() as s:
            rows = []
            for g in s["groups"]:
                if not self.group_visible(s, g) or query.casefold() not in (g["name"] + " " + g.get("email_address", "")).casefold():
                    continue
                rows.append({k: copy.deepcopy(v) for k, v in g.items() if k not in {"members", "visible_to", "members_visible_to"}})
            return page(rows, offset, limit)

    def get_group(self, group_id: str, include_members: bool = True) -> dict:
        with self.state() as s:
            g = self.resource(s, "groups", group_id)
            if not self.group_visible(s, g):
                raise PermissionError("Group is not visible")
            result = {k: copy.deepcopy(v) for k, v in g.items() if k not in {"members", "visible_to", "members_visible_to"}}
            allowed = g.get("kind") == "personal" or g.get("members_visible_to") is None or s["current_actor"] in g["members_visible_to"]
            result["members_visible"] = allowed
            if include_members and allowed:
                result["members"] = copy.deepcopy(g.get("members", []))
            return result

    def write_contact_group(self, name: str, members: list[str], group_id: str | None = None,
                            expected_version: int | None = None) -> dict:
        text(name, "name")
        members = unique(addresses(members))
        with self.state(mutate=True) as s:
            g = self.resource(s, "groups", group_id) if group_id else None
            if g and (g.get("kind") != "personal" or g["owner_id"] != s["current_actor"]):
                raise PermissionError("Only your personal contact groups are editable")
            # Personal lists contain resolved addresses, never nested lists.
            group_addresses = {v.get("email_address", "").casefold() for v in s["groups"]}
            if any(v.casefold() in group_addresses for v in members):
                raise ValueError("Nested groups are not supported")
            before = copy.deepcopy(g)
            if g is None:
                g = {"id": identifier("group"), "kind": "personal", "owner_id": s["current_actor"], "version": 1}
                s["groups"].append(g)
            else:
                check_version(g, expected_version)
                touch(g, s["now"])
            g.update(name=name, members=members)
            self.event(s, "write_contact_group", target=g["id"], before=before, after=g)
            return copy.deepcopy(g)

    def delete_contact_group(self, group_id: str, expected_version: int | None = None) -> dict:
        with self.state(mutate=True) as s:
            g = self.resource(s, "groups", group_id)
            if g.get("kind") != "personal" or g["owner_id"] != s["current_actor"]:
                raise PermissionError("Only your personal contact groups are editable")
            check_version(g, expected_version)
            s["groups"].remove(g)
            self.event(s, "delete_contact_group", target=group_id, before=g)
            return {"deleted_id": group_id}

    def _resolve_recipients(self, s, values):
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise ValueError("Recipients must be a list of addresses or contact:/group: references")
        result = []
        for value in values:
            if value.startswith("contact:"):
                c = self.resource(s, "contacts", value.removeprefix("contact:"))
                if not self.contact_visible(s, c):
                    raise PermissionError("Contact is not visible")
                if not c["emails"]:
                    raise ValueError("Contact has no address")
                default = c.get("default_email")
                if len(c["emails"]) > 1 and default is None:
                    raise ValueError("Contact has multiple addresses; select an explicit address")
                result.append(default or c["emails"][0])
            elif value.startswith("group:"):
                g = self.resource(s, "groups", value.removeprefix("group:"))
                if not self.group_visible(s, g):
                    raise PermissionError("Group is not visible")
                if g.get("kind") == "personal":
                    result.extend(g["members"])
                else:
                    result.append(g["email_address"])
            else:
                result.extend(addresses([value]))
        return unique(addresses(result))

    def resolve_recipients(self, recipients: list[str]) -> dict:
        with self.state() as s:
            resolved = self._resolve_recipients(s, recipients)
            groups = []
            for value in resolved:
                group = next((g for g in s["groups"] if g.get("email_address", "").casefold() == value.casefold()), None)
                if group and self.group_visible(s, group):
                    visible = group.get("members_visible_to") is None or s["current_actor"] in group["members_visible_to"]
                    groups.append({"address": value, "members_visible": visible,
                                   **({"members": group.get("members", [])} if visible else {})})
            return {"addresses": resolved, "organization_groups": groups,
                    "group_expansion_time": "submission", "external_directory_status": "unknown"}

    def list_delegates(self, account_name: str) -> list[dict]:
        with self.state() as s:
            return copy.deepcopy(self.require(s, account_name, "manage")["delegates"])

    def set_delegate(self, account_name: str, actor_id: str, permissions: list[str],
                     expected_version: int | None = None) -> dict:
        text(actor_id, "actor_id")
        if not permissions or not set(permissions) <= PERMISSIONS - {"manage"}:
            raise ValueError("Grant read/write/send_as/send_on_behalf permissions")
        with self.state(mutate=True) as s:
            a = self.require(s, account_name, "manage")
            check_version(a, expected_version)
            if actor_id == a["owner_id"]:
                raise ValueError("Owner permissions are not delegated")
            known = {p["id"] for p in s["actors"]} | {v["owner_id"] for v in s["accounts"]}
            if actor_id not in known:
                raise ValueError("Unknown actor")
            before = copy.deepcopy(a["delegates"])
            a["delegates"] = [d for d in a["delegates"] if d["actor_id"] != actor_id]
            a["delegates"].append({"actor_id": actor_id, "permissions": sorted(set(permissions))})
            touch(a, s["now"])
            self.event(s, "set_delegate", account_name, actor_id, before, a["delegates"])
            return {"delegates": copy.deepcopy(a["delegates"]), "account_version": a["version"]}

    def remove_delegate(self, account_name: str, actor_id: str, expected_version: int | None = None) -> dict:
        with self.state(mutate=True) as s:
            a = self.require(s, account_name, "manage")
            check_version(a, expected_version)
            previous = copy.deepcopy(a["delegates"])
            a["delegates"] = [d for d in a["delegates"] if d["actor_id"] != actor_id]
            if previous == a["delegates"]:
                raise ValueError("Unknown delegate")
            touch(a, s["now"])
            self.event(s, "remove_delegate", account_name, actor_id, previous, a["delegates"])
            return {"removed_actor_id": actor_id, "account_version": a["version"]}
