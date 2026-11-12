"""Host-only arrival, clock and delivery-evidence operations. Not MCP tools."""
import argparse
import base64
import copy
import hashlib
import json

from .common import addresses, date, identifier, text, touch


def receive_email(store, account_name, message):
    """Inject a normal inbound message and run its inbox automation atomically."""
    allowed = {"from", "to", "cc", "subject", "body", "html", "reply_to", "in_reply_to", "references", "message_id", "attachments", "headers", "automatic"}
    if set(message) - allowed:
        raise ValueError("Unsupported incoming fields")
    with store.state(mutate=True) as s:
        a = store.account(s, account_name)
        addresses([message["from"]])
        for key in ("to", "cc", "reply_to"):
            addresses(message.get(key, []))
        text(message.get("subject", ""), "subject", True)
        text(message.get("body", ""), "body", True)
        if any(c in message.get("subject", "") for c in "\r\n"):
            raise ValueError("Invalid subject header")
        for key, value in message.get("headers", {}).items():
            if not key or any(c in key for c in ":\r\n") or not isinstance(value, str) or any(c in value for c in "\r\n"):
                raise ValueError("Invalid incoming header")
        m = {"subject": "", "body": "", "to": [a["email_address"]], "cc": [],
             "reply_to": [], "attachments": [], "html": False, "references": [], **copy.deepcopy(message),
             "id": identifier("mail"), "account_name": account_name, "timestamp": s["now"],
             "mailbox": "INBOX", "bcc": [], "sender_copy": False, "version": 1,
             "is_read": False, "starred": False, "categories": [], "importance": "normal"}
        m.setdefault("message_id", "<" + identifier("incoming") + "@mail.local>")
        for attachment in m["attachments"]:
            raw = base64.b64decode(attachment["content_base64"], validate=True)
            if len(raw) > 25 * 1024 * 1024:
                raise ValueError("Attachment exceeds 25 MiB")
            attachment.setdefault("id", identifier("attachment"))
            attachment.update(size=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            attachment.setdefault("content_type", "application/octet-stream")
        if len(m["attachments"]) > 20 or sum(v["size"] for v in m["attachments"]) > 50 * 1024 * 1024:
            raise ValueError("At most 20 attachments and 50 MiB total")
        parent_ids = [*m.get("references", []), m.get("in_reply_to")]
        parent = next((v for v in s["messages"] if v["account_name"] == account_name and v["message_id"] in parent_ids), None)
        m["thread_id"] = parent["thread_id"] if parent else identifier("thread")
        s["messages"].append(m)
        store.event(s, "receive_email", account_name, m["id"], after=m, actor="mail-system")
        store._apply_incoming(s, m, automated=m.get("automatic", False))
        return {"email_id": m["id"], "message_id": m["message_id"]}


def advance_time(store, to):
    """Execute pending jobs in due-time order, preserving frozen message content."""
    with store.state(mutate=True) as s:
        target = date(to)
        if target < date(s["now"]):
            raise ValueError("Clock cannot move backwards")
        due = sorted([(j["send_at"], j["id"]) for j in s["scheduled"]
                      if j["status"] == "pending" and date(j["send_at"]) <= target], key=lambda v: (date(v[0]), v[1]))
        results = []
        original = s["now"]
        for due_at, job_id in due:
            s["now"] = max(date(s["now"]), date(due_at)).isoformat()
            savepoint = copy.deepcopy(s)
            j = store.resource(s, "scheduled", job_id)
            try:
                result = store._submit(s, j["prepared"], actor=j["actor_id"])
                j = store.resource(s, "scheduled", job_id)
                j.update(status="submitted", result=result)
            except (ValueError, PermissionError) as error:
                s.clear()
                s.update(savepoint)
                j = store.resource(s, "scheduled", job_id)
                j.update(status="failed", error=str(error))
            touch(j, s["now"])
            store.event(s, "execute_scheduled_email", j["account_name"], job_id,
                        after={k: v for k, v in j.items() if k != "prepared"}, actor=j["actor_id"])
            results.append({"id": job_id, "status": j["status"]})
        s["now"] = to
        store.event(s, "advance_time", before=original, after=to, actor="mail-system")
        return {"now": to, "scheduled_results": results}


def record_delivery(store, submission_id, address, status, reason=""):
    """Record evidence supplied by the host; unknown remains the external default."""
    if status not in {"delivered", "bounced"}:
        raise ValueError("Delivery evidence must be delivered or bounced")
    with store.state(mutate=True) as s:
        sub = store.resource(s, "submissions", submission_id)
        result = next((r for r in sub["recipient_results"] if r["address"].casefold() == address.casefold()), None)
        if result is None or result["status"] != "unknown":
            raise ValueError("Unknown recipient or delivery already finalized")
        result.update(status=status, at=s["now"], reason=reason)
        touch(sub, s["now"])
        statuses = {r["status"] for r in sub["recipient_results"]}
        sub["status"] = "bounced" if statuses == {"bounced"} else "delivered" if statuses == {"delivered"} else "partial" if "bounced" in statuses else "accepted"
        evidence = {"submission_id": submission_id, "address": address, "status": status, "reason": reason, "at": s["now"]}
        s["delivery_events"].append(evidence)
        store.event(s, "delivery_evidence", sub["account_name"], submission_id, after=evidence, actor="mail-system")
        if status == "bounced":
            # NDR is an ordinary incoming message and is marked automatic.
            m = {"id": identifier("mail"), "message_id": "<" + identifier("ndr") + "@mail.local>",
                 "account_name": sub["account_name"], "mailbox": "INBOX", "from": "mailer-daemon@mail.local",
                 "to": [store.account(s, sub["account_name"])["email_address"]], "cc": [], "bcc": [],
                 "subject": "Delivery failed: " + address, "body": reason, "timestamp": s["now"],
                 "attachments": [], "is_read": False, "starred": False, "categories": [], "version": 1,
                 "sender_copy": False, "automatic": True, "thread_id": identifier("thread"),
                 "in_reply_to": sub["message_id"], "headers": {"Auto-Submitted": "auto-generated"}}
            s["messages"].append(m)
            store.event(s, "receive_ndr", sub["account_name"], m["id"], after=m, actor="mail-system")
            store._apply_incoming(s, m, automated=True)
        return copy.deepcopy(store.resource(s, "submissions", submission_id))


def main():
    from .backend import MailStore
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    clock = commands.add_parser("advance-time")
    clock.add_argument("--to", required=True)
    incoming = commands.add_parser("receive")
    incoming.add_argument("--account", required=True)
    incoming.add_argument("--message-file", required=True)
    delivery = commands.add_parser("delivery")
    delivery.add_argument("--submission-id", required=True)
    delivery.add_argument("--address", required=True)
    delivery.add_argument("--status", choices=["delivered", "bounced"], required=True)
    delivery.add_argument("--reason", default="")
    args = parser.parse_args()
    store = MailStore(args.run_root)
    if args.command == "advance-time":
        result = advance_time(store, args.to)
    elif args.command == "receive":
        from pathlib import Path
        result = receive_email(store, args.account, json.loads(Path(args.message_file).read_text(encoding="utf-8-sig")))
    else:
        result = record_delivery(store, args.submission_id, args.address, args.status, args.reason)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
