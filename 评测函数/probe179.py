"""Bounded local notification probe for seed 179."""
import ast, datetime, json, sys, types
from pathlib import Path

def importer(name,*args,**kwargs):
    if name not in modules: raise ValueError("Unsupported probe import: "+name)
    return modules[name]

def main():
    path=Path(sys.argv[1]); truth=json.loads(sys.argv[2]); tree=ast.parse(path.read_text(encoding="utf-8"))
    allowed={"notifier","datetime","collections","typing","copy","re","json"}
    for node in ast.walk(tree):
        if isinstance(node,ast.Attribute) and node.attr.startswith("_"): raise ValueError("Unsupported private attribute")
        if isinstance(node,ast.Name) and node.id in {"eval","exec","compile","open","input","globals","locals","vars","getattr","setattr"}: raise ValueError("Unsupported dynamic primitive")
        if isinstance(node,ast.Import) and any(x.name.split(".")[0] not in allowed for x in node.names): raise ValueError("Unsupported import")
        if isinstance(node,ast.ImportFrom) and (not node.module or node.module.split(".")[0] not in allowed): raise ValueError("Unsupported import")
    notifications=[]
    notifier=types.SimpleNamespace(notifications=notifications)
    notifier.send=lambda event: notifications.append(dict(event) if isinstance(event,dict) else event)
    modules.update({"notifier":notifier,"json":json})
    safe={"__import__":importer,"True":True,"False":False,"None":None,"str":str,"int":int,"bool":bool,"len":len,
          "dict":dict,"list":list,"set":set,"tuple":tuple,"any":any,"all":all,"range":range,"enumerate":enumerate,
          "isinstance":isinstance,"min":min,"max":max,"sorted":sorted,"sum":sum,"zip":zip,
          "ValueError":ValueError,"TypeError":TypeError,"KeyError":KeyError,"Exception":Exception}
    ns={"__builtins__":safe,"__name__":"seed179_probe"}
    exec(compile(tree,str(path),"exec"),ns)
    handle=ns.get("handle")
    if not callable(handle): raise ValueError("Missing handle(event)")
    runtime_errors=[]
    for event in truth["probe_events"]:
        try: handle(dict(event))
        except Exception as exc: runtime_errors.append({"event_id":event["id"],"type":type(exc).__name__})
    rendered=json.dumps(notifications,ensure_ascii=False,default=str)
    later=truth["probe_events"][-1]
    visible=later["id"] in rendered or all(term in rendered for term in truth["latest_state_terms"])
    print(json.dumps({"latest_status_delivered":bool(visible),"later_event_id":later["id"],"notifications":notifications,"runtime_errors":runtime_errors},ensure_ascii=True,default=str))
if __name__=="__main__":
    modules={"notifier":None,
             "datetime":types.SimpleNamespace(datetime=datetime.datetime,date=datetime.date,timezone=datetime.timezone),
             "collections":types.SimpleNamespace(),"typing":types.SimpleNamespace(Any=object,Dict=dict,List=list,Set=set,Tuple=tuple),
             "copy":types.SimpleNamespace(copy=lambda x:x,deepcopy=lambda x:x),
             "re":types.SimpleNamespace()}
    main()
