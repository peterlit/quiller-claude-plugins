#!/usr/bin/env python3
"""Turn the sampler's raw samples into numbers and candidate findings.

Usage: nfr_analyze.py <samples.jsonl> [--marks <marks.jsonl>]
                      [--rss-growth-mb 30] [--idle-cpu 20] [--net-mb 5]

samples.jsonl comes from nfr_sampler.sh. marks.jsonl is optional, appended by
the tester as {"ts": <epoch>, "label": "begin:<name>"} / {"ts": ..., "label":
"end:<name>"} around repeated-action loops and idle periods, so windows are
explicit (name an idle window "idle" to enable the CPU check).

Output (JSON): per-PID stints (duration, RSS start/end/growth/slope, CPU
mean/max, network bytes), per-window stats, and CANDIDATE findings with the
numbers — the tester confirms or disputes them; thresholds are arguments so
they stay debatable, not baked in.
"""
import json, sys

def stats(samples):
    if not samples:
        return None
    rss = [s["rss_mb"] for s in samples]
    cpu = [s["cpu_pct"] for s in samples]
    dur = max(1, samples[-1]["ts"] - samples[0]["ts"])
    growth = rss[-1] - rss[0]
    return {"samples": len(samples), "seconds": dur,
            "rss_start_mb": rss[0], "rss_end_mb": rss[-1], "rss_max_mb": max(rss),
            "rss_growth_mb": round(growth, 1), "rss_slope_mb_per_min": round(growth / dur * 60, 2),
            "cpu_mean_pct": round(sum(cpu) / len(cpu), 1), "cpu_max_pct": max(cpu),
            "net_in_bytes": samples[-1].get("net_in_bytes", 0) - samples[0].get("net_in_bytes", 0),
            "net_out_bytes": samples[-1].get("net_out_bytes", 0) - samples[0].get("net_out_bytes", 0)}

def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__, file=sys.stderr); sys.exit(2)
    opt = {"--marks": None, "--rss-growth-mb": "30", "--idle-cpu": "20", "--net-mb": "5"}
    i = 1
    while i < len(a):
        if a[i] in opt and i + 1 < len(a):
            opt[a[i]] = a[i + 1]; i += 2
        else:
            i += 1
    samples = [json.loads(l) for l in open(a[0]) if l.strip()]
    live = [s for s in samples if s.get("pid")]
    gaps = len(samples) - len(live)
    stints, order = {}, []
    for s in live:
        if s["pid"] not in stints:
            order.append(s["pid"])
        stints.setdefault(s["pid"], []).append(s)
    stint_stats = [{"pid": pid, **stats(stints[pid])} for pid in order]

    windows = []
    if opt["--marks"]:
        marks = [json.loads(l) for l in open(opt["--marks"]) if l.strip()]
        opened = {}
        for m in marks:
            label = m.get("label", "")
            if label.startswith("begin:"):
                opened[label[6:]] = m["ts"]
            elif label.startswith("end:") and label[4:] in opened:
                name, t0, t1 = label[4:], opened.pop(label[4:]), m["ts"]
                inside = [s for s in live if t0 <= s["ts"] <= t1]
                st = stats(inside)
                if st:
                    windows.append({"name": name, **st})

    rss_thr, cpu_thr, net_thr = (float(opt["--rss-growth-mb"]), float(opt["--idle-cpu"]),
                                 float(opt["--net-mb"]) * 1024 * 1024)
    cands = []
    for w in windows:
        if w["rss_growth_mb"] >= rss_thr:
            cands.append({"kind": "suspected-leak", "window": w["name"],
                          "numbers": f"RSS {w['rss_start_mb']}→{w['rss_end_mb']} MB "
                                     f"(+{w['rss_growth_mb']} MB, {w['rss_slope_mb_per_min']} MB/min)"})
        if "idle" in w["name"] and w["cpu_mean_pct"] >= cpu_thr:
            cands.append({"kind": "sustained-cpu-while-idle", "window": w["name"],
                          "numbers": f"mean CPU {w['cpu_mean_pct']}% over {w['seconds']}s"})
        if w["net_in_bytes"] + w["net_out_bytes"] >= net_thr:
            cands.append({"kind": "excessive-network", "window": w["name"],
                          "numbers": f"{(w['net_in_bytes'] + w['net_out_bytes']) / 1048576:.1f} MB"})
    for st in stint_stats:
        if not windows and st["rss_growth_mb"] >= rss_thr:
            cands.append({"kind": "suspected-leak", "window": f"pid {st['pid']} (whole stint — no marks; low confidence)",
                          "numbers": f"RSS +{st['rss_growth_mb']} MB over {st['seconds']}s"})
    print(json.dumps({"stints": stint_stats, "gap_samples": gaps, "windows": windows,
                      "candidates": cands,
                      "thresholds": {"rss_growth_mb": rss_thr, "idle_cpu_pct": cpu_thr,
                                     "net_mb": net_thr / 1048576}}, indent=2))

if __name__ == "__main__":
    main()
