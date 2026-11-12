"""Atomic state, per-user local history and actual message-recipient evidence."""
import base64
import copy
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import tempfile
from contextlib import contextmanager

from filelock import FileLock
from .common import date, ident, text


class ChatCore:
    def __init__(self, run_root):
        self.root = Path(run_root).resolve()
        self.workspace = self.root / "workspace"
        self.service = self.root / "services/chat"
        self.path = self.service / "state.json"
        self.service.mkdir(parents=True, exist_ok=True)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.lock = FileLock(str(self.service / "state.lock"), timeout=10)
        with self.lock:
            s = json.loads(self.path.read_text(encoding="utf-8-sig"))
            self.normalize(s)
            self.validate(s)
            self.atomic_json(self.path, s)

    @staticmethod
    def normalize(s):
        if s.get("model_version") not in {2, 3}:
            raise ValueError("Chat model_version 2 or 3 required")
        old = s["model_version"] == 2
        s.setdefault("recall_window_seconds", 120)
        s.setdefault("sequence", 0)
        for key in ("relations", "friend_requests", "invitations", "drafts", "favorites", "events", "delivery_events", "member_events"):
            s.setdefault(key, [])
        for u in s["contacts"]:
            u.setdefault("version", 1)
            if old and u["id"] != s["current_user_id"] and not any(r["owner_id"] == s["current_user_id"] and r["user_id"] == u["id"] for r in s["relations"]):
                s["relations"].append({"owner_id": s["current_user_id"], "user_id": u["id"], "is_friend": True,
                                       "blocked": False, "remark": u.get("remark", ""), "tags": [], "version": 1})
                if not any(r["owner_id"] == u["id"] and r["user_id"] == s["current_user_id"] for r in s["relations"]):
                    s["relations"].append({"owner_id": u["id"], "user_id": s["current_user_id"], "is_friend": True,
                                           "blocked": False, "remark": "", "tags": [], "version": 1})
        for c in s["chats"]:
            for key, value in {"version": 1, "admin_ids": [], "dissolved": False, "invite_requires_approval": False,
                               "announcement": None, "pinned_message_ids": [], "member_nicknames": {}, "user_settings": {}}.items():
                c.setdefault(key, value)
            c.setdefault("membership", [{"user_id": uid, "joined_at": None, "left_at": None} for uid in c["member_ids"]])
        for m in s["messages"]:
            c = next(c for c in s["chats"] if c["id"] == m["chat_id"])
            for key, value in {"read_by": [], "hidden_by": [], "recalled": False, "attachments": [], "quote_message_id": None,
                               "mention_ids": [], "version": 1, "kind": "text", "status": "sent", "forwardable": True}.items():
                m.setdefault(key, value)
            if m["attachments"] and m["kind"] == "text":
                m["kind"] = "file"
            m.setdefault("recipient_ids", list(c["member_ids"]))
            m.setdefault("sequence", 0)
            sender = next(u for u in s["contacts"] if u["id"] == m["sender_id"])
            m.setdefault("sender_name", c["member_nicknames"].get(m["sender_id"]) or sender["name"])
            def normalize_content(content, depth=0):
                if depth > 3:
                    raise ValueError("Merged records exceed nesting limit 3")
                for a in content.get("attachments", []):
                    a.setdefault("content_type", mimetypes.guess_type(a["name"])[0] or "application/octet-stream")
                    a.setdefault("available", True)
                    a.setdefault("downloaded_by", [])
                if content.get("kind") == "merged" and content.get("payload"):
                    for item in content["payload"]["items"]:
                        normalize_content(item, depth+1)
            normalize_content(m)
        for m in s["messages"]:
            if m.get("quote_message_id") and not m.get("quote"):
                parent = next((v for v in s["messages"] if v["id"] == m["quote_message_id"] and v["chat_id"] == m["chat_id"]), None)
                if parent:
                    m["quote"] = {"message_id": parent["id"], "sender_id": parent["sender_id"], "sender_name": parent["sender_name"],
                                  "kind": parent["kind"], "text": parent["text"], "attachment_names": [a["name"] for a in parent["attachments"]]}
        s["model_version"] = 3

    @staticmethod
    def validate(s):
        if s["model_version"] != 3:
            raise ValueError("Chat state must be normalized to version 3")
        date(s["now"])
        if type(s["recall_window_seconds"]) is not int or s["recall_window_seconds"] < 0:
            raise ValueError("Invalid recall window")
        for key in ("contacts", "chats", "messages", "friend_requests", "invitations", "drafts", "favorites"):
            values = [v["id"] for v in s[key]]
            if len(values) != len(set(values)) or any(not isinstance(v, str) or not v for v in values):
                raise ValueError("Invalid or duplicate " + key + " IDs")
        users = {u["id"] for u in s["contacts"]}
        if s["current_user_id"] not in users:
            raise ValueError("Unknown current user")
        relations = [(r["owner_id"], r["user_id"]) for r in s["relations"]]
        if len(relations) != len(set(relations)) or any(a not in users or b not in users or a == b for a, b in relations):
            raise ValueError("Invalid contact relations")
        chats = {c["id"]: c for c in s["chats"]}
        for c in chats.values():
            members = c["member_ids"]
            if c["type"] not in {"direct", "group"} or len(members) != len(set(members)) or not set(members) <= users:
                raise ValueError("Invalid chat membership")
            if c["type"] == "direct" and len(members) != 2:
                raise ValueError("Direct chat requires two participants")
            if c["type"] == "group" and not c["dissolved"] and c.get("owner_id") not in members:
                raise ValueError("Active group requires an owner")
            if not set(c["admin_ids"]) <= set(members):
                raise ValueError("Administrators must be members")
            for record in c["membership"]:
                if record["user_id"] not in users:
                    raise ValueError("Unknown membership user")
                if record["joined_at"]:
                    date(record["joined_at"])
                if record["left_at"]:
                    date(record["left_at"])
        for m in s["messages"]:
            if m["chat_id"] not in chats or m["sender_id"] not in users or not set(m["recipient_ids"]) <= users:
                raise ValueError("Invalid message participants")
            if date(m["timestamp"]) > date(s["now"]):
                raise ValueError("Message is later than environment time")
            text(m["text"], empty=True)
            if m["kind"] not in {"text", "file", "image", "audio", "video", "link", "contact", "location", "merged", "system"} or m["status"] not in {"sent", "failed"}:
                raise ValueError("Invalid message kind/status")
            if not set(m["recipient_ids"]) <= {v["user_id"] for v in chats[m["chat_id"]]["membership"]}:
                raise ValueError("Recipients require a membership record")
        for r in s["friend_requests"]:
            if r["from_id"] not in users or r["to_id"] not in users or r["status"] not in {"pending", "accepted", "rejected"}:
                raise ValueError("Invalid friend request")
        for r in s["invitations"]:
            if r["chat_id"] not in chats or r["user_id"] not in users or r["inviter_id"] not in users or r["status"] not in {"pending", "approved", "rejected", "expired"}:
                raise ValueError("Invalid group invitation")
        draft_keys = [(d["owner_id"], d["chat_id"]) for d in s["drafts"]]
        if len(draft_keys) != len(set(draft_keys)):
            raise ValueError("Each user can have only one draft per chat")
        for key in ("drafts", "favorites"):
            if any(v["owner_id"] not in users for v in s[key]):
                raise ValueError("Unknown owner in " + key)

    @staticmethod
    def atomic_json(path, data):
        fd, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)

    @contextmanager
    def state(self, mutate=False):
        with self.lock:
            s = json.loads(self.path.read_text(encoding="utf-8"))
            yield s
            if mutate:
                self.validate(s)
                self.atomic_json(self.path, s)

    @staticmethod
    def resource(s, collection, resource_id):
        obj = next((v for v in s[collection] if v["id"] == resource_id), None)
        if obj is None:
            raise ValueError("Unknown " + collection + " resource")
        return obj

    def user(self, s, uid):
        return self.resource(s, "contacts", uid)

    @staticmethod
    def relation(s, uid, owner=None):
        owner = owner or s["current_user_id"]
        return next((r for r in s["relations"] if r["owner_id"] == owner and r["user_id"] == uid), None)

    def ensure_relation(self, s, uid):
        self.user(s, uid)
        if uid == s["current_user_id"]:
            raise ValueError("Contact action requires another user")
        r = self.relation(s, uid)
        if r is None:
            r = {"owner_id": s["current_user_id"], "user_id": uid, "is_friend": False,
                 "blocked": False, "remark": "", "tags": [], "version": 1}
            s["relations"].append(r)
        return r

    @staticmethod
    def settings(s, chat):
        return chat["user_settings"].get(s["current_user_id"], {})

    def chat(self, s, cid, active=False):
        c = self.resource(s, "chats", cid)
        uid = s["current_user_id"]
        member = uid in c["member_ids"] and not c["dissolved"]
        historical = any(v["user_id"] == uid for v in c["membership"])
        if active and not member or not active and not (member or historical):
            raise PermissionError("Chat is not accessible for this operation")
        return c

    def privileged(self, s, cid, owner=False):
        c = self.chat(s, cid, True)
        if c["type"] != "group" or s["current_user_id"] not in ({c["owner_id"]} if owner else {c["owner_id"], *c["admin_ids"]}):
            raise PermissionError("Group owner" + ("" if owner else "/administrator") + " required")
        return c

    @staticmethod
    def visible(s, m):
        uid = s["current_user_id"]
        return uid in m["recipient_ids"] and uid not in m["hidden_by"]

    def message(self, s, mid, chat_id=None, allow_recalled=False):
        m = self.resource(s, "messages", mid)
        if not self.visible(s, m) or chat_id is not None and m["chat_id"] != chat_id:
            raise PermissionError("Message is not in local history")
        self.chat(s, m["chat_id"])
        if m["recalled"] and not allow_recalled:
            raise ValueError("Message has been recalled")
        return m

    @staticmethod
    def event(s, action, target=None, before=None, after=None, actor=None):
        s["sequence"] += 1
        s["events"].append({"id": ident("event"), "sequence": s["sequence"], "at": s["now"],
                            "actor_id": actor or s["current_user_id"], "action": action, "target": target,
                            "before": copy.deepcopy(before), "after": copy.deepcopy(after)})

    def public(self, s, m):
        result = copy.deepcopy(m)
        for key in ("recipient_ids", "hidden_by", "read_by", "forwarded_from", "delivery_results"):
            result.pop(key, None)
        for a in result.get("attachments", []):
            a.pop("content_base64", None)
            a["saved_locally"] = s["current_user_id"] in a.pop("downloaded_by", [])
            if a.get("expires_at") and date(s["now"]) >= date(a["expires_at"]):
                a["available"] = False
        if result.get("kind") == "merged" and result.get("payload"):
            result["payload"] = {"title": result["payload"]["title"], "count": len(result["payload"]["items"])}
        quote = result.get("quote")
        if quote and any(v["id"] == quote.get("message_id") and v["recalled"] for v in s["messages"]):
            result["quote"] = {"message_id": quote["message_id"], "recalled": True, "text": "引用的消息已撤回"}
        return result

    def allowed_path(self, value):
        p = Path(value)
        p = p if p.is_absolute() else self.workspace / p
        cursor = self.workspace
        for part in p.absolute().relative_to(self.workspace).parts:
            cursor /= part
            if cursor.is_symlink() or (hasattr(cursor, "is_junction") and cursor.is_junction()) or (cursor.is_file() and cursor.stat().st_nlink > 1):
                raise ValueError("Links are not supported")
        p = p.resolve()
        if not p.is_relative_to(self.workspace):
            raise ValueError("File must stay inside workspace")
        return p

    def snapshot(self, value):
        p = self.allowed_path(value)
        if p.stat().st_size > 25 * 1024 * 1024:
            raise ValueError("Attachment exceeds 25 MiB")
        raw = p.read_bytes()
        return {"id": ident("attachment"), "name": p.name, "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                "content_type": mimetypes.guess_type(p.name)[0] or "application/octet-stream",
                "content_base64": base64.b64encode(raw).decode("ascii"), "available": True, "downloaded_by": []}
