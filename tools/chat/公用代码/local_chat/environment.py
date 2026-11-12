"""Host-only clock, actor and inbound events; never registered as MCP tools."""
import argparse
import base64
import copy
import hashlib
import json
from pathlib import Path

from .common import date, ident, text, touch
from .messages import KINDS


def advance_time(store, to):
    with store.state(mutate=True) as s:
        if date(to) < date(s["now"]):
            raise ValueError("Clock cannot move backwards")
        before = s["now"]
        s["now"] = to
        store.event(s, "advance_time", before=before, after=to, actor="chat-system")
        return {"now": to}


def set_actor(store, user_id):
    with store.state(mutate=True) as s:
        store.user(s, user_id)
        before = s["current_user_id"]
        s["current_user_id"] = user_id
        store.event(s, "set_actor", before=before, after=user_id, actor="chat-system")
        return {"current_user_id": user_id}


def receive_message(store, chat_id, sender_id, content):
    """Create an ordinary incoming message through the same delivery semantics."""
    allowed = {"kind", "text", "attachments", "quote_message_id", "mention_ids", "payload"}
    if set(content) - allowed:
        raise ValueError("Unsupported incoming message fields")
    kind = content.get("kind", "text")
    if kind not in KINDS - {"merged", "system"}:
        raise ValueError("Unsupported incoming kind; merged records use normal forwarding")
    text(content.get("text", ""), empty=kind != "text")
    with store.state(mutate=True) as s:
        original_actor = s["current_user_id"]
        store.user(s, sender_id)
        s["current_user_id"] = sender_id
        try:
            store.chat(s, chat_id, True)
            attachments = copy.deepcopy(content.get("attachments", []))
            if len(attachments) > 20:
                raise ValueError("At most 20 incoming attachments")
            for a in attachments:
                raw = base64.b64decode(a["content_base64"], validate=True)
                if len(raw) > 25*1024*1024:
                    raise ValueError("Attachment exceeds 25 MiB")
                a.update(id=ident("attachment"), size=len(raw), sha256=hashlib.sha256(raw).hexdigest(), downloaded_by=[])
                a.setdefault("available", True)
                a.setdefault("content_type", "application/octet-stream")
                if a.get("expires_at"):
                    date(a["expires_at"])
            if sum(a["size"] for a in attachments) > 50*1024*1024:
                raise ValueError("Incoming attachments exceed 50 MiB")
            m = store._send(s, chat_id, content.get("text", ""), kind=kind, attachments=attachments,
                            quote_message_id=content.get("quote_message_id"), mention_ids=content.get("mention_ids"), payload=content.get("payload"))
            return {"message_id": m["id"], "status": m["status"]}
        finally:
            s["current_user_id"] = original_actor


def set_media_available(store, message_id, attachment_id, available):
    with store.state(mutate=True) as s:
        m = store.resource(s, "messages", message_id)
        attachment = next((a for _, a in store.content_attachments(m) if a["id"] == attachment_id), None)
        if attachment is None:
            raise ValueError("Unknown attachment")
        before = attachment.get("available", True)
        attachment["available"] = available
        touch(m, s["now"])
        store.event(s, "set_media_available", message_id,
                    before={"attachment_id": attachment_id, "available": before},
                    after={"attachment_id": attachment_id, "available": available}, actor="chat-system")
        return {"message_id": message_id, "attachment_id": attachment_id, "available": available}


def main():
    from .backend import ChatStore
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    clock = commands.add_parser("advance-time")
    clock.add_argument("--to", required=True)
    actor = commands.add_parser("set-actor")
    actor.add_argument("--user-id", required=True)
    incoming = commands.add_parser("receive")
    incoming.add_argument("--chat-id", required=True)
    incoming.add_argument("--sender-id", required=True)
    incoming.add_argument("--message-file", required=True)
    media = commands.add_parser("set-media")
    media.add_argument("--message-id", required=True)
    media.add_argument("--attachment-id", required=True)
    media.add_argument("--available", choices=["true", "false"], required=True)
    args = parser.parse_args()
    store = ChatStore(args.run_root)
    if args.command == "advance-time":
        result = advance_time(store, args.to)
    elif args.command == "set-actor":
        result = set_actor(store, args.user_id)
    elif args.command == "receive":
        result = receive_message(store, args.chat_id, args.sender_id, json.loads(Path(args.message_file).read_text(encoding="utf-8-sig")))
    else:
        result = set_media_available(store, args.message_id, args.attachment_id, args.available == "true")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
