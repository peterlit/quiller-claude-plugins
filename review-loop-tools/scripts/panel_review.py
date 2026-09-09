#!/usr/bin/env python3
"""Run the multi-provider review panel: external finders whose candidates a
blind verifier adjudicates before anything reaches the ledger.

Usage:
  panel_review.py probe [<panel.json>] [--smoke]
  panel_review.py run <loop-dir> <round> [--range <a..b>]

probe: report which lanes are installed and whether their auth looks usable.
Fast checks by default (binaries, credential files, env vars, the ollama
daemon); --smoke additionally makes one tiny live call per remote lane so
"configured" means "works right now" — run it at the setup gate, because a
lane that needs an interactive browser login cannot recover mid-loop.

run: read <loop-dir>/panel.json, build one diff-only prompt from the round's
briefs/round-<N>.stat + .diff plus the shared template, and run every enabled
lane in parallel with a per-lane timeout. Each lane writes
fragments/round-<N>-<lane>.candidates.json (top 10 findings by confidence —
the flood cap) and its raw output to fragments/round-<N>-<lane>.raw.txt for
debugging. A lane that times out, errors, or lacks consent is SKIPPED with a
note — the panel never blocks a round. Remote lanes (codex, gemini) run only
when panel.json records consent.remote_lanes_approved: true.

Phase 1 is diff-only for every lane: the model sees the stat and the diff,
not the repo. Candidates carry no IDs and no status — the panel-verifier
agent verifies them against the code and only the skeptical-reviewer (the
chair) ever writes the ledger fragment.
"""
import concurrent.futures, json, os, re, shutil, subprocess, sys, urllib.error, urllib.request

SEVERITIES = {"blocker", "major", "minor"}
CAP = 10                      # top-N by confidence; the false-positive flood control
CHARS_PER_TOKEN = 4           # rough cap arithmetic for max_diff_tokens
OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

def template_path():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "..", "templates", "panel-reviewer.md")

def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)

# ---------------------------------------------------------------- probe ----

def probe(args):
    smoke = "--smoke" in args
    args = [a for a in args if a != "--smoke"]
    panel = load_json(args[0]) if args else None
    out = {}

    codex = shutil.which("codex")
    if not codex:
        out["codex"] = {"installed": False}
    else:
        st = {"installed": True, "auth": "unknown"}
        try:
            r = subprocess.run(["codex", "login", "status"], capture_output=True,
                               text=True, timeout=20)
            st["auth"] = "ok" if r.returncode == 0 else "needs-login"
            st["auth_detail"] = (r.stdout or r.stderr).strip().splitlines()[:1]
        except Exception as e:
            st["auth_detail"] = [f"probe failed: {e}"]
        if smoke and st["auth"] == "ok":
            try:
                r = subprocess.run(["codex", "exec", "--skip-git-repo-check",
                                    "reply with the single word ok"],
                                   capture_output=True, text=True, timeout=120)
                st["smoke"] = "ok" if r.returncode == 0 else f"failed: {(r.stderr or r.stdout).strip()[:200]}"
            except Exception as e:
                st["smoke"] = f"failed: {e}"
        out["codex"] = st

    gemini = shutil.which("gemini")
    if not gemini:
        out["gemini"] = {"installed": False}
    else:
        st = {"installed": True}
        if os.environ.get("GEMINI_API_KEY"):
            st["auth"] = "api-key"
        elif os.environ.get("GOOGLE_GENAI_USE_VERTEXAI") == "true":
            st["auth"] = "vertex-adc"
        elif os.path.exists(os.path.expanduser("~/.gemini/oauth_creds.json")):
            # Free-tier OAuth may allow training on inputs — the gate must say so.
            st["auth"] = "oauth (check data-training terms before private code)"
        else:
            st["auth"] = "needs-login"
        if smoke and st["auth"] != "needs-login":
            try:
                r = subprocess.run(["gemini", "-p", "reply with the single word ok"],
                                   capture_output=True, text=True, timeout=120)
                st["smoke"] = "ok" if r.returncode == 0 else f"failed: {(r.stderr or r.stdout).strip()[:200]}"
            except Exception as e:
                st["smoke"] = f"failed: {e}"
        out["gemini"] = st

    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as resp:
            models = [m.get("name") for m in json.load(resp).get("models", [])]
        out["local"] = {"installed": True, "auth": "none-needed", "models": models}
    except Exception:
        out["local"] = {"installed": False,
                        "hint": "ollama daemon not reachable at " + OLLAMA_URL}

    if panel:
        for lane in panel.get("lanes", []):
            name = lane.get("name")
            if name in out:
                out[name]["configured"] = True
    print(json.dumps(out, indent=2))

