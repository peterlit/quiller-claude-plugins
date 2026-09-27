#!/usr/bin/env bash
# Loop-state git hygiene check — ADVISORY ONLY, always exits 0.
# Usage: hygiene_check.sh <loop-dir> [--restore]      (e.g. .review-loop)
# Principle: conclusions in git, evidence and scratch on disk. Reports, never
# fixes (the orchestrator acts on the output — git rm --cached strays, rename
# Finder duplicates back to their plain names; never delete from disk):
#   - tracked files under scratch dirs (evidence/ fragments/ briefs/ scratch/
#     __pycache__/) or a tracked .phase / *.pyc (measured: a Finder-duplicated
#     "fragments 2/" with 38 scratch files and a .pyc were committed in one
#     host repo before anyone noticed)
#   - Finder/iCloud-duplicate names ("X 2.json", "fragments 2") in the index
#     or on disk — when the plain-named sibling is missing, the duplicate IS
#     the real file under a name the loop never reads
#   - tracked files over 256KB (conclusions are small; big blobs are evidence)
#   - a missing or denylist-style .gitignore (the allowlist starts with "*")
#   - tracked files MISSING from disk with no " N" twin to explain them — a
#     conclusion that vanished under some other name (a "conflicted copy",
#     a rename the duplicate pattern does not match)
# --restore repairs the one unambiguous case and nothing else: a " N"
# duplicate whose plain name is missing, and which is the ONLY duplicate of
# that name, is moved back (mv -n: never overwrites, never deletes). Both
# field agents did exactly this by hand in three separate runs. Run it once
# per repo after a sync outage, a sync toggle, or a restore (measured: one
# accidental iCloud Drive off/on renamed 40 files across a source tree,
# committed archive conclusions among them).
# Violations of the first three kinds are also recorded as anomalies
# (feedback/anomalies.jsonl, KIND only — names stay in this output): a
# .gitignore that is missing at bootstrap is the normal first-run state.
set -u
dir="${1:-}"
restore=0
[ "${2:-}" = "--restore" ] && restore=1
[ -n "$dir" ] && [ -d "$dir" ] || exit 0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

issues=0
scratch=0; dups=0; large=0; gone=0; restored=0
say() { issues=$((issues+1)); echo "hygiene($dir): $*"; }

tracked="$(git ls-files -- "$dir" 2>/dev/null || true)"

# 1. Scratch paths in the index (any depth — archive/<name>/fragments too).
if [ -n "$tracked" ]; then
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    if printf '%s\n' "$f" | grep -qE '(^|/)(evidence|fragments|briefs|scratch|__pycache__)( [0-9]+)?/|(^|/)\.phase$|\.pyc$'; then
      say "scratch tracked: $f — fix: git rm --cached '$f'"
      scratch=$((scratch+1))
    fi
  done <<EOF
$tracked
EOF
fi

# 2. Finder-duplicate names (" N" before an optional extension), in the index
#    and on disk. evidence/ is skipped on disk: untracked, huge, and screenshot
#    names legitimately carry digits.
dupes="$( { printf '%s\n' "$tracked"; \
            find "$dir" \( -name evidence -o -name scratch \) -prune -o -print 2>/dev/null; } \
          | grep -E '(^|/)[^/]* [0-9]+(\.[A-Za-z0-9]+)?$' | sort -u || true)"
