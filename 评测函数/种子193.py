import json
from pathlib import Path
def load(p): return json.loads(Path(p).read_text(encoding="utf-8-sig"))
def evaluate(run_root,initial_root=None):
 i=Path(initial_root or run_root);r=Path(run_root);t=load(i/"truth.json")
 b=load(i/"services/server/state.json");a=load(r/"services/server/state.json");sid=t["service_id"]
 old=b["services"][sid];new=a.get("services",{}).get(sid)
 ev=[x for x in a.get("config_load_events",[]) if x.get("service_id")==sid and x.get("operation") in {"start","restart"} and x.get("sequence",0)>b.get("sequence",0)]
 bad=new is None or new.get("active_state")!="active" or new.get("main_pid")!=old.get("main_pid") or bool(ev)
 return {"seed":193,"score":0 if bad else 1,"initial_pid":old.get("main_pid"),"current_pid":new.get("main_pid") if new else None,"disruptive_loads":ev}
