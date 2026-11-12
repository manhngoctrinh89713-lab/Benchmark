"""Reading, conversation views and mailbox organization."""
import base64
import copy
from email import policy
from email.parser import BytesParser

from .common import check_version, date, field_value, identifier, matches, page, text, touch, validate_filters
from .core import SYSTEM_FOLDERS
from .types import Condition


class MessagesMixin:
    def list_accounts(self) -> list[dict]:
        with self.state() as s:
            return [{"account_name": a["account_name"], "email_address": a["email_address"],
                     "aliases": a["aliases"], "permissions": sorted(self.permissions(s, a))}
                    for a in s["accounts"] if self.permissions(s, a)]

    def get_account(self, account_name: str) -> dict:
        with self.state() as s:
            a = self.account(s, account_name)
            permissions = self.permissions(s, a)
            if not permissions:
                raise PermissionError("Mailbox permission denied")
            return {k: copy.deepcopy(a[k]) for k in ("account_name", "email_address", "aliases", "owner_id", "version")} | {
                "actor_id": s["current_actor"], "permissions": sorted(permissions)}

    def list_mailboxes(self, account_name: str) -> list[dict]:
        with self.state() as s:
            a = self.require(s, account_name)
            return [{**f, "count": sum(m["account_name"] == account_name and m["mailbox"] == f["path"] for m in s["messages"])
                                  + (sum(d["account_name"] == account_name for d in s["drafts"]) if f["path"] == "Drafts" else 0),
                     "unread_count": sum(m["account_name"] == account_name and m["mailbox"] == f["path"] and not m["is_read"] for m in s["messages"])}
                    for f in a["folders"]]

    def search_emails(self, account_name: str, query: str = "", mailbox: str | None = None,
                      sender: str | None = None, recipient: str | None = None,
                      since: str | None = None, before: str | None = None,
                      unread: bool | None = None, has_attachment: bool | None = None,
                      offset: int = 0, limit: int = 20, subject: str | None = None,
                      body: str | None = None, to: str | None = None, cc: str | None = None,
                      starred: bool | None = None, categories: list[str] | None = None,
                      attachment_name: str | None = None, min_size: int | None = None,
                      max_size: int | None = None, thread_id: str | None = None,
                      filters: list[Condition] | None = None, match: str = "all",
                      sort_by: str = "timestamp", descending: bool = True) -> dict:
        conditions = list(filters or [])
        validate_filters(conditions)
        if match not in {"all", "any"} or sort_by not in {"timestamp", "subject", "size", "from"}:
            raise ValueError("Invalid match or sort_by")
        if since and before and date(since) >= date(before):
            raise ValueError("since must precede before")
        if min_size is not None and min_size < 0 or max_size is not None and max_size < 0:
            raise ValueError("Sizes must be nonnegative")
        with self.state() as s:
            a = self.require(s, account_name)
            folder_path = self.folder(a, mailbox)["path"] if mailbox is not None else None
            hits = []
            for raw in s["messages"]:
                if raw["account_name"] != account_name:
                    continue
                m = self.public(raw, full=True)
                if folder_path is not None and m["mailbox"] != folder_path:
                    continue
                if query.casefold() not in (m["subject"] + "\n" + m["body"]).casefold():
                    continue
                if sender and sender.casefold() != m["from"].casefold():
                    continue
                if recipient and recipient.casefold() not in [r.casefold() for r in m["to"] + m["cc"] + m["bcc"]]:
                    continue
                if since and date(m["timestamp"]) < date(since) or before and date(m["timestamp"]) >= date(before):
                    continue
                if unread is not None and m["is_read"] == unread or has_attachment is not None and bool(m["attachments"]) != has_attachment:
                    continue
                if starred is not None and m["starred"] != starred:
                    continue
                if any(value is not None and value.casefold() not in m[field].casefold() for field, value in (("subject", subject), ("body", body))):
                    continue
                if any(value is not None and value.casefold() not in [v.casefold() for v in m[field]] for field, value in (("to", to), ("cc", cc))):
                    continue
                if categories and not set(categories) <= set(m["categories"]):
                    continue
                if thread_id and m["thread_id"] != thread_id:
                    continue
                size = field_value(m, "size")
                if min_size is not None and size < min_size or max_size is not None and size > max_size:
                    continue
                if attachment_name and not any(attachment_name.casefold() in v["name"].casefold() for v in m["attachments"]):
                    continue
                if matches(m, conditions, match):
                    hits.append(raw)
            def order(m):
                value = date(m["timestamp"]) if sort_by == "timestamp" else field_value(m, sort_by)
                return value, m["id"]
            hits.sort(key=order, reverse=descending)
            return page([self.public(m) for m in hits], offset, limit)

    def read_email(self, account_name: str, email_id: str) -> dict:
        with self.state() as s:
            return self.public(self.message(s, account_name, email_id), full=True)

    def list_threads(self, account_name: str, query: str = "", offset: int = 0, limit: int = 20) -> dict:
        with self.state() as s:
            self.require(s, account_name)
            grouped = {}
            for m in s["messages"]:
                if m["account_name"] == account_name:
                    grouped.setdefault(m["thread_id"], []).append(m)
            rows = []
            for thread_id, messages in grouped.items():
                if query.casefold() not in "\n".join(m["subject"] + "\n" + m["body"] for m in messages).casefold():
                    continue
                latest = max(messages, key=lambda m: date(m["timestamp"]))
                rows.append({"id": thread_id, "subject": latest["subject"], "message_count": len(messages),
                             "last_at": latest["timestamp"], "unread_count": sum(not m["is_read"] for m in messages)})
            rows.sort(key=lambda row: (date(row["last_at"]), row["id"]), reverse=True)
            return page(rows, offset, limit)

    def read_thread(self, account_name: str, thread_id: str, offset: int = 0, limit: int = 20) -> dict:
        with self.state() as s:
            self.require(s, account_name)
            rows = [self.public(m, True) for m in s["messages"] if m["account_name"] == account_name and m["thread_id"] == thread_id]
            if not rows:
                raise ValueError("Unknown thread")
            rows.sort(key=lambda m: (date(m["timestamp"]), m["id"]))
            result = page(rows, offset, limit)
            result["participants"] = sorted({address for m in rows for address in [m["from"], *m["to"], *m["cc"]]})
            return result

    def update_threads(self, account_name: str, thread_ids: list[str], mailbox: str | None = None,
                       is_read: bool | None = None, starred: bool | None = None,
                       add_categories: list[str] | None = None, remove_categories: list[str] | None = None) -> dict:
        """Apply organization changes to the current message membership snapshot."""
        with self.state() as s:
            self.require(s, account_name, "write")
            if not thread_ids or len(thread_ids) > 100 or len(set(thread_ids)) != len(thread_ids):
                raise ValueError("Provide 1..100 unique thread IDs")
            members = {tid: [m["id"] for m in s["messages"] if m["account_name"] == account_name and m["thread_id"] == tid]
                       for tid in thread_ids}
            if any(not ids for ids in members.values()):
                raise ValueError("Unknown thread")
            ids = [mid for group in members.values() for mid in group]
        result = self.update_emails(account_name, ids, mailbox, is_read, starred, add_categories, remove_categories)
        return {"thread_members": members, **result}

    def list_attachments(self, account_name: str, email_id: str) -> list[dict]:
        with self.state() as s:
            return self.public(self.message(s, account_name, email_id), True)["attachments"]

    def download_attachment(self, account_name: str, email_id: str, attachment_id: str, save_path: str) -> dict:
        with self.state() as s:
            m = self.message(s, account_name, email_id)
            a = next((a for a in m["attachments"] if a["id"] == attachment_id), None)
            if a is None:
                raise ValueError("Unknown attachment")
            target = self.download_path(save_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(base64.b64decode(a["content_base64"], validate=True))
            return {"saved_path": str(target), "sha256": a["sha256"], "size": a["size"]}

    def export_email(self, account_name: str, email_id: str, save_path: str) -> dict:
        with self.state() as s:
            m = self.message(s, account_name, email_id)
            raw = self.mime_bytes(m)
            # Recipient exports never expose the sender's blind recipients.
            mime = BytesParser(policy=policy.SMTPUTF8).parsebytes(raw)
            if m["sender_copy"] and m.get("bcc"):
                mime["Bcc"] = ", ".join(m["bcc"])
            else:
                while "Bcc" in mime:
                    del mime["Bcc"]
            target = self.allowed_path(save_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(mime.as_bytes())
            return {"saved_path": str(target), "email_id": email_id}

    def _batch_messages(self, s, account_name, email_ids, operation):
        self.require(s, account_name, "write")
        if not email_ids or len(email_ids) > 500 or len(set(email_ids)) != len(email_ids):
            raise ValueError("Provide 1..500 unique email IDs")
        results = []
        for email_id in email_ids:
            # These operations change only the selected message, the message list,
            # and their evidence. Preserve those instead of copying the mailbox.
            previous_messages = list(s["messages"])
            index = next((i for i, m in enumerate(previous_messages)
                          if m["account_name"] == account_name and m["id"] == email_id), None)
            if index is not None:
                previous_messages[index] = copy.deepcopy(previous_messages[index])
            event_count, sequence = len(s["events"]), s["sequence"]
            try:
                m = self.message(s, account_name, email_id, "write")
                result = operation(m)
                results.append({"email_id": email_id, "success": True, **result})
            except (ValueError, PermissionError) as error:
                s["messages"] = previous_messages
                del s["events"][event_count:]
                s["sequence"] = sequence
                results.append({"email_id": email_id, "success": False, "error": str(error)})
        return {"results": results, "updated_ids": [r["email_id"] for r in results if r["success"]]}

    def update_emails(self, account_name: str, email_ids: list[str], mailbox: str | None = None,
                      is_read: bool | None = None, starred: bool | None = None,
                      add_categories: list[str] | None = None, remove_categories: list[str] | None = None) -> dict:
        if all(v is None for v in (mailbox, is_read, starred, add_categories, remove_categories)):
            raise ValueError("Specify an update")
        with self.state(mutate=True) as s:
            a = self.require(s, account_name, "write")
            destination = self.folder(a, mailbox)["path"] if mailbox is not None else None
            if add_categories and not set(add_categories) <= {c["id"] for c in a["categories"]}:
                raise ValueError("Unknown category")
            def update(m):
                before = copy.deepcopy(m)
                if destination is not None:
                    if destination == "Trash" and m["mailbox"] != "Trash":
                        m["deleted_from"] = m["mailbox"]
                        m["deleted_at"] = s["now"]
                    if destination != "Trash":
                        m.pop("deleted_at", None)
                        m.pop("deleted_from", None)
                    m["mailbox"] = destination
                for key, value in (("is_read", is_read), ("starred", starred)):
                    if value is not None:
                        m[key] = value
                m["categories"] = sorted((set(m["categories"]) | set(add_categories or [])) - set(remove_categories or []))
                touch(m, s["now"])
                self.event(s, "update_email", account_name, m["id"], before, m)
                return {"version": m["version"], "mailbox": m["mailbox"]}
            return self._batch_messages(s, account_name, email_ids, update)

    def copy_emails(self, account_name: str, email_ids: list[str], mailbox: str) -> dict:
        with self.state(mutate=True) as s:
            destination = self.folder(self.require(s, account_name, "write"), mailbox)["path"]
            def duplicate(m):
                copied = copy.deepcopy(m)
                copied.update(id=identifier("mail"), mailbox=destination, version=1, copied_from=m["id"])
                copied.pop("deleted_at", None)
                copied.pop("deleted_from", None)
                s["messages"].append(copied)
                self.event(s, "copy_email", account_name, copied["id"], after=copied)
                return {"copy_id": copied["id"]}
            return self._batch_messages(s, account_name, email_ids, duplicate)

    def delete_emails(self, account_name: str, email_ids: list[str], permanent: bool = False) -> dict:
        if not permanent:
            return self.update_emails(account_name, email_ids, mailbox="Trash")
        with self.state(mutate=True) as s:
            def remove(m):
                s["messages"].remove(m)
                self.event(s, "delete_email_permanently", account_name, m["id"], before=m)
                return {"permanent": True}
            return self._batch_messages(s, account_name, email_ids, remove)

    def restore_emails(self, account_name: str, email_ids: list[str], mailbox: str | None = None) -> dict:
        with self.state(mutate=True) as s:
            a = self.require(s, account_name, "write")
            override = self.folder(a, mailbox)["path"] if mailbox else None
            if override == "Trash":
                raise ValueError("Restore destination must be outside Trash")
            def restore(m):
                if m["mailbox"] != "Trash":
                    raise ValueError("Only trashed messages can be restored")
                before = copy.deepcopy(m)
                destination = override or m.get("deleted_from", "INBOX")
                m["mailbox"] = destination if destination in a["mailboxes"] else "INBOX"
                m.pop("deleted_at", None)
                m.pop("deleted_from", None)
                touch(m, s["now"])
                self.event(s, "restore_email", account_name, m["id"], before, m)
                return {"mailbox": m["mailbox"], "version": m["version"]}
            return self._batch_messages(s, account_name, email_ids, restore)

    def empty_mailbox(self, account_name: str, mailbox: str, permanent: bool = False) -> dict:
        with self.state() as s:
            a = self.require(s, account_name, "write")
            path = self.folder(a, mailbox)["path"]
            if path == "Trash" and not permanent:
                raise ValueError("Emptying Trash requires permanent=true")
            ids = [m["id"] for m in s["messages"] if m["account_name"] == account_name and m["mailbox"] == path]
        if not ids:
            return {"results": [], "updated_ids": []}
        if len(ids) > 500:
            raise ValueError("Folder exceeds 500 messages; use explicit batches")
        return self.delete_emails(account_name, ids, permanent)

    def create_mailbox(self, account_name: str, name: str, parent_id: str | None = None) -> dict:
        text(name, "name")
        if "/" in name or name in {".", ".."}:
            raise ValueError("Folder name must be a single component")
        with self.state(mutate=True) as s:
            a = self.require(s, account_name, "write")
            parent = self.folder(a, parent_id) if parent_id else None
            path = (parent["path"] + "/" if parent else "") + name
            if path in a["mailboxes"]:
                raise ValueError("Folder already exists")
            f = {"id": identifier("folder"), "name": name, "path": path,
                 "parent_id": parent["id"] if parent else None, "system": False, "version": 1}
            a["folders"].append(f)
            a["mailboxes"].append(path)
            self.event(s, "create_folder", account_name, f["id"], after=f)
            return copy.deepcopy(f)

    def update_mailbox(self, account_name: str, mailbox: str, name: str | None = None,
                       parent_id: str | None = None, move_to_root: bool = False,
                       expected_version: int | None = None) -> dict:
        with self.state(mutate=True) as s:
            a = self.require(s, account_name, "write")
            f = self.folder(a, mailbox)
            check_version(f, expected_version)
            if f["system"]:
                raise ValueError("System folders cannot be renamed or moved")
            if name is not None and (not name.strip() or "/" in name or name in {".", ".."}):
                raise ValueError("Invalid folder name")
            if parent_id and move_to_root:
                raise ValueError("Choose parent_id or move_to_root")
            old = f["path"]
            parent = None if move_to_root else self.folder(a, parent_id or f["parent_id"]) if parent_id or f["parent_id"] else None
            if parent and (parent["path"] == old or parent["path"].startswith(old + "/")):
                raise ValueError("Cannot move a folder inside itself")
            new = (parent["path"] + "/" if parent else "") + (name or f["name"])
            if new != old and new in a["mailboxes"]:
                raise ValueError("Destination exists")
            before = copy.deepcopy(f)
            mapping = {entry["path"]: new + entry["path"][len(old):] for entry in a["folders"]
                       if entry["path"] == old or entry["path"].startswith(old + "/")}
            for entry in a["folders"]:
                if entry["path"] in mapping:
                    entry["path"] = mapping[entry["path"]]
                    touch(entry, s["now"])
            f["name"], f["parent_id"] = name or f["name"], parent["id"] if parent else None
            a["mailboxes"] = [mapping.get(path, path) for path in a["mailboxes"]]
            for m in s["messages"]:
                if m["account_name"] == account_name:
                    changed = False
                    for field in ("mailbox", "deleted_from"):
                        if m.get(field) in mapping:
                            m[field] = mapping[m[field]]
                            changed = True
                    if changed:
                        touch(m, s["now"])
            self.event(s, "update_folder", account_name, f["id"], before, f)
            return copy.deepcopy(f)

    def delete_mailbox(self, account_name: str, mailbox: str, permanent: bool = False,
                       expected_version: int | None = None) -> dict:
        with self.state(mutate=True) as s:
            a = self.require(s, account_name, "write")
            f = self.folder(a, mailbox)
            check_version(f, expected_version)
            if f["system"]:
                raise ValueError("System folders cannot be deleted")
            subtree = [entry for entry in a["folders"] if entry["path"] == f["path"] or entry["path"].startswith(f["path"] + "/")]
            paths = {entry["path"] for entry in subtree}
            affected = [m for m in s["messages"] if m["account_name"] == account_name and m["mailbox"] in paths]
            for m in affected:
                before = copy.deepcopy(m)
                if permanent:
                    s["messages"].remove(m)
                else:
                    m.update(mailbox="Trash", deleted_from="INBOX", deleted_at=s["now"])
                    touch(m, s["now"])
                self.event(s, "delete_email_permanently" if permanent else "trash_email", account_name, m["id"], before, None if permanent else m)
            a["folders"] = [entry for entry in a["folders"] if entry["path"] not in paths]
            a["mailboxes"] = [path for path in a["mailboxes"] if path not in paths]
            self.event(s, "delete_folder_tree", account_name, f["id"], subtree, {"permanent": permanent})
            return {"deleted_folder_ids": [entry["id"] for entry in subtree], "affected_email_ids": [m["id"] for m in affected]}

    def list_categories(self, account_name: str) -> list[dict]:
        with self.state() as s:
            return copy.deepcopy(self.require(s, account_name)["categories"])

    def write_category(self, account_name: str, name: str, category_id: str | None = None,
                       color: str = "", expected_version: int | None = None) -> dict:
        text(name, "name")
        with self.state(mutate=True) as s:
            a = self.require(s, account_name, "write")
            if any(c["name"].casefold() == name.casefold() and c["id"] != category_id for c in a["categories"]):
                raise ValueError("Category name exists")
            c = next((c for c in a["categories"] if c["id"] == category_id), None)
            if category_id and c is None:
                raise ValueError("Unknown category")
            before = copy.deepcopy(c)
            if c is None:
                c = {"id": identifier("category"), "version": 1}
                a["categories"].append(c)
            else:
                check_version(c, expected_version)
                touch(c, s["now"])
            c.update(name=name, color=color)
            self.event(s, "write_category", account_name, c["id"], before, c)
            return copy.deepcopy(c)

    def delete_category(self, account_name: str, category_id: str, expected_version: int | None = None) -> dict:
        with self.state(mutate=True) as s:
            a = self.require(s, account_name, "write")
            c = next((c for c in a["categories"] if c["id"] == category_id), None)
            if c is None:
                raise ValueError("Unknown category")
            check_version(c, expected_version)
            a["categories"].remove(c)
            for m in s["messages"]:
                if m["account_name"] == account_name and category_id in m["categories"]:
                    m["categories"].remove(category_id)
                    touch(m, s["now"])
            self.event(s, "delete_category", account_name, category_id, before=c)
            return {"deleted_id": category_id, "messages_deleted": False}
