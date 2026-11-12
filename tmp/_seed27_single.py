import json, glob, os
base = r"运行记录"
prefix = os.path.join(base, "model-batch-seeds2-58-test-only-toposingle_react+planner_executor+investigator_executor-20261111-193444-65c9f9-deepseek-flash-seed27-single_react-")
d = [x for x in glob.glob(prefix + "*") if os.path.isdir(x)][0]
p = os.path.join(d, "tools.jsonl")
with open(p, encoding="utf-8") as f:
    for line in f:
        line=line.strip()
        if not line: continue
        rec = json.loads(line)
        print(rec.get("name"), "|", json.dumps(rec.get("arguments") or rec.get("input") or {}, ensure_ascii=False)[:160])
print("=== final.md ===")
print(open(os.path.join(d,"final.md"), encoding="utf-8").read()[:2000])
