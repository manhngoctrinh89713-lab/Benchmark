"""Per-user conversation drafts and independent favorite content copies."""
import base64
import copy

from .common import ident, page, text, touch, version


class PersonalMixin:
    def get_draft(self, chat_id: str) -> dict:
        with self.state() as s:
            self.chat(s, chat_id)
            d = next((v for v in s["drafts"] if v["chat_id"] == chat_id and v["owner_id"] == s["current_user_id"]), None)
            return {"chat_id": chat_id, "draft": copy.deepcopy(d)}

    def save_draft(self, chat_id: str, content: str, quote_message_id: str | None = None,
                   mention_ids: list[str] | None = None, expected_version: int | None = None) -> dict:
        text(content, "content", True)
        with self.state(mutate=True) as s:
            c = self.chat(s, chat_id, True)
            if quote_message_id:
                self.message(s, quote_message_id, chat_id)
            mentions = list(dict.fromkeys(mention_ids or []))
            if mentions and (c["type"] != "group" or not set(mentions) <= set(c["member_ids"])):
                raise ValueError("Mentions require current group members")
            d = next((v for v in s["drafts"] if v["chat_id"] == chat_id and v["owner_id"] == s["current_user_id"]), None)
            version(d or {"version": 0}, expected_version)
            before = copy.deepcopy(d)
            if d is None:
                d = {"id": ident("draft"), "chat_id": chat_id, "owner_id": s["current_user_id"], "version": 0}
                s["drafts"].append(d)
            d.update(text=content, quote_message_id=quote_message_id, mention_ids=mentions)
            touch(d, s["now"])
            self.event(s, "save_draft", d["id"], before, d)
            return copy.deepcopy(d)

    def clear_draft(self, chat_id: str, expected_version: int | None = None) -> dict:
        with self.state(mutate=True) as s:
            self.chat(s, chat_id)
            d = next((v for v in s["drafts"] if v["chat_id"] == chat_id and v["owner_id"] == s["current_user_id"]), None)
            if d:
                version(d, expected_version)
                s["drafts"].remove(d)
                self.event(s, "clear_draft", d["id"], before=d)
            elif expected_version not in {None, 0}:
                raise ValueError("Draft no longer exists")
            return {"chat_id": chat_id, "cleared": d is not None}

    def send_draft(self, chat_id: str, expected_version: int | None = None) -> dict:
        with self.state(mutate=True) as s:
            d = next((v for v in s["drafts"] if v["chat_id"] == chat_id and v["owner_id"] == s["current_user_id"]), None)
            if d is None:
                raise ValueError("No draft in selected conversation")
            version(d, expected_version)
            text(d["text"])
            m = self._send(s, chat_id, d["text"], quote_message_id=d["quote_message_id"], mention_ids=d["mention_ids"])
            if m["status"] == "sent":
                s["drafts"].remove(d)
                self.event(s, "consume_draft", d["id"], before=d)
            return self.public(s, m)

    def _favorite(self, s, favorite_id):
        f = self.resource(s, "favorites", favorite_id)
        if f["owner_id"] != s["current_user_id"]:
            raise PermissionError("Favorite belongs to another user")
        return f

    def favorite_message(self, message_id: str, title: str = "", tags: list[str] | None = None) -> dict:
        text(title, "title", True)
        self._tags(tags or [])
        with self.state(mutate=True) as s:
            m = self.message(s, message_id)
            if m["kind"] == "system" or m["status"] != "sent":
                raise ValueError("This message cannot be saved as a favorite")
            for holder, a in self.content_attachments(m):
                self._attachment(s, holder, a["id"])
            f = {"id": ident("favorite"), "owner_id": s["current_user_id"], "title": title or m["text"][:80],
                 "tags": list(tags or []), "version": 1, "created_at": s["now"], "content": self._content_snapshot(m)}
            if m.get("quote"):
                f["content"]["quote"] = copy.deepcopy(self.public(s, m)["quote"])
            s["favorites"].append(f)
            self.event(s, "favorite_message", f["id"], after=f)
            return self._favorite_view(f)

    def _favorite_view(self, f):
        result = {k: copy.deepcopy(v) for k, v in f.items() if k != "content"}
        result["content"] = self.public_snapshot(f["content"])
        return result

    def list_favorites(self, query: str = "", tag: str | None = None,
                       offset: int = 0, limit: int = 20) -> dict:
        with self.state() as s:
            rows = [self._favorite_view(f) for f in reversed(s["favorites"]) if f["owner_id"] == s["current_user_id"]
                    and (tag is None or tag in f["tags"]) and query.casefold() in (f["title"]+"\n"+f["content"]["text"]).casefold()]
            return page(rows, offset, limit)

    def get_favorite(self, favorite_id: str, item_path: list[int] | None = None,
                     offset: int = 0, limit: int = 20) -> dict:
        with self.state() as s:
            f = self._favorite(s, favorite_id)
            result = self._favorite_view(f)
            if f["content"]["kind"] == "merged":
                content = self._merged_at(f["content"], item_path or [])
                result["items"] = page([self.public_snapshot(v) for v in content["payload"]["items"]], offset, limit)
            elif item_path:
                raise ValueError("item_path requires a merged favorite")
            return result

    @staticmethod
    def _tags(tags):
        if len(tags) > 30 or len(tags) != len(set(tags)):
            raise ValueError("At most 30 unique tags")
        for tag in tags:
            text(tag, "tag")

    def update_favorite(self, favorite_id: str, title: str | None = None,
                         tags: list[str] | None = None, expected_version: int | None = None) -> dict:
        if title is None and tags is None:
            raise ValueError("Specify title or tags")
        if title is not None:
            text(title, "title", True)
        if tags is not None:
            self._tags(tags)
        with self.state(mutate=True) as s:
            f = self._favorite(s, favorite_id)
            version(f, expected_version)
            before = copy.deepcopy(f)
            if title is not None:
                f["title"] = title
            if tags is not None:
                f["tags"] = tags
            touch(f, s["now"])
            self.event(s, "update_favorite", favorite_id, before, f)
            return self._favorite_view(f)

    def delete_favorite(self, favorite_id: str, expected_version: int | None = None) -> dict:
        with self.state(mutate=True) as s:
            f = self._favorite(s, favorite_id)
            version(f, expected_version)
            s["favorites"].remove(f)
            self.event(s, "delete_favorite", favorite_id, before=f)
            return {"deleted_id": favorite_id}

    def forward_favorite(self, favorite_id: str, target_chat_id: str) -> dict:
        with self.state(mutate=True) as s:
            f = self._favorite(s, favorite_id)
            content = f["content"]
            if content["kind"] == "audio":
                raise ValueError("Voice messages cannot be forwarded")
            return self.public(s, self._send(s, target_chat_id, content["text"], kind=content["kind"],
                                            attachments=content["attachments"], payload=content["payload"]))

    def download_favorite_attachment(self, favorite_id: str, attachment_id: str, save_path: str) -> dict:
        with self.state() as s:
            f = self._favorite(s, favorite_id)
            a = next((a for _, a in self.content_attachments(f["content"]) if a["id"] == attachment_id), None)
            if a is None:
                raise ValueError("Unknown favorite attachment")
            target = self.allowed_path(save_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(base64.b64decode(a["content_base64"], validate=True))
            return {"path": str(target), "size": a["size"], "sha256": a["sha256"]}
