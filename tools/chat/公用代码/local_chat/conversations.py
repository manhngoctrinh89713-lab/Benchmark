"""Conversation preferences, group membership and fixed group roles."""
import copy

from .common import date, ident, ids, page, text, touch, version


class ConversationsMixin:
    @staticmethod
    def group_snapshot(c):
        return {k: copy.deepcopy(c.get(k)) for k in ("id", "type", "name", "owner_id", "admin_ids", "member_ids", "member_nicknames", "announcement", "pinned_message_ids", "version", "dissolved", "invite_requires_approval")}

    def chat_summary(self, s, c, include_last_message=True):
        uid = s["current_user_id"]
        settings = self.settings(s, c)
        active = uid in c["member_ids"] and not c["dissolved"]
        result = self.group_snapshot(c) if active else copy.deepcopy(settings.get("exit_snapshot", self.group_snapshot(c)))
        messages = self.ordered([m for m in s["messages"] if m["chat_id"] == c["id"] and self.visible(s, m)])
        result.update(current_user_id=uid, is_member=active, local_settings={k: v for k, v in settings.items() if k != "exit_snapshot"},
                      unread_count=sum(m["sender_id"] != uid and uid not in m["read_by"] for m in messages),
                      last_message_time=messages[-1]["timestamp"] if messages else None)
        if include_last_message:
            result["last_message"] = self.public(s, messages[-1]) if messages else None
        result["pinned_message_ids"] = [mid for mid in result.get("pinned_message_ids", [])
                                         if any(m["id"] == mid and self.visible(s, m) and not m["recalled"] for m in messages)]
        return result

    def list_chats(self, query: str | None = None, limit: int = 20, page: int = 0,
                   include_last_message: bool = True, sort_by: str = "last_active",
                   chat_type: str | None = None, unread_only: bool = False,
                   pinned: bool | None = None, muted: bool | None = None,
                   include_hidden: bool = False, active_only: bool = False) -> list[dict]:
        if type(page) is not int or page < 0 or not 1 <= limit <= 100 or sort_by not in {"last_active", "name"} or chat_type not in {None, "direct", "group"}:
            raise ValueError("Invalid pagination, sort or chat_type")
        with self.state() as s:
            rows = []
            for c in s["chats"]:
                if not any(v["user_id"] == s["current_user_id"] for v in c["membership"]):
                    continue
                settings = self.settings(s, c)
                if settings.get("hidden", False) and not include_hidden:
                    continue
                view = self.chat_summary(s, c, include_last_message)
                if active_only and not view["is_member"] or chat_type and c["type"] != chat_type:
                    continue
                if (query or "").casefold() not in (view["name"] + " " + c["id"]).casefold():
                    continue
                if unread_only and not (view["unread_count"] or settings.get("manual_unread")):
                    continue
                if pinned is not None and settings.get("pinned", False) != pinned or muted is not None and settings.get("muted", False) != muted:
                    continue
                rows.append(view)
            if sort_by == "name":
                rows.sort(key=lambda c: (not c["local_settings"].get("pinned", False), c["name"].casefold(), c["id"]))
            else:
                rows.sort(key=lambda c: (c["local_settings"].get("pinned", False), date(c["last_message_time"]).timestamp() if c["last_message_time"] else float("-inf"), c["id"]), reverse=True)
            return rows[page*limit:(page+1)*limit]

    def get_chat(self, chat_id: str, include_last_message: bool = True) -> dict:
        with self.state() as s:
            return self.chat_summary(s, self.chat(s, chat_id), include_last_message)

    def update_chat_settings(self, chat_id: str, pinned: bool | None = None,
                             muted: bool | None = None, hidden: bool | None = None,
                             manual_unread: bool | None = None) -> dict:
        values = {k: v for k, v in {"pinned": pinned, "muted": muted, "hidden": hidden, "manual_unread": manual_unread}.items() if v is not None}
        if not values:
            raise ValueError("Specify a setting")
        with self.state(mutate=True) as s:
            c = self.chat(s, chat_id)
            prefs = c["user_settings"].setdefault(s["current_user_id"], {})
            before = copy.deepcopy(prefs)
            prefs.update(values)
            self.event(s, "update_chat_settings", chat_id, before, prefs)
            return self.chat_summary(s, c)

    def create_chat(self, member_ids: list[str], name: str = "", chat_type: str = "group") -> dict:
        if chat_type not in {"direct", "group"}:
            raise ValueError("chat_type must be direct/group")
        text(name, "name", True)
        ids(member_ids)
        with self.state(mutate=True) as s:
            uid = s["current_user_id"]
            members = sorted(set(member_ids) | {uid})
            for mid in members:
                self.user(s, mid)
                if mid != uid:
                    r = self.relation(s, mid)
                    if not r or not r["is_friend"] or r["blocked"]:
                        raise PermissionError("Select unblocked friends")
            if chat_type == "direct":
                if len(members) != 2:
                    raise ValueError("Direct chat requires two users")
                existing = next((c for c in s["chats"] if c["type"] == "direct" and set(c["member_ids"]) == set(members)), None)
                if existing:
                    existing["user_settings"].setdefault(uid, {})["hidden"] = False
                    return self.chat_summary(s, existing)
            elif len(members) < 3:
                raise ValueError("Creating a group requires at least three users")
            c = {"id": ident("chat"), "name": name or "、".join(self.user(s, mid)["name"] for mid in members if mid != uid),
                 "type": chat_type, "owner_id": uid if chat_type == "group" else None, "admin_ids": [],
                 "member_ids": members, "membership": [{"user_id": mid, "joined_at": s["now"], "left_at": None} for mid in members],
                 "dissolved": False, "version": 1, "invite_requires_approval": False, "announcement": None,
                 "pinned_message_ids": [], "member_nicknames": {}, "user_settings": {}}
            s["chats"].append(c)
            self.event(s, "create_chat", c["id"], after=self.group_snapshot(c))
            if chat_type == "group":
                self._notice(s, c, "群聊已创建")
            return self.chat_summary(s, c)

    def _notice(self, s, c, content):
        return self._emit(s, c, "system", content, forwardable=False)

    def _join(self, s, c, members):
        added = sorted(set(members) - set(c["member_ids"]))
        if not added:
            return []
        for uid in added:
            c["member_ids"].append(uid)
            c["membership"].append({"user_id": uid, "joined_at": s["now"], "left_at": None})
            c["user_settings"].setdefault(uid, {}).pop("exit_snapshot", None)
            c["user_settings"][uid]["hidden"] = False
        for r in s["invitations"]:
            if r["chat_id"] == c["id"] and r["user_id"] in added and r["status"] == "pending":
                r["status"] = "approved"
                touch(r, s["now"])
                self.event(s, "complete_group_invitation", r["id"], after=r)
        touch(c, s["now"])
        self.event(s, "add_group_members", c["id"], after={"added": added, "member_ids": c["member_ids"]})
        s["member_events"].append({"sequence": s["sequence"], "at": s["now"], "chat_id": c["id"], "added": added,
                                   "member_ids": list(c["member_ids"]), "history_visibility": "since_join", "existing_message_ids": []})
        self._notice(s, c, "成员已加入：" + "、".join(self.user(s, uid)["name"] for uid in added))
        return added

    def _leave(self, s, c, members):
        before = self.group_snapshot(c)
        before["member_profiles"] = [{"id": uid, "name": self.user(s, uid)["name"]} for uid in c["member_ids"]]
        for uid in members:
            c["user_settings"].setdefault(uid, {})["exit_snapshot"] = copy.deepcopy(before)
            for record in c["membership"]:
                if record["user_id"] == uid and record["left_at"] is None:
                    record["left_at"] = s["now"]
        c["member_ids"] = [uid for uid in c["member_ids"] if uid not in members]
        c["admin_ids"] = [uid for uid in c["admin_ids"] if uid not in members]
        for r in s["invitations"]:
            if r["chat_id"] == c["id"] and r["inviter_id"] in members and r["status"] == "pending":
                r["status"] = "expired"
                touch(r, s["now"])
                self.event(s, "expire_group_invitation", r["id"], after=r)
        touch(c, s["now"])
        self.event(s, "remove_group_members", c["id"], before, self.group_snapshot(c))
        self._notice(s, c, "成员已离开：" + "、".join(self.user(s, uid)["name"] for uid in members))

    def update_chat_members(self, chat_id: str, member_ids: list[str], action: str) -> dict:
        ids(member_ids)
        if action not in {"add", "remove"}:
            raise ValueError("action must be add/remove")
        with self.state(mutate=True) as s:
            c = self.chat(s, chat_id, True)
            if c["type"] != "group":
                raise ValueError("Group required")
            pending = []
            if action == "add":
                for uid in member_ids:
                    self.user(s, uid)
                    if uid in c["member_ids"]:
                        continue
                    r = self.relation(s, uid)
                    if not r or not r["is_friend"] or r["blocked"]:
                        raise PermissionError("Invite unblocked friends")
                    if c["invite_requires_approval"] and s["current_user_id"] not in {c["owner_id"], *c["admin_ids"]}:
                        request = next((r for r in s["invitations"] if r["chat_id"] == chat_id and r["user_id"] == uid and r["status"] == "pending"), None)
                        if request is None:
                            request = {"id": ident("invitation"), "chat_id": chat_id, "user_id": uid,
                                       "inviter_id": s["current_user_id"], "status": "pending", "version": 1, "created_at": s["now"]}
                            s["invitations"].append(request)
                            self.event(s, "request_group_invitation", request["id"], after=request)
                        pending.append(request["id"])
                immediate = [uid for uid in member_ids if not any(r["id"] in pending and r["user_id"] == uid for r in s["invitations"])]
                self._join(s, c, immediate)
            else:
                self.privileged(s, chat_id)
                if not set(member_ids) <= set(c["member_ids"]):
                    raise ValueError("Selected users must be group members")
                if c["owner_id"] in member_ids or s["current_user_id"] in member_ids:
                    raise ValueError("Use leave_chat for yourself; transfer ownership first if needed")
                if s["current_user_id"] != c["owner_id"] and set(member_ids) & set(c["admin_ids"]):
                    raise PermissionError("Only owner can remove administrators")
                self._leave(s, c, member_ids)
            return {"chat": self.chat_summary(s, c), "pending_invitation_ids": pending}

    def list_group_invitations(self, chat_id: str, status: str | None = "pending",
                               offset: int = 0, limit: int = 20) -> dict:
        if status not in {None, "pending", "approved", "rejected", "expired"}:
            raise ValueError("Invalid invitation status")
        with self.state() as s:
            c = self.chat(s, chat_id, True)
            if c["type"] != "group":
                raise ValueError("Group required")
            privileged = s["current_user_id"] in {c["owner_id"], *c["admin_ids"]}
            return page([copy.deepcopy(r) for r in s["invitations"] if r["chat_id"] == chat_id and (privileged or r["inviter_id"] == s["current_user_id"])
                         and (status is None or r["status"] == status)], offset, limit)

    def respond_group_invitation(self, invitation_id: str, approve: bool,
                                 expected_version: int | None = None) -> dict:
        with self.state(mutate=True) as s:
            r = self.resource(s, "invitations", invitation_id)
            c = self.privileged(s, r["chat_id"])
            version(r, expected_version)
            if r["status"] != "pending":
                raise ValueError("Invitation is no longer pending")
            before = copy.deepcopy(r)
            if approve and r["inviter_id"] not in c["member_ids"]:
                raise ValueError("Inviter is no longer a member")
            r["status"] = "approved" if approve else "rejected"
            touch(r, s["now"])
            if approve:
                self._join(s, c, [r["user_id"]])
            self.event(s, "respond_group_invitation", invitation_id, before, r)
            return copy.deepcopy(r)

    def leave_chat(self, chat_id: str) -> dict:
        with self.state(mutate=True) as s:
            c = self.chat(s, chat_id, True)
            if c["type"] != "group":
                raise ValueError("Group required; hide a direct conversation instead")
            if c["owner_id"] == s["current_user_id"]:
                raise ValueError("Transfer ownership or dissolve the group first")
            self._leave(s, c, [s["current_user_id"]])
            return {"chat_id": chat_id, "is_member": False, "history_retained": True}

    def transfer_group_owner(self, chat_id: str, user_id: str,
                             expected_version: int | None = None) -> dict:
        with self.state(mutate=True) as s:
            c = self.privileged(s, chat_id, True)
            version(c, expected_version)
            if user_id not in c["member_ids"] or user_id == c["owner_id"]:
                raise ValueError("Choose another current member")
            before = self.group_snapshot(c)
            c["owner_id"] = user_id
            c["admin_ids"] = [uid for uid in c["admin_ids"] if uid != user_id]
            touch(c, s["now"])
            self.event(s, "transfer_group_owner", chat_id, before, self.group_snapshot(c))
            self._notice(s, c, "群主已转让给：" + self.user(s, user_id)["name"])
            return self.chat_summary(s, c)

    def list_chat_members(self, chat_id: str, query: str = "", role: str | None = None,
                          offset: int = 0, limit: int = 20) -> dict:
        if role not in {None, "owner", "administrator", "member"}:
            raise ValueError("Invalid role")
        with self.state() as s:
            c = self.chat(s, chat_id)
            view = self.chat_summary(s, c, False)
            profiles = {u["id"]: u for u in view.get("member_profiles", [])}
            rows = []
            for uid in view["member_ids"]:
                user_role = "owner" if uid == view.get("owner_id") else "administrator" if uid in view["admin_ids"] else "member"
                if role is not None and role != user_role:
                    continue
                nickname = view["member_nicknames"].get(uid, "")
                profile = {"id": uid, "name": self.user(s, uid)["name"]} if view["is_member"] else profiles.get(uid, {"id": uid})
                r = self.relation(s, uid)
                item = {**profile, "group_nickname": nickname, "remark": r.get("remark", "") if r else "", "role": user_role}
                if query.casefold() in " ".join(str(item.get(k, "")) for k in ("id", "name", "group_nickname", "remark")).casefold():
                    rows.append(item)
            return {"is_current_membership": view["is_member"], **page(rows, offset, limit)}

    def set_group_administrator(self, chat_id: str, user_id: str, administrator: bool,
                                expected_version: int | None = None) -> dict:
        with self.state(mutate=True) as s:
            c = self.privileged(s, chat_id, True)
            version(c, expected_version)
            if user_id not in c["member_ids"] or user_id == c["owner_id"]:
                raise ValueError("Choose a current nonowner member")
            before = self.group_snapshot(c)
            c["admin_ids"] = sorted((set(c["admin_ids"]) | {user_id}) if administrator else set(c["admin_ids"]) - {user_id})
            touch(c, s["now"])
            self.event(s, "set_group_administrator", chat_id, before, self.group_snapshot(c))
            self._notice(s, c, "群管理员已更新")
            return self.chat_summary(s, c)

    def dissolve_group(self, chat_id: str, expected_version: int | None = None) -> dict:
        with self.state(mutate=True) as s:
            c = self.privileged(s, chat_id, True)
            version(c, expected_version)
            self._notice(s, c, "群聊已解散")
            before = self.group_snapshot(c)
            c["dissolved"] = True
            touch(c, s["now"])
            for uid in c["member_ids"]:
                c["user_settings"].setdefault(uid, {})["exit_snapshot"] = self.group_snapshot(c)
                c["user_settings"][uid]["exit_snapshot"]["member_profiles"] = [{"id": mid, "name": self.user(s, mid)["name"]} for mid in c["member_ids"]]
            for record in c["membership"]:
                if record["left_at"] is None:
                    record["left_at"] = s["now"]
            for invitation in s["invitations"]:
                if invitation["chat_id"] == chat_id and invitation["status"] == "pending":
                    invitation["status"] = "expired"
                    touch(invitation, s["now"])
            self.event(s, "dissolve_group", chat_id, before, self.group_snapshot(c))
            return {"chat_id": chat_id, "dissolved": True, "history_retained": True}

    def update_group(self, chat_id: str, name: str | None = None,
                     invite_requires_approval: bool | None = None,
                     expected_version: int | None = None) -> dict:
        if name is None and invite_requires_approval is None:
            raise ValueError("Specify a group setting")
        if name is not None:
            text(name, "name")
        with self.state(mutate=True) as s:
            c = self.privileged(s, chat_id)
            version(c, expected_version)
            before = self.group_snapshot(c)
            if name is not None:
                c["name"] = name
            if invite_requires_approval is not None:
                c["invite_requires_approval"] = invite_requires_approval
            touch(c, s["now"])
            self.event(s, "update_group", chat_id, before, self.group_snapshot(c))
            self._notice(s, c, "群设置已更新" + ("：" + name if name is not None else ""))
            return self.chat_summary(s, c)

    def set_group_nickname(self, chat_id: str, nickname: str) -> dict:
        text(nickname, "nickname", True)
        with self.state(mutate=True) as s:
            c = self.chat(s, chat_id, True)
            if c["type"] != "group":
                raise ValueError("Group required")
            before = c["member_nicknames"].get(s["current_user_id"], "")
            c["member_nicknames"][s["current_user_id"]] = nickname
            touch(c, s["now"])
            self.event(s, "set_group_nickname", chat_id, before, nickname)
            return self.chat_summary(s, c)

    def get_group_announcement(self, chat_id: str) -> dict:
        with self.state() as s:
            c = self.chat(s, chat_id)
            view = self.chat_summary(s, c, False)
            if c["type"] != "group":
                raise ValueError("Group required")
            return {"chat_id": chat_id, "announcement": view["announcement"], "is_member": view["is_member"]}

    def set_group_announcement(self, chat_id: str, content: str | None,
                               expected_version: int | None = None) -> dict:
        if content is not None:
            text(content, "content")
        with self.state(mutate=True) as s:
            c = self.privileged(s, chat_id)
            current = c["announcement"]
            version(current or {"version": 0}, expected_version)
            # Keep a tombstone version so delete/recreate cannot reset concurrency.
            c["announcement"] = {"text": content, "deleted": content is None, "version": (current or {}).get("version", 0)+1,
                                 "author_id": s["current_user_id"], "updated_at": s["now"]}
            touch(c, s["now"])
            self.event(s, "set_group_announcement", chat_id, current, c["announcement"])
            self._notice(s, c, "群公告已删除" if content is None else "群公告：" + content)
            return copy.deepcopy(c["announcement"])

    def list_pinned_messages(self, chat_id: str) -> list[dict]:
        with self.state() as s:
            c = self.chat(s, chat_id)
            if c["type"] != "group":
                raise ValueError("Group required")
            mids = self.chat_summary(s, c, False)["pinned_message_ids"]
            return [self.public(s, self.message(s, mid, chat_id)) for mid in mids]

    def set_message_pinned(self, chat_id: str, message_id: str, pinned: bool,
                           expected_version: int | None = None) -> dict:
        with self.state(mutate=True) as s:
            c = self.privileged(s, chat_id)
            version(c, expected_version)
            self.message(s, message_id, chat_id)
            before = list(c["pinned_message_ids"])
            c["pinned_message_ids"] = list(dict.fromkeys(before + [message_id])) if pinned else [mid for mid in before if mid != message_id]
            touch(c, s["now"])
            self.event(s, "set_message_pinned", chat_id, before, c["pinned_message_ids"])
            self._notice(s, c, "群置顶消息已更新")
            return {"chat_id": chat_id, "pinned_message_ids": self.chat_summary(s, c, False)["pinned_message_ids"], "version": c["version"]}
