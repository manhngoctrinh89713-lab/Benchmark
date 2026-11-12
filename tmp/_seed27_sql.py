import json, glob, os
base = r"运行记录"
for seed in ["27"]:
    for topo, phases in [("single_react", [""]), ("planner_executor", ["planner","executor"]), ("investigator_executor", ["investigator","executor"])]:
        prefix = os.path.join(base, "model-batch-seeds2-58-test-only-toposingle_react+planner_executor+investigator_executor-20261111-193444-65c9f9-deepseek-flash-seed%s-%s-" % (seed, topo))
        d = [x for x in glob.glob(prefix + "*") if os.path.isdir(x)][0]
        print("#"*90)
        print(seed, topo, os.path.basename(d))
        for ph in phases:
            p = os.path.join(d, ph, "tools.jsonl") if ph else os.path.join(d, "tools.jsonl")
            if not os.path.exists(p): continue
            print("--- phase:", ph or "single")
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line=line.strip()
                    if not line: continue
                    rec = json.loads(line)
                    name = rec.get("name") or ""
                    args = rec.get("arguments") or rec.get("input") or {}
                    if name == "database__execute_transaction" or name == "database__write_query":
                        print("WRITE:", json.dumps(args, ensure_ascii=False))
                    elif name in ("database__read_query",):
                        print("READ:", json.dumps(args, ensure_ascii=False)[:240])