# ----------------------------------------------------------------- run -----

def build_prompt(loop, rnd, max_diff_tokens):
    with open(template_path(), encoding="utf-8") as fh:
        tmpl = fh.read()
    stat = open(os.path.join(loop, "briefs", f"round-{rnd}.stat"), encoding="utf-8").read()
    diff_path = os.path.join(loop, "briefs", f"round-{rnd}.diff")
    cap_chars = max_diff_tokens * CHARS_PER_TOKEN
    with open(diff_path, encoding="utf-8", errors="replace") as fh:
        diff = fh.read(cap_chars + 1)
    truncated = len(diff) > cap_chars
    if truncated:
        # No silent caps: cut at the last complete file boundary and say so.
        cut = diff.rfind("\ndiff --git", 0, cap_chars)
        diff = diff[:cut if cut > 0 else cap_chars]
    note = ("\n\n[NOTE: the diff was TRUNCATED at the size cap; the stat above "
            "lists every changed file, including ones whose hunks you cannot "
            "see. Do not file findings about files you cannot see.]"
            if truncated else "")
    return (f"{tmpl}\n\n## DIFF STAT\n```\n{stat}\n```\n"
            f"## DIFF\n```diff\n{diff}\n```{note}"), truncated

def extract_json(text):
    """Models wrap JSON in prose or ``` fences; take the outermost object."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None

def sanitize(obj, lane):
    """Keep only well-formed candidates; sort by confidence; cap at CAP."""
    if not isinstance(obj, dict) or not isinstance(obj.get("findings"), list):
        return None
    keep = []
    for f in obj["findings"]:
        if not isinstance(f, dict):
            continue
        if not f.get("claim") or f.get("severity") not in SEVERITIES:
            continue
        ev = f.get("evidence")
        if not (isinstance(ev, list) and ev):
            continue
        try:
            conf = max(0.0, min(1.0, float(f.get("confidence", 0.5))))
        except (TypeError, ValueError):
            conf = 0.5
        keep.append({"claim": str(f["claim"])[:600],
                     "evidence": [str(e)[:200] for e in ev][:8],
                     "severity": f["severity"],
                     "confidence": conf,
                     "area": str(f.get("area", ""))[:80]})
    keep.sort(key=lambda f: -f["confidence"])
    return {"lane": lane, "filed": len(keep[:CAP]),
            "overflow_dropped": max(0, len(keep) - CAP),
            "findings": keep[:CAP]}

def run_codex(lane, prompt, repo, timeout):
    out_file = lane["_out_base"] + ".last-message.txt"
    cmd = ["codex", "exec", "--sandbox", "read-only", "--skip-git-repo-check",
           "--output-last-message", out_file]
    if lane.get("model"):
        cmd += ["-m", lane["model"]]
    cmd.append("-")
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                       timeout=timeout, cwd=repo)
    if os.path.exists(out_file):
        with open(out_file, encoding="utf-8") as fh:
            return fh.read(), r
    return r.stdout, r

def run_gemini(lane, prompt, repo, timeout):
    cmd = ["gemini"]
    if lane.get("model"):
        cmd += ["-m", lane["model"]]
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                       timeout=timeout, cwd=repo)
    return r.stdout, r

def run_ollama(lane, prompt, repo, timeout):
    body = json.dumps({"model": lane.get("model", "qwen3-coder:30b"),
                       "prompt": prompt, "stream": False,
                       "format": "json"}).encode()
    req = urllib.request.Request(f"{OLLAMA_URL}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp).get("response", ""), None

def run_cmd(lane, prompt, repo, timeout):
    """Generic lane: any command that reads the prompt on stdin and prints
    the candidates JSON on stdout. The escape hatch for CLIs we don't know,
    and the fixture hook for testing the panel plumbing offline."""
    r = subprocess.run(lane["cmd"], shell=True, input=prompt, capture_output=True,
                       text=True, timeout=timeout, cwd=repo)
    return r.stdout, r

RUNNERS = {"codex": run_codex, "gemini": run_gemini, "ollama": run_ollama,
           "cmd": run_cmd}

def run_lane(lane, loop, rnd, repo, consent_remote):
    name, kind = lane.get("name"), lane.get("type", lane.get("name"))
    frag_dir = os.path.join(loop, "fragments")
    os.makedirs(frag_dir, exist_ok=True)
    base = os.path.join(frag_dir, f"round-{rnd}-{name}")
    lane["_out_base"] = base
    if kind in ("codex", "gemini") and not consent_remote:
        return {"lane": name, "status": "skipped",
                "note": "no remote-lane consent recorded in panel.json"}
    runner = RUNNERS.get(kind)
    if not runner:
        return {"lane": name, "status": "skipped", "note": f"unknown type '{kind}'"}
    prompt, truncated = build_prompt(loop, rnd, int(lane.get("max_diff_tokens", 32000)))
    timeout = int(lane.get("timeout_s", 600))
    try:
        raw, proc = runner(lane, prompt, repo, timeout)
    except subprocess.TimeoutExpired:
        return {"lane": name, "status": "timeout", "timeout_s": timeout}
    except (urllib.error.URLError, OSError) as e:
        return {"lane": name, "status": "error", "note": str(e)[:200]}
    with open(base + ".raw.txt", "w", encoding="utf-8") as fh:
        fh.write(raw or "")
    if proc is not None and proc.returncode != 0:
        return {"lane": name, "status": "error",
                "note": (proc.stderr or "nonzero exit").strip()[:200]}
    cands = sanitize(extract_json(raw or ""), name)
    if cands is None:
        return {"lane": name, "status": "error",
                "note": f"no parseable candidates JSON (raw kept at {base}.raw.txt)"}
    if truncated:
        cands["diff_truncated"] = True
    out_path = base + ".candidates.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(cands, fh, indent=2)
        fh.write("\n")
    return {"lane": name, "status": "ok", "filed": cands["filed"],
            "overflow_dropped": cands["overflow_dropped"], "candidates": out_path}

def run(args):
    if len(args) < 2:
        print("usage: panel_review.py run <loop-dir> <round>", file=sys.stderr)
        sys.exit(2)
    loop, rnd = args[0], args[1]
    panel = load_json(os.path.join(loop, "panel.json"))
    if not panel or not panel.get("lanes"):
        print(json.dumps({"status": "no-panel", "note": "no panel.json or no lanes"}))
        return
    repo = os.path.dirname(os.path.abspath(loop))
    consent = bool((panel.get("consent") or {}).get("remote_lanes_approved"))
    for p in (f"round-{rnd}.stat", f"round-{rnd}.diff"):
        if not os.path.exists(os.path.join(loop, "briefs", p)):
            print(f"panel_review: missing briefs/{p} — run the diff verb first",
                  file=sys.stderr)
            sys.exit(1)
    lanes = panel["lanes"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(lanes)) as ex:
        results = list(ex.map(lambda l: run_lane(l, loop, rnd, repo, consent), lanes))
    ok = [r for r in results if r["status"] == "ok"]
    # rnd may be a label ("final" for the post-stop pass), not just a number.
    print(json.dumps({"round": int(rnd) if str(rnd).isdigit() else rnd,
                      "lanes": results,
                      "candidates_files": [r["candidates"] for r in ok]}, indent=2))

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("probe", "run"):
        print(__doc__.strip().splitlines()[3].strip() + "\n" +
              __doc__.strip().splitlines()[4].strip(), file=sys.stderr)
        sys.exit(2)
    (probe if sys.argv[1] == "probe" else run)(sys.argv[2:])

if __name__ == "__main__":
    main()
