"""Composition snapshots, submission, replies and scheduled messages."""
import base64
import copy
from email.message import EmailMessage
from email.policy import SMTPUTF8
from email.parser import BytesParser

from .common import addresses, check_version, date, identifier, page, text, touch, unique
from .types import DraftChanges


class ComposeMixin:
    def _prepare(self, s, account_name, recipients, subject, body, cc=None, bcc=None,
                 html=False, attachments=None, in_reply_to=None, reply_to=None,
                 from_address=None, send_mode="send_as", attachment_snapshots=None):
        self.account(s, account_name)
        text(subject, "subject", True)
        text(body, "body", True)
        if len(body.encode()) > 1024 * 1024 or any("\r" in h or "\n" in h for h in [subject, in_reply_to or ""]):
            raise ValueError("Body exceeds 1 MiB or invalid header")
        if send_mode not in {"send_as", "send_on_behalf"}:
            raise ValueError("Invalid send_mode")
        if type(html) is not bool:
            raise ValueError("html must be boolean")
        to = self._resolve_recipients(s, recipients or [])
        cc = [v for v in self._resolve_recipients(s, cc or []) if v.casefold() not in {x.casefold() for x in to}]
        bcc = [v for v in self._resolve_recipients(s, bcc or []) if v.casefold() not in {x.casefold() for x in to + cc}]
        if len(to + cc + bcc) > 500:
            raise ValueError("At most 500 recipients")
        account = self.account(s, account_name)
        sender = from_address or account["email_address"]
        addresses([sender])
        if sender.casefold() not in {v.casefold() for v in [account["email_address"], *account["aliases"]]}:
            raise ValueError("from_address is not an identity of the selected account")
        parent = None
        if in_reply_to:
            self.require(s, account_name, "read")
            parent = next((m for m in s["messages"] if m["account_name"] == account_name and m["message_id"] == in_reply_to), None)
            if parent is None:
                raise ValueError("Reply parent Message-ID not found in selected account")
        snapshots = copy.deepcopy(attachment_snapshots or [])
        snapshots += [self.snapshot(p) for p in attachments or []]
        if len(snapshots) > 20 or sum(a["size"] for a in snapshots) > 50 * 1024 * 1024:
            raise ValueError("At most 20 attachments and 50 MiB total")
        return {"account_name": account_name, "to": to, "cc": cc, "bcc": bcc,
                "subject": subject, "body": body, "html": html, "from": sender,
                "reply_to": addresses(reply_to or []), "send_mode": send_mode,
                "attachments": snapshots, "in_reply_to": in_reply_to,
                "references": unique([*(parent.get("references", []) if parent else []), *([in_reply_to] if in_reply_to else [])]),
                "thread_id": parent["thread_id"] if parent else identifier("thread"), "sender_copy": True}

    @staticmethod
    def mime_bytes(message):
        mime = EmailMessage(policy=SMTPUTF8)
        for key, value in (("From", message["from"]), ("To", ", ".join(message["to"])),
                           ("Subject", message["subject"]), ("Date", date(message["timestamp"]))):
            mime[key] = value
        if message.get("message_id"):
            mime["Message-ID"] = message["message_id"]
        for key, field in (("Cc", "cc"), ("Reply-To", "reply_to"), ("References", "references")):
            if message.get(field):
                mime[key] = " ".join(message[field]) if field == "references" else ", ".join(message[field])
        if message.get("sender") and message["sender"] != message["from"]:
            mime["Sender"] = message["sender"]
        if message.get("in_reply_to"):
            mime["In-Reply-To"] = message["in_reply_to"]
        if message.get("automatic"):
            mime["Auto-Submitted"] = "auto-generated"
        managed = {"from", "to", "cc", "bcc", "subject", "date", "message-id", "sender", "reply-to",
                   "references", "in-reply-to", "mime-version", "content-type", "content-transfer-encoding"}
        if message.get("automatic"):
            managed.add("auto-submitted")
        for key, value in message.get("headers", {}).items():
            if key.casefold() not in managed:
                mime[key] = value
        mime.set_content(message["body"], subtype="html" if message.get("html") else "plain")
        for attachment in message["attachments"]:
            raw = base64.b64decode(attachment["content_base64"], validate=True)
            content_type = attachment.get("content_type", "application/octet-stream")
            if content_type == "message/rfc822":
                mime.add_attachment(BytesParser(policy=SMTPUTF8).parsebytes(raw), filename=attachment["name"])
            else:
                main, sub = content_type.split("/", 1)
                mime.add_attachment(raw, maintype=main, subtype=sub, filename=attachment["name"])
        return mime.as_bytes()

    def _submit(self, s, prepared, actor=None, automatic=False):
        if not prepared["to"] + prepared["cc"] + prepared["bcc"]:
            raise ValueError("Sending requires at least one recipient")
        actor = actor or s["current_actor"]
        a = self.require(s, prepared["account_name"], prepared["send_mode"], actor=actor)
        if prepared["from"].casefold() not in {v.casefold() for v in [a["email_address"], *a["aliases"]]}:
            raise PermissionError("Sending identity is no longer available")
        message = copy.deepcopy(prepared)
        message.update(id=identifier("mail"), message_id="<" + identifier("message") + "@mail.local>",
                       timestamp=s["now"], mailbox="Sent", is_read=True, starred=False,
                       categories=[], version=1, importance="normal", automatic=automatic,
                       sender=prepared["from"] if prepared["send_mode"] == "send_as" else self.actor_address(s, actor))
        envelope = []
        origins = {}
        for address in prepared["to"] + prepared["cc"] + prepared["bcc"]:
            group = next((g for g in s["groups"] if g.get("kind", "organization") == "organization"
                          and g.get("email_address", "").casefold() == address.casefold()), None)
            if group:
                members = addresses(group.get("members", []))
                known_groups = {g.get("email_address", "").casefold() for g in s["groups"]}
                if any(v.casefold() in known_groups for v in members):
                    raise ValueError("Nested organization groups are unsupported")
                envelope.extend(members)
                for member in members:
                    origins.setdefault(member.casefold(), []).append({"id": group["id"], "address": address,
                                                                      "members_visible_to": copy.deepcopy(group.get("members_visible_to")),
                                                                      "visible_to": copy.deepcopy(group.get("visible_to"))})
            else:
                envelope.append(address)
        envelope = unique(envelope)
        if not envelope or len(envelope) > 500:
            raise ValueError("Expanded recipients must contain 1..500 addresses")
        message["envelope_recipients"] = envelope
        message["mime_base64"] = base64.b64encode(self.mime_bytes(message)).decode("ascii")
        s["messages"].append(message)
        submission = {"id": identifier("submission"), "account_name": a["account_name"],
                      "email_id": message["id"], "message_id": message["message_id"],
                      "actor_id": actor, "status": "accepted", "submitted_at": s["now"],
                      "recipient_results": [], "version": 1}
        s["submissions"].append(submission)
        submission_id = submission["id"]
        self.event(s, "submit_email", a["account_name"], message["id"], after=message, actor=actor)
        s["sent_events"].append({"sequence": s["sequence"], "at": s["now"], "message": copy.deepcopy(message)})
        delivered_mailboxes = {}
        for address in envelope:
            submission = self.resource(s, "submissions", submission_id)
            routing = {"groups": origins.get(address.casefold(), [])}
            target = next((account for account in s["accounts"] if address.casefold() in
                           {v.casefold() for v in [account["email_address"], *account["aliases"]]}), None)
            if target:
                if target["account_name"] in delivered_mailboxes:
                    submission["recipient_results"].append({"address": address, "status": "delivered", "at": s["now"], **routing})
                    s["delivery_events"].append({"submission_id": submission_id, "address": address,
                                                  "email_id": delivered_mailboxes[target["account_name"]],
                                                  "status": "delivered", "at": s["now"]})
                    continue
                received = copy.deepcopy(message)
                received.update(id=identifier("mail"), account_name=target["account_name"], mailbox="INBOX",
                                sender_copy=False, bcc=[], is_read=False)
                received.pop("envelope_recipients", None)
                # Threads belong to the receiving mailbox, related through References.
                related = next((m for m in s["messages"] if m["account_name"] == target["account_name"]
                                and m["message_id"] in received["references"]), None)
                received["thread_id"] = related["thread_id"] if related else identifier("thread")
                s["messages"].append(received)
                delivered_mailboxes[target["account_name"]] = received["id"]
                self.event(s, "receive_email", target["account_name"], received["id"], after=received, actor="mail-system")
                submission["recipient_results"].append({"address": address, "status": "delivered", "at": s["now"], **routing})
                s["delivery_events"].append({"submission_id": submission["id"], "address": address,
                                              "email_id": received["id"], "status": "delivered", "at": s["now"]})
                self._apply_incoming(s, received, automated=automatic)
            else:
                submission["recipient_results"].append({"address": address, "status": "unknown", **routing})
        submission = self.resource(s, "submissions", submission_id)
        if all(r["status"] == "delivered" for r in submission["recipient_results"]):
            submission["status"] = "delivered"
        return {"email_id": message["id"], "message_id": message["message_id"],
                "submission_id": submission_id, "status": submission["status"]}

    def send_email(self, account_name: str, recipients: list[str], subject: str, body: str,
                   cc: list[str] | None = None, bcc: list[str] | None = None,
                   html: bool = False, attachments: list[str] | None = None,
                   in_reply_to: str | None = None, reply_to: list[str] | None = None,
                   from_address: str | None = None, send_mode: str = "send_as") -> dict:
        with self.state(mutate=True) as s:
            self.require(s, account_name, send_mode)
            prepared = self._prepare(s, account_name, recipients, subject, body, cc, bcc, html,
                                     attachments, in_reply_to, reply_to, from_address, send_mode)
            return self._submit(s, prepared)

    def get_send_status(self, account_name: str, submission_id: str) -> dict:
        with self.state() as s:
            self.require(s, account_name)
            submission = self.resource(s, "submissions", submission_id)
            if submission["account_name"] != account_name:
                raise ValueError("Unknown submission in selected account")
            result = copy.deepcopy(submission)
            visible, hidden_groups = [], {}
            for item in result["recipient_results"]:
                groups = item.pop("groups", [])
                groups = [next((current for current in s["groups"] if current["id"] == g["id"]), g) for g in groups]
                hidden = [g for g in groups if
                          (g.get("visible_to") is not None and s["current_actor"] not in g["visible_to"]) or
                          (g.get("members_visible_to") is not None and s["current_actor"] not in g["members_visible_to"])]
                if hidden:
                    for g in hidden:
                        address = g.get("email_address", g.get("address"))
                        hidden_groups[address] = {"address": address, "status": "unknown", "members_visible": False}
                else:
                    visible.append(item)
            result["recipient_results"] = visible + list(hidden_groups.values())
            return result

    def _draft(self, s, account_name, draft_id, write=False):
        self.require(s, account_name, "write" if write else "read")
        d = self.resource(s, "drafts", draft_id)
        if d["account_name"] != account_name:
            raise ValueError("Unknown draft in selected account")
        return d

    def _save_draft(self, s, prepared):
        self.require(s, prepared["account_name"], "write")
        draft = {**prepared, "id": identifier("draft"), "version": 1,
                 "created_at": s["now"], "updated_at": s["now"]}
        s["drafts"].append(draft)
        self.event(s, "create_draft", draft["account_name"], draft["id"], after=draft)
        return self.public(draft, True)

    def create_draft(self, account_name: str, recipients: list[str] | None = None, subject: str = "", body: str = "",
                     cc: list[str] | None = None, bcc: list[str] | None = None,
                     html: bool = False, attachments: list[str] | None = None,
                     in_reply_to: str | None = None, reply_to: list[str] | None = None,
                     from_address: str | None = None, send_mode: str = "send_as") -> dict:
        with self.state(mutate=True) as s:
            self.require(s, account_name, "write")
            prepared = self._prepare(s, account_name, recipients, subject, body, cc, bcc, html,
                                     attachments, in_reply_to, reply_to, from_address, send_mode)
            return self._save_draft(s, prepared)

    def list_drafts(self, account_name: str, offset: int = 0, limit: int = 20) -> dict:
        with self.state() as s:
            self.require(s, account_name)
            return page([self.public(d) for d in s["drafts"] if d["account_name"] == account_name], offset, limit)

    def get_draft(self, account_name: str, draft_id: str) -> dict:
        with self.state() as s:
            return self.public(self._draft(s, account_name, draft_id), True)

    def update_draft(self, account_name: str, draft_id: str, changes: DraftChanges,
                     expected_version: int | None = None) -> dict:
        allowed = {"recipients", "cc", "bcc", "subject", "body", "html", "reply_to", "from_address", "send_mode"}
        if not changes or set(changes) - allowed:
            raise ValueError("Unsupported draft fields")
        with self.state(mutate=True) as s:
            d = self._draft(s, account_name, draft_id, True)
            check_version(d, expected_version)
            before = copy.deepcopy(d)
            prepared = self._prepare(s, account_name, changes.get("recipients", d["to"]),
                                     changes.get("subject", d["subject"]), changes.get("body", d["body"]),
                                     changes.get("cc", d["cc"]), changes.get("bcc", d["bcc"]),
                                     changes.get("html", d["html"]), in_reply_to=d["in_reply_to"],
                                     reply_to=changes.get("reply_to", d["reply_to"]),
                                     from_address=changes.get("from_address", d["from"]),
                                     send_mode=changes.get("send_mode", d["send_mode"]), attachment_snapshots=d["attachments"])
            prepared["thread_id"] = d["thread_id"]
            d.update(prepared)
            touch(d, s["now"])
            self.event(s, "update_draft", account_name, draft_id, before, d)
            return self.public(d, True)

    def delete_draft(self, account_name: str, draft_id: str, expected_version: int | None = None) -> dict:
        with self.state(mutate=True) as s:
            d = self._draft(s, account_name, draft_id, True)
            check_version(d, expected_version)
            s["drafts"].remove(d)
            self.event(s, "delete_draft", account_name, draft_id, before=d)
            return {"deleted_id": draft_id}

    def send_draft(self, account_name: str, draft_id: str, expected_version: int | None = None) -> dict:
        with self.state(mutate=True) as s:
            d = self._draft(s, account_name, draft_id, True)
            check_version(d, expected_version)
            result = self._submit(s, d)
            s["drafts"] = [item for item in s["drafts"] if item["id"] != draft_id]
            self.event(s, "consume_draft", account_name, draft_id, before=d)
            return result

    def update_draft_attachments(self, account_name: str, draft_id: str,
                                 attachments: list[str] | None = None,
                                 remove_ids: list[str] | None = None,
                                 expected_version: int | None = None) -> dict:
        with self.state(mutate=True) as s:
            d = self._draft(s, account_name, draft_id, True)
            check_version(d, expected_version)
            remove_ids = remove_ids or []
            if not set(remove_ids) <= {a["id"] for a in d["attachments"]}:
                raise ValueError("Unknown attachment")
            before = copy.deepcopy(d)
            result = [a for a in d["attachments"] if a["id"] not in remove_ids] + [self.snapshot(p) for p in attachments or []]
            if len(result) > 20 or sum(a["size"] for a in result) > 50 * 1024 * 1024:
                raise ValueError("At most 20 attachments and 50 MiB total")
            d["attachments"] = result
            touch(d, s["now"])
            self.event(s, "update_draft_attachments", account_name, draft_id, before, d)
            return self.public(d, True)

    def reply_email(self, account_name: str, email_id: str, body: str,
                    reply_all: bool = False, quote_original: bool = True,
                    attachments: list[str] | None = None, as_draft: bool = True,
                    send_mode: str = "send_as", from_address: str | None = None) -> dict:
        with self.state(mutate=True) as s:
            m = self.message(s, account_name, email_id)
            a = self.account(s, account_name)
            own = {v.casefold() for v in [a["email_address"], *a["aliases"]]}
            own.update(v["email_address"].casefold() for v in s["actors"] if v["id"] == s["current_actor"])
            own.update(v.casefold() for box in s["accounts"] if box["owner_id"] == s["current_actor"]
                       for v in [box["email_address"], *box["aliases"]])
            primary = m["to"] if m["sender_copy"] else m.get("reply_to") or [m["from"]]
            recipients = [v for v in primary if v.casefold() not in own]
            cc = [v for v in (m["to"] + m["cc"] if reply_all else []) if v.casefold() not in own]
            text_body = body + ("\n\n--- Original message ---\n" + m["body"] if quote_original else "")
            subject = m["subject"] if m["subject"].lower().startswith("re:") else "Re: " + m["subject"]
            prepared = self._prepare(s, account_name, recipients, subject, text_body, cc=cc,
                                     attachments=attachments, in_reply_to=m["message_id"],
                                     send_mode=send_mode, from_address=from_address)
            return self._save_draft(s, prepared) if as_draft else self._submit(s, prepared)

    def forward_email(self, account_name: str, email_id: str, recipients: list[str],
                      body: str = "", cc: list[str] | None = None, bcc: list[str] | None = None,
                      include_attachments: bool = True, as_attachment: bool = False,
                      as_draft: bool = True, send_mode: str = "send_as",
                      from_address: str | None = None) -> dict:
        with self.state(mutate=True) as s:
            m = self.message(s, account_name, email_id)
            prepared = self._forward_prepared(s, m, recipients, body, cc, bcc,
                                              include_attachments, as_attachment, send_mode, from_address)
            return self._save_draft(s, prepared) if as_draft else self._submit(s, prepared)

    def _forward_prepared(self, s, m, recipients, body="", cc=None, bcc=None,
                          include_attachments=True, as_attachment=False,
                          send_mode="send_as", from_address=None):
        snapshots = copy.deepcopy(m["attachments"]) if include_attachments and not as_attachment else []
        if as_attachment:
            import hashlib
            original = copy.deepcopy(m)
            if not include_attachments:
                original["attachments"] = []
            raw = self.mime_bytes(original)
            snapshots = [{"id": identifier("attachment"), "name": "forwarded.eml", "content_type": "message/rfc822",
                          "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                          "content_base64": base64.b64encode(raw).decode("ascii")}]
        content = body if as_attachment else body + "\n\n--- Forwarded message ---\nFrom: " + m["from"] + "\nTo: " + ", ".join(m["to"]) + "\nSubject: " + m["subject"] + "\n\n" + m["body"]
        return self._prepare(s, m["account_name"], recipients, "Fwd: " + m["subject"], content,
                             cc=cc, bcc=bcc, attachment_snapshots=snapshots,
                             send_mode=send_mode, from_address=from_address)

    def schedule_email(self, account_name: str, draft_id: str, send_at: str,
                       expected_version: int | None = None) -> dict:
        with self.state(mutate=True) as s:
            d = self._draft(s, account_name, draft_id, True)
            check_version(d, expected_version)
            self.require(s, account_name, d["send_mode"])
            if not d["to"] + d["cc"] + d["bcc"]:
                raise ValueError("Scheduling requires at least one recipient")
            if date(send_at) <= date(s["now"]):
                raise ValueError("send_at must be in the future")
            job = {"id": identifier("scheduled"), "account_name": account_name, "status": "pending",
                   "actor_id": s["current_actor"], "send_at": send_at, "version": 1,
                   "prepared": copy.deepcopy(d), "created_at": s["now"]}
            s["scheduled"].append(job)
            s["drafts"].remove(d)
            self.event(s, "schedule_email", account_name, job["id"], before=d, after=job)
            return self._public_schedule(job)

    def _public_schedule(self, job):
        result = {k: copy.deepcopy(v) for k, v in job.items() if k != "prepared"}
        result["message"] = self.public(job["prepared"], True)
        return result

    def list_scheduled_emails(self, account_name: str, status: str | None = None,
                              offset: int = 0, limit: int = 20) -> dict:
        if status not in {None, "pending", "submitted", "failed", "cancelled"}:
            raise ValueError("Invalid schedule status")
        with self.state() as s:
            self.require(s, account_name)
            return page([self._public_schedule(j) for j in s["scheduled"] if j["account_name"] == account_name and (status is None or j["status"] == status)], offset, limit)

    def update_scheduled_email(self, account_name: str, scheduled_id: str, send_at: str | None = None,
                               replacement_draft_id: str | None = None,
                               expected_version: int | None = None) -> dict:
        with self.state(mutate=True) as s:
            self.require(s, account_name, "write")
            j = self.resource(s, "scheduled", scheduled_id)
            if j["account_name"] != account_name or j["status"] != "pending":
                raise ValueError("Unknown or nonpending scheduled message")
            check_version(j, expected_version)
            if j["actor_id"] != s["current_actor"]:
                raise PermissionError("Only the scheduling actor can modify this submission")
            before = copy.deepcopy(j)
            if send_at:
                if date(send_at) <= date(s["now"]):
                    raise ValueError("send_at must be in the future")
                j["send_at"] = send_at
            if replacement_draft_id:
                d = self._draft(s, account_name, replacement_draft_id, True)
                self.require(s, account_name, d["send_mode"])
                if not d["to"] + d["cc"] + d["bcc"]:
                    raise ValueError("Scheduling requires at least one recipient")
                j["prepared"] = copy.deepcopy(d)
                s["drafts"].remove(d)
            if not send_at and not replacement_draft_id:
                raise ValueError("Specify send_at or replacement_draft_id")
            touch(j, s["now"])
            self.event(s, "update_scheduled_email", account_name, scheduled_id, before, j)
            return self._public_schedule(j)

    def cancel_scheduled_email(self, account_name: str, scheduled_id: str,
                               expected_version: int | None = None) -> dict:
        with self.state(mutate=True) as s:
            self.require(s, account_name, "write")
            j = self.resource(s, "scheduled", scheduled_id)
            if j["account_name"] != account_name or j["status"] != "pending":
                raise ValueError("Unknown or nonpending scheduled message")
            check_version(j, expected_version)
            before = copy.deepcopy(j)
            j["status"] = "cancelled"
            touch(j, s["now"])
            self.event(s, "cancel_scheduled_email", account_name, scheduled_id, before, j)
            return self._public_schedule(j)