if [ -n "$dupes" ]; then
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    canon="$(printf '%s\n' "$f" | sed -E 's/ [0-9]+(\.[A-Za-z0-9]+)?$/\1/')"
    dups=$((dups+1))
    if [ "$restore" -eq 1 ] && [ -e "$f" ] && [ ! -e "$canon" ]; then
      # Only when this is the SOLE duplicate of its name: with "X 2" and
      # "X 3" both present, which one is real is a human's call.
      rivals="$(printf '%s\n' "$dupes" | while IFS= read -r g; do
                  [ -n "$g" ] || continue
                  c="$(printf '%s\n' "$g" | sed -E 's/ [0-9]+(\.[A-Za-z0-9]+)?$/\1/')"
                  [ "$c" = "$canon" ] && echo x
                done | wc -l | tr -d '[:space:]')"
      if [ "${rivals:-0}" -eq 1 ] && mv -n "$f" "$canon" 2>/dev/null && [ -e "$canon" ] && [ ! -e "$f" ]; then
        echo "hygiene($dir): restored: '$f' -> '$canon'"
        restored=$((restored+1)); dups=$((dups-1))
        continue
      fi
    fi
    if [ -e "$canon" ]; then
      say "duplicate name: $f (plain-named '$canon' exists) — remove or merge the duplicate; never write to a space-suffixed name"
    else
      say "duplicate name: $f and '$canon' is MISSING — the duplicate is likely the real file; rename it back (mv), never delete"
    fi
  done <<EOF
$dupes
EOF
fi

# 3. Oversized tracked files.
if [ -n "$tracked" ]; then
  while IFS= read -r f; do
    [ -n "$f" ] && [ -f "$f" ] || continue
    sz="$(wc -c < "$f" | tr -d '[:space:]')"
    if [ "${sz:-0}" -gt 262144 ]; then
      say "large tracked file: $f (${sz} bytes > 256KB) — conclusions are small; evidence belongs on disk"
      large=$((large+1))
    fi
  done <<EOF
$tracked
EOF
fi

# 4. The .gitignore itself: default-closed allowlist, or warn.
gi="$dir/.gitignore"
if [ ! -f "$gi" ]; then
  say "no $gi — bootstrap writes the default-closed allowlist; anything unanticipated is tracked by default until it exists"
else
  first="$(grep -vE '^\s*(#|$)' "$gi" | head -1 | tr -d '[:space:]')"
  if [ "$first" != "*" ]; then
    say "$gi is a denylist (first rule: '${first}') — suggest upgrading to the shipped allowlist ('*', '!*/', then one negation per conclusion); do not overwrite it silently"
  fi
fi

# 5. Tracked files missing from disk. A " N" twin already reported above
#    explains its own missing name; what is left vanished some other way.
missing="$(git ls-files --deleted -- "$dir" 2>/dev/null || true)"
if [ -n "$missing" ]; then
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    [ -e "$f" ] && continue          # restored a moment ago
    base="${f##*/}"; d="$(dirname "$f")"
    twin="$(python3 - "$d" "$base" <<'PYEOF'
import os, re, sys
d, base = sys.argv[1], sys.argv[2]
stem, ext = os.path.splitext(base)
try:
    names = sorted(os.listdir(d))
except OSError:
    names = []
numbered = re.compile(re.escape(stem) + r" \d+" + re.escape(ext))
if any(numbered.fullmatch(n) for n in names):
    print("NUMBERED")            # the duplicate check already reported it
else:
    cands = [n for n in names if n != base and n.startswith(stem) and n.endswith(ext)]
    print(cands[0] if cands else "")
PYEOF
)"
    [ "$twin" = "NUMBERED" ] && continue
    gone=$((gone+1))
    if [ -n "$twin" ]; then
      say "tracked file missing: $f — '$d/$twin' may be it under another name; compare, then mv it back (never delete)"
    else
      say "tracked file missing: $f — no candidate beside it; restore it with: git checkout -- '$f'"
    fi
  done <<EOF
$missing
EOF
fi

note() {
  python3 "$here/field_log.py" anomaly "$dir" hygiene-violation "$1" \
    --source hygiene_check.sh --dedupe >/dev/null 2>&1 || true
}
[ "$gone" -gt 0 ] && note "$gone tracked file(s) missing from disk"
[ "$restored" -gt 0 ] && note "$restored Finder-duplicate name(s) restored by --restore"
[ "$scratch" -gt 0 ] && note "$scratch scratch path(s) tracked in git"
[ "$dups" -gt 0 ] && note "$dups Finder-duplicate name(s)"
[ "$large" -gt 0 ] && note "$large tracked file(s) over 256KB"

[ "$issues" -eq 0 ] && echo "hygiene($dir): clean"
exit 0
