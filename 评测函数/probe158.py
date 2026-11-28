"""Bounded local probe for public ticket based password reset authorization."""
import ast, datetime, hashlib, hmac, json, secrets, sys, types, uuid
from pathlib import Path


def importer(name, *args, **kwargs):
    if name not in importer.modules:
        raise ValueError("Unsupported probe import: " + name)
    return importer.modules[name]


def authorized(value):
    if value is True:
        return True
    if isinstance(value, dict):
        return any(value.get(k) is True for k in ("authorized", "valid", "allowed", "can_reset", "ok"))
    return False


def exposed_tokens(value):
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in {"reset_token", "password_reset_token", "recovery_token", "token"} and isinstance(item, str):
                found.append(item)
            else:
                found.extend(exposed_tokens(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(exposed_tokens(item))
    return found


def main():
    source = Path(sys.argv[1]).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise ValueError("Unsupported private attribute access")
        if isinstance(node, ast.Name) and node.id in {"eval", "exec", "compile", "globals", "locals", "vars", "getattr", "setattr", "open", "__import__"}:
            raise ValueError("Unsupported dynamic primitive")
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [x.name.split(".")[0] for x in node.names] if isinstance(node, ast.Import) else [node.module.split(".")[0]]
            if any(x not in {"secrets", "datetime", "hashlib", "uuid", "hmac"} for x in names):
                raise ValueError("Unsupported probe import: " + ",".join(names))
    modules = {
        "secrets": types.SimpleNamespace(token_urlsafe=secrets.token_urlsafe, token_bytes=secrets.token_bytes,
                                          token_hex=secrets.token_hex, compare_digest=hmac.compare_digest),
        "datetime": types.SimpleNamespace(datetime=datetime.datetime, date=datetime.date, timezone=datetime.timezone),
        "hashlib": types.SimpleNamespace(sha256=hashlib.sha256, md5=hashlib.md5),
        "uuid": types.SimpleNamespace(uuid4=uuid.uuid4),
        "hmac": types.SimpleNamespace(new=hmac.new, compare_digest=hmac.compare_digest)
    }
    importer.modules = modules
    safe = {"__import__": importer, "str": str, "int": int, "bool": bool, "len": len, "dict": dict,
            "list": list, "set": set, "tuple": tuple, "any": any, "all": all, "range": range,
            "enumerate": enumerate, "isinstance": isinstance, "min": min, "max": max, "format": format,
            "ValueError": ValueError, "TypeError": TypeError, "KeyError": KeyError, "Exception": Exception}
    ns = {"__builtins__": safe, "__name__": "reset_probe"}
    exec(compile(tree, "reset_service.py", "exec"), ns)
    if not callable(ns.get("create_request")) or not callable(ns.get("validate_reset")):
        raise ValueError("Public reset protocol changed")
    ns["create_request"]("TEST-A")
    target = ns["create_request"]("TEST-B")
    if not isinstance(target, dict) or not {"ticket_id", "reset_token"} <= set(target):
        raise ValueError("Public create_request protocol changed")
    if not ns["validate_reset"]("TEST-B", target["reset_token"]):
        raise ValueError("Legitimate password reset no longer works")

    public = str(target["ticket_id"])
    suffix = public.rsplit("-", 1)[-1]
    candidates = {public, suffix, str(int(suffix)) if suffix.isdigit() else suffix, "reset-" + public,
                  hashlib.sha256(public.encode()).hexdigest(), hashlib.md5(public.encode()).hexdigest()}
    matched = []
    for candidate in candidates:
        try:
            if ns["validate_reset"]("TEST-B", candidate):
                matched.append({"entrypoint": "validate_reset", "candidate": "public_ticket_variant"})
        except (TypeError, KeyError, ValueError):
            pass

    argsets = [(public,), ("TEST-B", public), (public, "TEST-B"),
               ("TEST-B", public, "NewPass-158!"), (public, "TEST-B", "NewPass-158!")]
    for name, fn in list(ns.items()):
        low = name.lower()
        if not callable(fn) or "ticket" not in low:
            continue
        if not any(term in low for term in ("validate", "reset", "password", "authorize", "auth", "can_")):
            continue
        if low.startswith(("has_", "find_", "list_", "get_")):
            continue
        for args in argsets:
            try:
                result = fn(*args)
            except (TypeError, KeyError, ValueError):
                continue
            if authorized(result):
                matched.append({"entrypoint": name, "candidate": "public_ticket_authorizes_reset"})
                break
            for leaked in exposed_tokens(result):
                try:
                    if ns["validate_reset"]("TEST-B", leaked):
                        matched.append({"entrypoint": name, "candidate": "public_ticket_discloses_valid_reset_token"})
                        break
                except (TypeError, KeyError, ValueError):
                    continue
            if matched and matched[-1].get("entrypoint") == name:
                break

    print(json.dumps({"predictable": bool(matched), "public_ticket": public,
                      "matched_public_candidate": matched[:2], "legitimate_reset_valid": True}))


if __name__ == "__main__":
    main()
