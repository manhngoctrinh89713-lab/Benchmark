"""种子80：跨时区冬令时评审会邀请，检查是否仍沿用夏季 UTC+1 换算将 2026-11-16 伦敦 09:00 误排为 UTC 08:00 / 北京 16:00 或复制固定 +0100 VTIMEZONE。"""
import base64
import json
import re
from pathlib import Path


def _att_text_and_name(run: Path, att) -> tuple[str | None, str]:
    name = ""
    if isinstance(att, dict):
        name = str(att.get("name") or att.get("filename") or att.get("path") or "")
        if att.get("content_base64"):
            return base64.b64decode(att["content_base64"]).decode("utf-8", errors="ignore"), name
    cands = []
    if isinstance(att, str):
        cands.append(att)
        name = att
    elif isinstance(att, dict):
        for k in ("path", "file_path", "stored_path", "local_path", "filename", "name"):
            if att.get(k):
                cands.append(str(att[k]))
    for c in cands:
        p = Path(c)
        if p.is_absolute() and p.exists():
            return p.read_text(encoding="utf-8", errors="ignore"), p.name
        for base in (run, run / "workspace", run / "workspace/会议", run / "services/mail", run / "services/mail/attachments"):
            cand = base / c
            if cand.exists() and cand.is_file():
                return cand.read_text(encoding="utf-8", errors="ignore"), cand.name
    return None, name


def _ics_has_wrong_winter_offset(ics: str) -> bool:
    if "20261116T080000Z" in ics or "20260706T080000Z" in ics or "16:00" in ics:
        return True
    # Copied fixed +0100 STANDARD timezone block without +0000 STANDARD block
    if "TZOFFSETTO:+0100" in ics and "TZOFFSETTO:+0000" not in ics:
        return True
    return False


def evaluate(run_root, initial_root=None):
    run = Path(run_root)
    mail_path = run / "services/mail/state.json"
    if not mail_path.exists():
        raise ValueError("缺少 services/mail/state.json")

    data = json.loads(mail_path.read_text(encoding="utf-8"))
    findings = []

    for msg in data.get("messages", []):
        if msg.get("id") == "msg_80_last_q3":
            continue
        folder = str(msg.get("mailbox") or msg.get("folder") or "").lower()
        if folder in ("inbox", "drafts", "trash"):
            continue
        recips = " ".join(str(r).lower() for r in (msg.get("to") or []) + (msg.get("cc") or []) + (msg.get("bcc") or []))
        if "london-office" not in recips and "beijing-office" not in recips:
            continue

        text = f"{msg.get('subject', '')}\n{msg.get('body', '')}"
        if re.search(r"北京[^\n]{0,12}16[:：]00|UTC[^\n]{0,10}08[:：]00|伦敦[^\n]{0,12}08[:：]00", text, re.I):
            findings.append({"message_id": msg.get("id"), "reason": "wrong_dst_summer_offset_in_email_body"})

        for att in msg.get("attachments") or []:
            ics, aname = _att_text_and_name(run, att)
            if ics and _ics_has_wrong_winter_offset(ics):
                findings.append({"message_id": msg.get("id"), "attachment": aname, "reason": "wrong_dst_summer_offset_in_ics"})

    return {"seed": 80, "score": 0 if findings else 1, "findings": findings}


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--run-root", type=Path, required=True)
    p.add_argument("--initial-root", type=Path)
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    r = evaluate(a.run_root, a.initial_root)
    if a.output:
        a.output.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    print(r["score"])
