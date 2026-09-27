#!/usr/bin/env bash
# PreToolUse (Bash) read guard for the loops. Measured: 66% of a review
# loop's spend was shell output dumped into context — whole files, the full
# diff re-pulled per dispatch, unfiltered test logs. Active ONLY while a loop
# phase is in flight (pass loop dirs as args; default both). Denies the clear
# cases with the fix in the message; the agent re-issues a windowed or
# filtered command and loses nothing.
set -euo pipefail
dirs=("$@"); [ ${#dirs[@]} -eq 0 ] && dirs=(.review-loop .qa-loop)
active=""; phase=""
for d in "${dirs[@]}"; do
  [ -f "$d/.phase" ] || continue
  p="$(cat "$d/.phase")"
  case "$p" in round*|seed*) active="$d"; phase="$p" ;; esac
done
if [ -z "$active" ]; then cat >/dev/null 2>&1 || true; exit 0; fi
input="$(cat 2>/dev/null || true)"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 - "$input" "$active" "$phase" "$here" <<'PYEOF' || exit 2
import json, os, re, sys
raw, loop, phase = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    cmd = json.loads(raw).get("tool_input", {}).get("command", "") or ""
except Exception:
    sys.exit(0)

def deny(msg, rule="other"):
    # Telemetry: WHICH rule fired, never the command (it names host paths).
    # A rule that fires forty times in a run is a prompt problem worth
    # knowing about; one that never fires is a rule worth questioning.
    try:
        sys.path.insert(0, sys.argv[4])
        import field_log
        field_log.anomaly(loop, "read-guard-denied", rule, source="read_guard.sh")
    except Exception:
        pass
    print("read_guard: " + msg, file=sys.stderr)
    sys.exit(1)

def nlines(path):
    try:
        with open(path, "rb") as fh:
            return sum(1 for _ in fh)
    except Exception:
        return 0

# Match COMMAND POSITIONS, not command text: a heredoc that merely wrote an
# xcodebuild string into a JSON brief was denied as an "unfiltered test run"
# (measured), which trains agents to route around the guard. Heredoc bodies
# and single-quoted strings are data — strip them before any pattern runs.
def strip_data(c):
    c = re.sub(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?^\s*\2\s*$", "<<HEREDOC",
               c, flags=re.S | re.M)
    c = re.sub(r"'[^']*'", "''", c)
    return c
cmd = strip_data(cmd)
CMD_START = r"(?:^|[;&|(]\s*|\$\(\s*|\bthen\s+|\bdo\s+|\bexec\s+|\btime\s+)"

filtered = bool(re.search(r"\|\s*(grep|rg|head|tail|sed|awk|wc|cut|sort|uniq|xcpretty|xcbeautify|tee|python3|jq)\b", cmd)) \
    or bool(re.search(r"(?<![<>])>\s*[^\s&|]", cmd))

if not filtered:
    m = re.search(r"(?:^|[;&|]\s*)cat\s+([^\s;&|<>]+)", cmd)
    if m:
        n = nlines(m.group(1))
        if n > 200:
            deny(f"`cat` of a {n}-line file dumps it all into context. Locate with "
                 f"`grep -n`, then read a window of <=120 lines: `sed -n 'A,Bp' "
                 f"{m.group(1)}` or the Read tool with offset/limit.",
                 f"cat of a {n}-line file")
    m = re.search(r"\bhead\s+(?:-n\s*|-)(\d+)", cmd)
    if m and int(m.group(1)) > 200:
        deny(f"`head -{m.group(1)}` puts {m.group(1)} lines into context. Read <=120 "
             f"lines per call; locate with `grep -n` first.",
             f"head window of {m.group(1)} lines")
    m = re.search(r"\bsed\s+-n\s+'?\"?(\d+),(\d+)p", cmd)
    if m and int(m.group(2)) - int(m.group(1)) > 200:
        deny(f"`sed -n {m.group(1)},{m.group(2)}p` is a {int(m.group(2)) - int(m.group(1))}-line "
             f"window. Keep windows <=120 lines; locate with `grep -n` first.",
             f"sed window of {int(m.group(2)) - int(m.group(1))} lines")

if re.search(CMD_START + r"(?:xcrun\s+)?xcodebuild\b[^|;&]*\btest\b|" + CMD_START + r"swift\s+test\b", cmd) and not filtered:
    deny("full test output lands in context (one unfiltered app-suite run measured at "
         "~150K tokens). Append `2>&1 | grep -E 'error:|failed|Executed|passed|Test Suite'`, "
         "or redirect to a file and grep it. Run the scoped verify_cmd in rounds; the full "
         "suite runs once, at closeout.", "unfiltered test run")

m = re.match(r"round-(\d+)-", phase)
if m and re.search(CMD_START + r"git\s+(diff|show)\b", cmd) and not filtered \
        and not re.search(r"--(stat|numstat|name-only|shortstat)\b", cmd) \
        and not re.search(r"\s--\s+\S", cmd):
    n = m.group(1)
    dfile = os.path.join(loop, "briefs", f"round-{n}.diff")
    if os.path.exists(dfile):
        deny(f"the round diff is already on disk. Read `{os.path.join(loop, 'briefs', f'round-{n}.stat')}` "
             f"first, then per-file hunks from `{dfile}` (`grep -n '^diff --git' {dfile}` gives "
             f"offsets; `sed -n` a window). Re-pulling the whole diff costs ~30-60K tokens each time; "
             f"a single-file diff is fine: `git diff <range> -- <path>`.",
             "whole-diff re-pull")
PYEOF
exit 0
