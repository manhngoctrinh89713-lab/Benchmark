import json, glob, os, sys

def load_run(run_dir):
    info = {}
    for name in ["run.json", "final.md", "brief.md", "user.md"]:
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

def main():
    base = r"运行记录"
    seeds = sys.argv[1:]
    show = sys.argv[2] if len(sys.argv) > 2 else "full"
    for seed in seeds:
        for topo in ["single_react", "planner_executor", "investigator_executor"]:
            prefix = os.path.join(base, "model-batch-seeds2-58-test-only-toposingle_react+planner_executor+investigator_executor-20261111-193444-65c9f9-deepseek-flash-seed%s-%s-" % (seed, topo))
            matches = [d for d in glob.glob(prefix + "*") if os.path.isdir(d)]
            if not matches:
                continue
            d = matches[0]
            info = load_run(d)
            print("=" * 100)
            print("SEED %s | %s | %s" % (seed, topo, os.path.basename(d)))
            print("-" * 100)
            if info.get("user.md"):
                print("USER: %s" % info["user.md"].strip())
                print("-" * 100)
            if info.get("brief.md"):
                print("BRIEF:")
                print(info["brief.md"])
                print("-" * 100)
            print("TOOL CALLS:")
            for c in info["calls"]:
                rec = c["rec"]
                name = rec.get("name") or rec.get("tool") or "?"
                args = rec.get("arguments") or rec.get("input") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        pass
                argstr = json.dumps(args, ensure_ascii=False)
                if len(argstr) > 260:
                    argstr = argstr[:260] + "..."
                print("  [%s] %s %s" % (c["phase"], name, argstr))
            print("-" * 100)
            if show == "full":
                print("FINAL:")
                print((info.get("final.md") or "")[:1500])

if __name__ == "__main__":
    main()
