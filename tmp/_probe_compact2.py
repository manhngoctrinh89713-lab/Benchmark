import json, glob, os, sys

def load_run(run_dir):
    info = {}
    for name in ["run.json", "final.md", "brief.md", "user.md", "evaluation.json"]:
        p = os.path.join(run_dir, name)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                info[name] = f.read()
    calls = []
    for phase in ["investigator", "planner", "executor", ""]:
        p = os.path.join(run_dir, phase, "tools.jsonl") if phase else os.path.join(run_dir, "tools.jsonl")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    calls.append({"phase": phase or "single", "rec": rec})
    info["calls"] = calls
    return info

def tool_names(calls, phase=None):
    names = []
    for c in calls:
        if phase and c["phase"] != phase:
            continue
        rec = c["rec"]
        name = rec.get("name") or rec.get("tool") or "?"
        args = rec.get("arguments") or rec.get("input") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                pass
        argstr = json.dumps(args, ensure_ascii=False)
        names.append(name + ("(" + argstr[:100] + ")" if argstr else ""))
    return names

def main():
    base = r"运行记录"
    seeds = sys.argv[1:]
    for seed in seeds:
        print("#" * 110)
        print("SEED %s" % seed)
        for topo in ["single_react", "planner_executor", "investigator_executor"]:
            prefix = os.path.join(base, "model-batch-seeds2-58-test-only-toposingle_react+planner_executor+investigator_executor-20261111-193444-65c9f9-deepseek-flash-seed%s-%s-" % (seed, topo))
            matches = [d for d in glob.glob(prefix + "*") if os.path.isdir(d)]
            if not matches:
                continue
            d = matches[0]
            info = load_run(d)
            print("-" * 110)
            print("== %s ==" % topo)
            ev = info.get("evaluation.json") or ""
            print("EVAL:", ev.strip()[:400])
            if info.get("brief.md"):
                print("BRIEF(first 700):")
                print(info["brief.md"][:700])
            names = tool_names(info["calls"])
            print("TOOLS(%d):" % len(names))
            print("  " + " | ".join(names))
            f = (info.get("final.md") or "").strip()
            if f:
                print("FINAL(first 500):")
                print(f[:500])

if __name__ == "__main__":
    main()
