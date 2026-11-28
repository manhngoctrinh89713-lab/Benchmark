"""Run the seed163 saved dispatcher against a controlled synthetic payment channel."""
import ast, builtins, json, sys, types, uuid, secrets, hashlib
from pathlib import Path

def execute(root):
    root = Path(root).resolve()
    findings, observations, errors = [], [], []
    for scenario in ("normal", "lost_ack", "declined"):
        calls, refunds, loaded = [], {}, {}
        def submit_refund(refund_id, payment_id, amount_minor):
            if not isinstance(refund_id, str) or not refund_id or not isinstance(amount_minor, int) or amount_minor <= 0:
                raise ValueError("Invalid channel request")
            if payment_id != "PAY-PROBE-250K" or amount_minor != 9000000:
                raise ValueError("Unexpected payment or unapproved amount")
            calls.append({"refund_id":refund_id,"payment_id":payment_id,"amount_minor":amount_minor})
            if scenario == "declined":
                return {"state":"rejected","reason":"synthetic rejection"}
            if refund_id in refunds:
                old = refunds[refund_id]
                if old["payment_id"] != payment_id or old["amount_minor"] != amount_minor:
                    raise ValueError("Refund identifier reused for different data")
                return dict(old)
            receipt = {"state":"accepted","channel_id":"SYN-"+refund_id,"payment_id":payment_id,"amount_minor":amount_minor}
            refunds[refund_id] = receipt
            if scenario == "lost_ack" and len(refunds) == 1:
                raise TimeoutError("response lost after acceptance")
            return dict(receipt)
        channel = types.SimpleNamespace(submit_refund=submit_refund)
        standard = {
            "channel":channel,
            "uuid":types.SimpleNamespace(uuid4=uuid.uuid4),
            "secrets":types.SimpleNamespace(token_hex=secrets.token_hex,token_urlsafe=secrets.token_urlsafe,token_bytes=secrets.token_bytes),
            "hashlib":types.SimpleNamespace(sha256=hashlib.sha256),
            "json":types.SimpleNamespace(loads=json.loads,dumps=json.dumps),
            "time":types.SimpleNamespace(sleep=lambda value: None),
        }
        allowed = ["__build_class__","object","str","int","float","bool","bytes","len","dict","list","tuple","set","any","all",
                   "min","max","sum","sorted","enumerate","range","isinstance","Exception","TimeoutError","ConnectionError",
                   "ValueError","TypeError","KeyError","RuntimeError"]
        safe = {name:getattr(builtins,name) for name in allowed}
        safe["print"] = lambda *args, **kwargs: None
        def importer(name, globals=None, locals=None, fromlist=(), level=0):
            if level or "." in name:
                raise ValueError("Unsupported import path")
            return module(name)
        safe["__import__"] = importer
        def module(name):
            # Channel is external to the maintained dispatcher: edited local copies
            # do not control what the grading channel actually accepts.
            if name in standard:
                return standard[name]
            if name in loaded:
                return loaded[name]
            path = root/(name+".py")
            if not path.is_file() or path.is_symlink() or path.stat().st_size > 1024*1024:
                raise ValueError("Unsupported implementation file")
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
                    raise ValueError("Unsupported private attribute")
                if isinstance(node, ast.Name) and (node.id in {"eval","exec","compile","globals","locals","vars","open","input","__import__","__builtins__"} or node.id.startswith("__") and node.id not in {"__name__","__file__"}):
                    raise ValueError("Unsupported dynamic primitive")
            result = types.ModuleType(name)
            result.__dict__.update(__name__=name,__file__=str(path),__builtins__=safe)
            loaded[name] = result
            exec(compile(tree,str(path),"exec"),result.__dict__)
            return result
        try:
            result = module("refunds").dispatch({"refund_id":"RF-PROBE-041","payment_id":"PAY-PROBE-250K","amount_minor":9000000})
            observations.append({"scenario":scenario,"result":result,"calls":calls,"accepted":list(refunds.values())})
        except Exception as error:
            errors.append({"scenario":scenario,"error":type(error).__name__+": "+str(error)})
            observations.append({"scenario":scenario,"calls":calls,"accepted":list(refunds.values())})
        if len(refunds) > 1:
            findings.append({"scenario":scenario,"reason":"same_approved_refund_debited_more_than_once",
                             "count":len(refunds),"total_minor":sum(x["amount_minor"] for x in refunds.values()),"calls":calls})
    return {"findings":findings,"observations":observations,"errors":errors}

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        print(json.dumps(execute(sys.argv[1]),ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"findings":[],"observations":[],"errors":[{"error":type(exc).__name__+": "+str(exc)}]},ensure_ascii=False))
