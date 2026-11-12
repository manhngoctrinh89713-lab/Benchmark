"""Message content, recipients, immutable forwarding and local record operations."""
import base64
import copy
from urllib.parse import urlsplit

from .common import date, ident, ids, page, text, touch

KINDS = {"text", "file", "image", "audio", "video", "link", "contact", "location", "merged", "system"}


class MessagesMixin:
    @staticmethod
    def ordered(messages):
        return sorted(messages, key=lambda m: (date(m["timestamp"]), m.get("sequence", 0), m["id"]))

    def list_messages(self, chat_id: str | None = None, query: str = "", sender_id: str | None = None,
                      since: str | None = None, before: str | None = None,
                      has_attachment: bool | None = None, unread: bool | None = None,
                      offset: int = 0, limit: int = 20, kind: str | None = None,
                      attachment_name: str | None = None, mentioned_user_id: str | None = None,
                      descending: bool = True) -> dict:
        lower, upper = date(since) if since else None, date(before) if before else None
        if lower and upper and lower >= upper or kind is not None and kind not in KINDS:
            raise ValueError("Invalid time range or kind")
        with self.state() as s:
            if chat_id:
                self.chat(s, chat_id)
            hits = []
            for m in s["messages"]:
                if not self.visible(s, m) or chat_id is not None and m["chat_id"] != chat_id:
                    continue
                if query.casefold() not in m["text"].casefold() or sender_id is not None and m["sender_id"] != sender_id:
                    continue
                if lower and date(m["timestamp"]) < lower or upper and date(m["timestamp"]) >= upper:
                    continue
                if has_attachment is not None and bool(m["attachments"]) != has_attachment or kind and m["kind"] != kind:
                    continue
                if attachment_name and not any(attachment_name.casefold() in a["name"].casefold() for a in m["attachments"]):
                    continue
                if mentioned_user_id and mentioned_user_id not in m["mention_ids"]:
                    continue
                is_unread = m["sender_id"] != s["current_user_id"] and s["current_user_id"] not in m["read_by"]
                if unread is not None and unread != is_unread:
                    continue
                hits.append(m)
            rows = self.ordered(hits)
            if descending:
                rows.reverse()
            return page([self.public(s, m) for m in rows], offset, limit)

    def read_message(self, message_id: str) -> dict:
        with self.state() as s:
            return self.public(s, self.message(s, message_id, allow_recalled=True))

    def get_message_context(self, message_id: str, before: int = 5, after: int = 5) -> dict:
        if not 0 <= before <= 50 or not 0 <= after <= 50:
            raise ValueError("before/after must be 0..50")
        with self.state() as s:
            m = self.message(s, message_id, allow_recalled=True)
            rows = self.ordered([v for v in s["messages"] if v["chat_id"] == m["chat_id"] and self.visible(s, v)])
            index = rows.index(m)
            return {"message": self.public(s, m), "before": [self.public(s, v) for v in rows[max(0,index-before):index]],
                    "after": [self.public(s, v) for v in rows[index+1:index+after+1]]}

    def _emit(self, s, c, kind, content="", attachments=None, quote=None, mentions=None,
              payload=None, forwarded_from=None, forwardable=True):
        uid = s["current_user_id"]
        recipients = list(c["member_ids"])
        status, failure = "sent", None
        if c["type"] == "direct" and kind != "system":
            target = next(v for v in recipients if v != uid)
            own, peer = self.relation(s, target), self.relation(s, uid, target)
            if not own or not own["is_friend"] or own["blocked"]:
                raise PermissionError("An unblocked friend is required for direct sending")
            if not peer or not peer["is_friend"] or peer["blocked"]:
                recipients, status, failure = [uid], "failed", "Message could not be delivered"
        m = {"id": ident("message"), "chat_id": c["id"], "sender_id": uid,
             "sender_name": c["member_nicknames"].get(uid) or self.user(s, uid)["name"], "text": content, "kind": kind,
             "timestamp": s["now"], "sequence": s["sequence"]+1, "version": 1,
             "quote_message_id": quote.get("message_id") if quote else None, "quote": copy.deepcopy(quote),
             "mention_ids": list(mentions or []), "attachments": copy.deepcopy(attachments or []),
             "recipient_ids": recipients, "read_by": [uid] if uid in recipients else [], "hidden_by": [], "recalled": False,
             "status": status, "forwardable": forwardable, "payload": copy.deepcopy(payload)}
        if failure:
            m["error"] = failure
        if forwarded_from:
            m["forwarded_from"] = copy.deepcopy(forwarded_from)
        s["messages"].append(m)
        for recipient in recipients:
            c["user_settings"].setdefault(recipient, {})["hidden"] = False
        self.event(s, "send_message" if kind != "system" else "group_notice", m["id"], after=m)
        # Record actual recipients and bytes; plain text paths do not transfer files.
        s["delivery_events"].append({"sequence": s["sequence"], "at": s["now"], "message": copy.deepcopy(m),
                                     "member_ids": [v for v in recipients if v != uid], "linked_files": [],
                                     "quoted_message": copy.deepcopy(quote), "status": status})
        return m

    def _send(self, s, chat_id, content, quote_message_id=None, attachments=None, mention_ids=None,
              mention_all=False, kind="text", payload=None, forwarded_from=None):
        c = self.chat(s, chat_id, True)
        mentions = list(dict.fromkeys(mention_ids or []))
        if mentions and (c["type"] != "group" or not set(mentions) <= set(c["member_ids"])):
            raise ValueError("Mentions require current group members")
        if mention_all:
            self.privileged(s, chat_id)
            mentions = [uid for uid in c["member_ids"] if uid != s["current_user_id"]]
        quote = None
        if quote_message_id:
            parent = self.message(s, quote_message_id, chat_id)
            quote = {"message_id": parent["id"], "sender_id": parent["sender_id"],
                     "sender_name": parent.get("sender_name", self.user(s, parent["sender_id"])["name"]),
                     "kind": parent["kind"], "text": parent["text"],
                     "attachment_names": [a["name"] for a in parent["attachments"]]}
        return self._emit(s, c, kind, content, attachments, quote, mentions, payload, forwarded_from)

    def send_message(self, chat_id: str, text: str, quote_message_id: str | None = None,
                     mention_ids: list[str] | None = None, mention_all: bool = False) -> dict:
        from .common import text as validate_text
        validate_text(text)
        with self.state(mutate=True) as s:
            return self.public(s, self._send(s, chat_id, text, quote_message_id=quote_message_id,
                                            mention_ids=mention_ids, mention_all=mention_all))

    def send_file(self, chat_id: str, file_path: str) -> dict:
        with self.state(mutate=True) as s:
            self.chat(s, chat_id, True)
            return self.public(s, self._send(s, chat_id, "", attachments=[self.snapshot(file_path)], kind="file"))

    def send_media(self, chat_id: str, file_path: str, kind: str) -> dict:
        if kind not in {"image", "audio", "video"}:
            raise ValueError("kind must be image/audio/video")
        with self.state(mutate=True) as s:
            self.chat(s, chat_id, True)
            attachment = self.snapshot(file_path)
            if not attachment["content_type"].startswith(kind + "/"):
                raise ValueError("File type does not match media kind")
            return self.public(s, self._send(s, chat_id, "", attachments=[attachment], kind=kind))

    def send_card(self, chat_id: str, kind: str, title: str = "", description: str = "",
                  url: str | None = None, user_id: str | None = None,
                  latitude: float | None = None, longitude: float | None = None) -> dict:
        text(title, "title", True)
        text(description, "description", True)
        if kind not in {"link", "contact", "location"}:
            raise ValueError("kind must be link/contact/location")
        with self.state(mutate=True) as s:
            self.chat(s, chat_id, True)
            if kind == "link":
                parsed = urlsplit(url or "")
                if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                    raise ValueError("Provide an http(s) URL without embedded credentials")
                if user_id is not None or latitude is not None or longitude is not None:
                    raise ValueError("Unexpected link card fields")
                payload = {"url": url, "title": title, "description": description}
            elif kind == "contact":
                if not user_id or url is not None or latitude is not None or longitude is not None:
                    raise ValueError("Contact card requires only user_id")
                profile = self.contact_view(s, user_id)
                payload = {k: profile[k] for k in ("id", "name", "wechat_id") if k in profile}
            else:
                if latitude is None or longitude is None or not -90 <= latitude <= 90 or not -180 <= longitude <= 180 or url is not None or user_id is not None:
                    raise ValueError("Provide valid latitude/longitude only")
                payload = {"latitude": latitude, "longitude": longitude, "title": title, "description": description}
            display = title or description or payload.get("name") or payload.get("url") or "位置"
            return self.public(s, self._send(s, chat_id, display, kind=kind, payload=payload))

    def get_send_status(self, message_id: str) -> dict:
        with self.state() as s:
            m = self.message(s, message_id, allow_recalled=True)
            if m["sender_id"] != s["current_user_id"]:
                raise PermissionError("Only your own send status is available")
            return {"message_id": message_id, "status": m["status"], "error": m.get("error"),
                    "accepted_at": m["timestamp"], "read_status": "unknown"}

    def _attachment(self, s, m, aid):
        a = next((a for a in m["attachments"] if a["id"] == aid), None)
        if a is None:
            raise ValueError("Unknown attachment")
        if s["current_user_id"] not in a["downloaded_by"] and (not a.get("available", True) or a.get("expires_at") and date(s["now"]) >= date(a["expires_at"])):
            raise ValueError("Attachment is no longer downloadable")
        return a

    def download_media(self, chat_id: str, message_id: str, attachment_id: str, save_path: str) -> dict:
        with self.state(mutate=True) as s:
            m = self.message(s, message_id, chat_id)
            holder = next((holder for holder, a in self.content_attachments(m) if a["id"] == attachment_id), None)
            if holder is None:
                raise ValueError("Unknown attachment")
            a = self._attachment(s, holder, attachment_id)
            target = self.allowed_path(save_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(base64.b64decode(a["content_base64"], validate=True))
            if s["current_user_id"] not in a["downloaded_by"]:
                a["downloaded_by"].append(s["current_user_id"])
            self.event(s, "download_media", message_id, after={"attachment_id": attachment_id, "sha256": a["sha256"]})
            return {"path": str(target), "size": a["size"], "sha256": a["sha256"]}

    def _forward_content(self, s, m):
        if not m.get("forwardable", True) or m["kind"] in {"audio", "system"} or m["status"] != "sent":
            raise ValueError("This message type cannot be forwarded")
        # A downloaded file belongs to the local copy; server expiry need not erase it.
        for holder, a in self.content_attachments(m):
            self._attachment(s, holder, a["id"])
        return self._content_snapshot(m)

    @staticmethod
    def content_attachments(content, depth=0):
        if depth > 3:
            raise ValueError("Merged records exceed nesting limit 3")
        for a in content.get("attachments", []):
            yield content, a
        if content.get("kind") == "merged" and content.get("payload"):
            for item in content["payload"]["items"]:
                yield from MessagesMixin.content_attachments(item, depth+1)

    def _content_snapshot(self, m):
        content = {k: copy.deepcopy(m.get(k)) for k in ("kind", "text", "attachments", "payload", "sender_id", "sender_name", "timestamp")}
        content["source_message_id"] = m["id"]
        for _, a in self.content_attachments(content):
            a.update(id=ident("attachment"), available=True, downloaded_by=[])
            a.pop("expires_at", None)
        return content

    def forward_message(self, source_chat_id: str, message_id: str, target_chat_id: str) -> dict:
        with self.state(mutate=True) as s:
            source = self.message(s, message_id, source_chat_id)
            content = self._forward_content(s, source)
            return self.public(s, self._send(s, target_chat_id, content["text"], attachments=content["attachments"],
                                            kind=content["kind"], payload=content["payload"],
                                            forwarded_from={"chat_id": source_chat_id, "message_id": message_id}))

    def forward_messages(self, source_chat_id: str, message_ids: list[str], target_chat_ids: list[str],
                         merged: bool = False, title: str = "聊天记录") -> dict:
        ids(message_ids)
        ids(target_chat_ids, 20)
        text(title, "title")
        with self.state(mutate=True) as s:
            selected = [self.message(s, mid, source_chat_id) for mid in message_ids]
            selected = self.ordered(selected)
            contents = [self._forward_content(s, m) for m in selected]
            if sum(a["size"] for item in contents for _, a in self.content_attachments(item, 1 if merged else 0)) > 50*1024*1024:
                raise ValueError("Selected attachments exceed 50 MiB")
            results = []
            for target in target_chat_ids:
                # Only target-specific failures are partial; invalid sources fail before sending.
                try:
                    self.chat(s, target, True)
                    if merged:
                        m = self._send(s, target, title, kind="merged", payload={"title": title, "items": contents})
                        results.append({"chat_id": target, "message_id": m["id"], "status": m["status"]})
                    else:
                        for item in contents:
                            m = self._send(s, target, item["text"], kind=item["kind"], attachments=item["attachments"], payload=item["payload"],
                                           forwarded_from={"chat_id": source_chat_id, "message_id": item["source_message_id"]})
                            results.append({"chat_id": target, "source_message_id": item["source_message_id"], "message_id": m["id"], "status": m["status"]})
                except (ValueError, PermissionError) as error:
                    results.append({"chat_id": target, "status": "failed", "error": str(error)})
            return {"results": results}

    def read_merged_messages(self, message_id: str, offset: int = 0, limit: int = 20,
                             item_path: list[int] | None = None) -> dict:
        with self.state() as s:
            m = self.message(s, message_id)
            if m["kind"] != "merged":
                raise ValueError("Merged message required")
            m = self._merged_at(m, item_path or [])
            rows = [self.public_snapshot(item) for item in m["payload"]["items"]]
            return {"title": m["payload"]["title"], **page(rows, offset, limit)}

    @staticmethod
    def _merged_at(content, path):
        if len(path) > 3:
            raise ValueError("Merged records exceed nesting limit 3")
        for index in path:
            if content.get("kind") != "merged" or type(index) is not int or not 0 <= index < len(content["payload"]["items"]):
                raise ValueError("Invalid merged item path")
            content = content["payload"]["items"][index]
        if content.get("kind") != "merged":
            raise ValueError("Path must select a merged record")
        return content

    def list_media(self, chat_id: str | None = None, query: str = "", offset: int = 0, limit: int = 20) -> dict:
        with self.state() as s:
            if chat_id is not None:
                self.chat(s, chat_id)
            rows = []
            for m in reversed(self.ordered(s["messages"])):
                if not self.visible(s, m) or m["recalled"] or chat_id is not None and m["chat_id"] != chat_id:
                    continue
                for _, a in self.content_attachments(m):
                    if query.casefold() in a["name"].casefold():
                        item = copy.deepcopy(a)
                        item.pop("content_base64", None)
                        item["saved_locally"] = s["current_user_id"] in item.pop("downloaded_by", [])
                        if item.get("expires_at") and date(s["now"]) >= date(item["expires_at"]):
                            item["available"] = False
                        rows.append({"message_id": m["id"], "chat_id": m["chat_id"], "timestamp": m["timestamp"], **item})
            return page(rows, offset, limit)

    @staticmethod
    def public_snapshot(item):
        result = copy.deepcopy(item)
        for a in result.get("attachments", []):
            a.pop("content_base64", None)
            a.pop("downloaded_by", None)
        if result.get("kind") == "merged":
            result["payload"] = {"title": result["payload"]["title"], "count": len(result["payload"]["items"])}
        return result

    def delete_message(self, chat_id: str, message_id: str) -> dict:
        return self.delete_messages(chat_id, [message_id])

    def delete_messages(self, chat_id: str, message_ids: list[str]) -> dict:
        ids(message_ids, 500)
        with self.state(mutate=True) as s:
            self.chat(s, chat_id)
            results = []
            for mid in message_ids:
                try:
                    m = self.message(s, mid, chat_id, True)
                    m["hidden_by"].append(s["current_user_id"])
                    self.event(s, "delete_local_message", mid, after={"user_id": s["current_user_id"]})
                    results.append({"message_id": mid, "success": True})
                except (ValueError, PermissionError) as error:
                    results.append({"message_id": mid, "success": False, "error": str(error)})
            return {"scope": "local_only", "results": results}

    def clear_chat_history(self, chat_id: str) -> dict:
        with self.state(mutate=True) as s:
            c = self.chat(s, chat_id)
            mids = []
            for m in s["messages"]:
                if m["chat_id"] == chat_id and self.visible(s, m):
                    m["hidden_by"].append(s["current_user_id"])
                    mids.append(m["id"])
            c["user_settings"].setdefault(s["current_user_id"], {})["manual_unread"] = False
            self.event(s, "clear_local_history", chat_id, after={"message_ids": mids})
            return {"chat_id": chat_id, "cleared": len(mids), "scope": "local_only"}

    def recall_message(self, chat_id: str, message_id: str) -> dict:
        with self.state(mutate=True) as s:
            self.chat(s, chat_id, True)
            m = self.message(s, message_id, chat_id)
            if m["sender_id"] != s["current_user_id"] or m["kind"] == "system" or m["status"] != "sent":
                raise PermissionError("Only your own successfully sent messages can be recalled")
            if (date(s["now"])-date(m["timestamp"])).total_seconds() > s["recall_window_seconds"]:
                raise ValueError("Recall window expired")
            before = copy.deepcopy(m)
            m.update(text="", attachments=[], payload=None, quote=None, quote_message_id=None, mention_ids=[],
                     recalled=True, recalled_at=s["now"], notice="消息已撤回")
            touch(m, s["now"])
            self.event(s, "recall_message", message_id, before, m)
            return self.public(s, m)

    def mark_read(self, chat_id: str) -> dict:
        with self.state(mutate=True) as s:
            c = self.chat(s, chat_id)
            count = 0
            for m in s["messages"]:
                if m["chat_id"] == chat_id and self.visible(s, m) and s["current_user_id"] not in m["read_by"]:
                    m["read_by"].append(s["current_user_id"])
                    count += 1
            c["user_settings"].setdefault(s["current_user_id"], {})["manual_unread"] = False
            self.event(s, "mark_read", chat_id, after={"updated": count})
            return {"updated": count, "scope": "local_only"}
