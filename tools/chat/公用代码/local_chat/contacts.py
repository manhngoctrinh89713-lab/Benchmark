"""Profiles, private contact annotations and friend-request lifecycle."""
import copy

from .common import ident, page, text, touch, version


class ContactsMixin:
    @staticmethod
    def known_users(s):
        uid = s["current_user_id"]
        known = {uid} | {r["user_id"] for r in s["relations"] if r["owner_id"] == uid}
        for request in s["friend_requests"]:
            if uid in {request["from_id"], request["to_id"]}:
                known.update({request["from_id"], request["to_id"]})
        for c in s["chats"]:
            if uid in c["member_ids"] and not c["dissolved"]:
                known.update(c["member_ids"])
        return known

    def contact_view(self, s, uid):
        if uid not in self.known_users(s):
            raise PermissionError("User profile is not visible")
        u = self.user(s, uid)
        result = {k: copy.deepcopy(u[k]) for k in ("id", "name", "wechat_id", "organization", "version") if k in u}
        r = self.relation(s, uid)
        if uid == s["current_user_id"] or r and r["is_friend"]:
            if "phone" in u:
                result["phone"] = u["phone"]
        result["relationship"] = copy.deepcopy(r) if r else {"is_friend": False, "blocked": False}
        return result

    def get_profile(self) -> dict:
        with self.state() as s:
            return copy.deepcopy(self.user(s, s["current_user_id"]))

    def update_profile(self, name: str | None = None, phone: str | None = None,
                       expected_version: int | None = None) -> dict:
        if name is None and phone is None:
            raise ValueError("Specify name or phone")
        if name is not None:
            text(name, "name")
        if phone is not None:
            text(phone, "phone", True)
        with self.state(mutate=True) as s:
            u = self.user(s, s["current_user_id"])
            version(u, expected_version)
            before = copy.deepcopy(u)
            if name is not None:
                u["name"] = name
            if phone is not None:
                u["phone"] = phone
            touch(u, s["now"])
            self.event(s, "update_profile", u["id"], before, u)
            return copy.deepcopy(u)

    def search_contacts(self, query: str = "", offset: int = 0, limit: int = 20,
                        friends_only: bool = True, tag: str | None = None,
                        blocked: bool | None = None) -> dict:
        with self.state() as s:
            rows = []
            for uid in sorted(self.known_users(s) - {s["current_user_id"]}):
                r = self.relation(s, uid)
                if friends_only and not (r and r["is_friend"]):
                    continue
                if tag is not None and (not r or tag not in r["tags"]):
                    continue
                if blocked is not None and bool(r and r["blocked"]) != blocked:
                    continue
                view = self.contact_view(s, uid)
                fields = [str(view.get(k, "")) for k in ("id", "name", "wechat_id", "phone", "organization")]
                fields.extend([r.get("remark", ""), *r.get("tags", [])] if r else [])
                if query.casefold() in " ".join(fields).casefold():
                    rows.append(view)
            return page(rows, offset, limit)

    def get_contact(self, user_id: str) -> dict:
        with self.state() as s:
            return self.contact_view(s, user_id)

    def update_contact(self, user_id: str, remark: str | None = None,
                       tags: list[str] | None = None, expected_version: int | None = None) -> dict:
        if remark is None and tags is None:
            raise ValueError("Specify remark or tags")
        if remark is not None:
            text(remark, "remark", True)
        if tags is not None:
            if len(tags) > 30 or len(set(tags)) != len(tags):
                raise ValueError("At most 30 unique tags")
            for tag in tags:
                text(tag, "tag")
        with self.state(mutate=True) as s:
            r = self.ensure_relation(s, user_id)
            if not r["is_friend"]:
                raise ValueError("Contact is not a friend")
            version(r, expected_version)
            before = copy.deepcopy(r)
            if remark is not None:
                r["remark"] = remark
            if tags is not None:
                r["tags"] = tags
            touch(r, s["now"])
            self.event(s, "update_contact", user_id, before, r)
            return self.contact_view(s, user_id)

    def delete_contact(self, user_id: str, expected_version: int | None = None) -> dict:
        with self.state(mutate=True) as s:
            r = self.ensure_relation(s, user_id)
            version(r, expected_version)
            before = copy.deepcopy(r)
            r["is_friend"] = False
            touch(r, s["now"])
            self.event(s, "delete_contact", user_id, before, r)
            return {"user_id": user_id, "is_friend": False, "history_retained": True}

    def set_contact_blocked(self, user_id: str, blocked: bool,
                            expected_version: int | None = None) -> dict:
        with self.state(mutate=True) as s:
            if user_id not in self.known_users(s):
                raise PermissionError("Unknown contact")
            r = self.ensure_relation(s, user_id)
            version(r, expected_version)
            before = copy.deepcopy(r)
            r["blocked"] = blocked
            touch(r, s["now"])
            self.event(s, "set_contact_blocked", user_id, before, r)
            return self.contact_view(s, user_id)

    def send_friend_request(self, user_id: str, message: str = "") -> dict:
        text(message, "message", True)
        with self.state(mutate=True) as s:
            self.user(s, user_id)
            if user_id == s["current_user_id"]:
                raise ValueError("Cannot request yourself")
            relation = self.relation(s, user_id)
            if relation and relation["is_friend"]:
                raise ValueError("Contact is already a friend")
            pending = next((r for r in s["friend_requests"] if r["from_id"] == s["current_user_id"] and r["to_id"] == user_id and r["status"] == "pending"), None)
            if pending:
                return copy.deepcopy(pending)
            r = {"id": ident("friend_request"), "from_id": s["current_user_id"], "to_id": user_id,
                 "message": message, "status": "pending", "created_at": s["now"], "version": 1}
            s["friend_requests"].append(r)
            self.event(s, "send_friend_request", r["id"], after=r)
            return copy.deepcopy(r)

    def list_friend_requests(self, direction: str = "incoming", status: str | None = "pending",
                             offset: int = 0, limit: int = 20) -> dict:
        if direction not in {"incoming", "outgoing"} or status not in {None, "pending", "accepted", "rejected"}:
            raise ValueError("Invalid direction or status")
        with self.state() as s:
            field = "to_id" if direction == "incoming" else "from_id"
            return page([copy.deepcopy(r) for r in s["friend_requests"] if r[field] == s["current_user_id"] and (status is None or r["status"] == status)], offset, limit)

    def respond_friend_request(self, request_id: str, accept: bool,
                               expected_version: int | None = None) -> dict:
        with self.state(mutate=True) as s:
            r = self.resource(s, "friend_requests", request_id)
            if r["to_id"] != s["current_user_id"] or r["status"] != "pending":
                raise PermissionError("Pending incoming request required")
            version(r, expected_version)
            before = copy.deepcopy(r)
            relation = self.ensure_relation(s, r["from_id"])
            if accept and relation["blocked"]:
                raise ValueError("Unblock the contact before accepting")
            r["status"] = "accepted" if accept else "rejected"
            touch(r, s["now"])
            if accept:
                relation["is_friend"] = True
                touch(relation, s["now"])
                reverse = self.relation(s, r["to_id"], r["from_id"])
                if reverse is None:
                    reverse = {"owner_id": r["from_id"], "user_id": r["to_id"], "blocked": False, "remark": "", "tags": [], "version": 1}
                    s["relations"].append(reverse)
                reverse["is_friend"] = True
                touch(reverse, s["now"])
            self.event(s, "respond_friend_request", request_id, before, r)
            return copy.deepcopy(r)
