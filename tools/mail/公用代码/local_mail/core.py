"""Transactional mailbox storage, authorization and immutable operation evidence."""
import base64
import copy
from contextlib import contextmanager
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import tempfile

from filelock import FileLock
from .common import addresses, date, identifier, text

PERMISSIONS = {"read", "write", "send_as", "send_on_behalf", "manage"}
SYSTEM_FOLDERS = {"INBOX", "Sent", "Trash", "Drafts", "Archive", "Junk"}


class MailCore:
    def __init__(self, run_root):
        self.root = Path(run_root).resolve()
        self.workspace = self.root / "workspace"
        self.service = self.root / "services/mail"
        self.path = self.service / "state.json"
        self.lock = FileLock(str(self.service / "state.lock"), timeout=10)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.service.mkdir(parents=True, exist_ok=True)
        with self.lock:
            if not self.path.exists():
                raise ValueError("Missing mail environment")
            state = json.loads(self.path.read_text(encoding="utf-8-sig"))
            self.normalize(state)
            self.validate(state)
            self.atomic_json(self.path, state)

    @staticmethod
    def normalize(s):
        s.setdefault("current_actor", "local-user")
        s.setdefault("sequence", 0)
        for key in ("contacts", "messages", "drafts", "groups", "rules", "scheduled",
                    "submissions", "events", "sent_events", "actors", "delivery_events"):
            s.setdefault(key, [])
        s["mail_model_version"] = 2
        for a in s["accounts"]:
            a.setdefault("owner_id", s["current_actor"])
            a.setdefault("aliases", [])
            a.setdefault("delegates", [])
            a.setdefault("version", 1)
            a.setdefault("categories", [])
            a.setdefault("auto_reply", {"enabled": False, "body": "", "external_body": "",
                                        "external_audience": "none", "start_at": None,
                                        "end_at": None, "version": 1})
            a.setdefault("auto_reply_history", [])
            for name in ("INBOX", "Sent", "Trash", "Drafts", "Archive", "Junk"):
                if name not in a["mailboxes"]:
                    a["mailboxes"].append(name)
            a.setdefault("folders", [])
            known = {f["path"] for f in a["folders"]}
            for path in list(a["mailboxes"]):
                components = path.split("/")
                for index in range(1, len(components) + 1):
                    full = "/".join(components[:index])
                    if full not in known:
                        parent = next((f["id"] for f in a["folders"] if f["path"] == full.rpartition("/")[0]), None)
                        a["folders"].append({"id": identifier("folder"), "name": components[index-1],
                                             "path": full, "parent_id": parent,
                                             "system": full in SYSTEM_FOLDERS, "version": 1})
                        known.add(full)
                        if full not in a["mailboxes"]:
                            a["mailboxes"].append(full)
        for c in s["contacts"]:
            c.setdefault("owner_id", s["current_actor"])
            c.setdefault("scope", "personal")
            c.setdefault("version", 1)
        for g in s["groups"]:
            g.setdefault("kind", "organization")
            g.setdefault("version", 1)
            if g["kind"] == "personal":
                g.setdefault("owner_id", s["current_actor"])
        for m in s["messages"]:
            m.setdefault("version", 1)
            m.setdefault("cc", [])
            m.setdefault("bcc", [])
            m.setdefault("attachments", [])
            m.setdefault("categories", [])
            m.setdefault("is_read", False)
            m.setdefault("starred", False)
            m.setdefault("importance", "normal")
            for attachment in m["attachments"]:
                attachment.setdefault("content_type", mimetypes.guess_type(attachment["name"])[0] or "application/octet-stream")
            a = next(a for a in s["accounts"] if a["account_name"] == m["account_name"])
            identities = [a["email_address"], *a["aliases"]]
            m.setdefault("sender_copy", m["from"].casefold() in [v.casefold() for v in identities])
            m.setdefault("thread_id", identifier("thread"))
        lookup = {(m["account_name"], m.get("message_id")): m for m in s["messages"]}
        # Existing references are used only during first migration.
        if not s.get("threads_initialized"):
            def root_id(m, seen):
                while True:
                    key = (m["account_name"], m.get("message_id"))
                    parent = lookup.get((m["account_name"], m.get("in_reply_to")))
                    if not parent or key in seen:
                        return m["thread_id"]
                    seen.add(key)
                    m = parent
            roots = {m["id"] + "@" + m["account_name"]: root_id(m, set()) for m in s["messages"]}
            for m in s["messages"]:
                m["thread_id"] = roots[m["id"] + "@" + m["account_name"]]
            s["threads_initialized"] = True

    @staticmethod
    def validate(s):
        date(s["now"])
        names = [a["account_name"] for a in s["accounts"]]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate account names")
        all_addresses = [v.casefold() for a in s["accounts"] for v in [a["email_address"], *a["aliases"]]]
        if len(all_addresses) != len(set(all_addresses)):
            raise ValueError("Mailbox identities must be unique")
        for a in s["accounts"]:
            addresses([a["email_address"], *a.get("aliases", [])])
            if not {"INBOX", "Sent", "Trash"} <= set(a["mailboxes"]):
                raise ValueError("Missing system folders")
            folders = a["folders"]
            if len({f["id"] for f in folders}) != len(folders) or len({f["path"] for f in folders}) != len(folders):
                raise ValueError("Duplicate folders")
            if {f["path"] for f in folders} != set(a["mailboxes"]):
                raise ValueError("Folder catalog and mailbox paths disagree")
            for f in folders:
                parent = next((v for v in folders if v["id"] == f["parent_id"]), None) if f["parent_id"] else None
                if f["parent_id"] and not parent or f["path"] != (parent["path"] + "/" if parent else "") + f["name"]:
                    raise ValueError("Invalid folder hierarchy")
                if f["system"] != (f["path"] in SYSTEM_FOLDERS):
                    raise ValueError("Invalid system folder flag")
            for delegate in a.get("delegates", []):
                if not set(delegate["permissions"]) <= PERMISSIONS - {"manage"}:
                    raise ValueError("Invalid delegated permissions")
        ids = [(m["account_name"], m["id"]) for m in s["messages"]]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate mail IDs within an account")
        for m in s["messages"]:
            a = next((a for a in s["accounts"] if a["account_name"] == m["account_name"]), None)
            if not a or m["mailbox"] not in a["mailboxes"]:
                raise ValueError("Unknown mailbox")
            date(m["timestamp"])
            addresses([m["from"]])
            for field in ("to", "cc", "bcc", "reply_to"):
                addresses(m.get(field, []))
            aids = [a["id"] for a in m.get("attachments", [])]
            if len(aids) != len(set(aids)):
                raise ValueError("Duplicate attachment IDs")
        for c in s["contacts"]:
            addresses(c["emails"])
            if c.get("default_email") and c["default_email"] not in c["emails"]:
                raise ValueError("Contact default_email must belong to emails")
        group_addresses = []
        for g in s["groups"]:
            if g["kind"] not in {"personal", "organization"}:
                raise ValueError("Invalid group kind")
            addresses(g["members"])
            if g["kind"] == "organization":
                addresses([g["email_address"]])
                group_addresses.append(g["email_address"].casefold())
        if len(group_addresses) != len(set(group_addresses)) or set(group_addresses) & set(all_addresses):
            raise ValueError("Group address conflicts with another recipient identity")
        if any(v.casefold() in group_addresses for g in s["groups"] for v in g["members"]):
            raise ValueError("Nested groups are not supported")
        for key in ("contacts", "groups", "rules", "drafts", "scheduled", "submissions", "actors"):
            ids = [v["id"] for v in s[key]]
            if len(ids) != len(set(ids)):
                raise ValueError("Duplicate " + key + " IDs")
        for key in ("rules", "drafts", "scheduled", "submissions"):
            if any(v["account_name"] not in names for v in s[key]):
                raise ValueError("Unknown account in " + key)

    @staticmethod
    def atomic_json(path, data):
        fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    @contextmanager
    def state(self, mutate=False):
        with self.lock:
            s = json.loads(self.path.read_text(encoding="utf-8"))
            yield s
            if mutate:
                self.validate(s)
                self.atomic_json(self.path, s)

    @staticmethod
    def account(s, name):
        a = next((a for a in s["accounts"] if a["account_name"] == name), None)
        if a is None:
            raise ValueError("Unknown account")
        return a

    @staticmethod
    def permissions(s, account, actor=None):
        actor = actor or s["current_actor"]
        if actor == account["owner_id"]:
            return set(PERMISSIONS)
        return {p for d in account.get("delegates", []) if d["actor_id"] == actor for p in d["permissions"]}

    def require(self, s, name, permission="read", actor=None):
        a = self.account(s, name)
        if permission not in self.permissions(s, a, actor):
            raise PermissionError("Mailbox permission denied: " + permission)
        return a

    def message(self, s, account_name, email_id, permission="read"):
        self.require(s, account_name, permission)
        result = next((m for m in s["messages"] if m["account_name"] == account_name and m["id"] == email_id), None)
        if result is None:
            raise ValueError("Unknown email")
        return result

    @staticmethod
    def resource(s, collection, resource_id):
        obj = next((obj for obj in s[collection] if obj["id"] == resource_id), None)
        if obj is None:
            raise ValueError("Unknown " + collection + " resource")
        return obj

    @staticmethod
    def folder(account, value):
        result = next((f for f in account["folders"] if value in (f["id"], f["path"])), None)
        if result is None:
            raise ValueError("Unknown folder")
        return result

    @staticmethod
    def event(s, action, account_name=None, target=None, before=None, after=None, actor=None):
        s["sequence"] += 1
        s["events"].append({"id": identifier("event"), "sequence": s["sequence"], "at": s["now"],
                            "actor_id": actor or s["current_actor"], "action": action,
                            "account_name": account_name, "target": target,
                            "before": copy.deepcopy(before), "after": copy.deepcopy(after)})

    @staticmethod
    def public(message, full=False):
        result = copy.deepcopy(message)
        for key in ("mime_base64", "sender_copy", "envelope_recipients", "automatic", "deleted_from"):
            result.pop(key, None)
        if not message.get("sender_copy", False):
            result["bcc"] = []
            if "headers" in result:
                result["headers"] = {k: v for k, v in result["headers"].items() if k.casefold() != "bcc"}
        if not full:
            result.pop("body", None)
        for attachment in result.get("attachments", []):
            attachment.pop("content_base64", None)
        return result

    def allowed_path(self, path):
        candidate = Path(path)
        candidate = candidate if candidate.is_absolute() else self.workspace / candidate
        cursor = self.workspace
        for part in candidate.absolute().relative_to(self.workspace).parts:
            cursor = cursor / part
            if cursor.is_symlink() or (hasattr(cursor, "is_junction") and cursor.is_junction()) or (cursor.is_file() and cursor.stat().st_nlink > 1):
                raise ValueError("Links are not supported")
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self.workspace):
            raise ValueError("File must stay inside the workspace")
        return resolved

    download_path = allowed_path

    def snapshot(self, path, attachment_id=None):
        path = self.allowed_path(path)
        if path.stat().st_size > 25 * 1024 * 1024:
            raise ValueError("Attachment exceeds 25 MiB")
        raw = path.read_bytes()
        import mimetypes
        return {"id": attachment_id or identifier("attachment"), "name": path.name,
                "content_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                "content_base64": base64.b64encode(raw).decode("ascii")}

    def actor_address(self, s, actor=None):
        actor = actor or s["current_actor"]
        person = next((p for p in s["actors"] if p["id"] == actor), None)
        if person:
            addresses([person["email_address"]])
            return person["email_address"]
        owned = next((a for a in s["accounts"] if a["owner_id"] == actor), None)
        if not owned:
            raise ValueError("Actor has no registered sending address")
        return owned["email_address"]
