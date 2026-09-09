#!/usr/bin/env bash
# Loop-state git hygiene check — ADVISORY ONLY, always exits 0.
# Usage: hygiene_check.sh <loop-dir>            (e.g. .review-loop)
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
set -u
dir="${1:-}"
[ -n "$dir" ] && [ -d "$dir" ] || exit 0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

issues=0
say() { issues=$((issues+1)); echo "hygiene($dir): $*"; }

tracked="$(git ls-files -- "$dir" 2>/dev/null || true)"

# 1. Scratch paths in the index (any depth — archive/<name>/fragments too).
if [ -n "$tracked" ]; then
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    if printf '%s\n' "$f" | grep -qE '(^|/)(evidence|fragments|briefs|scratch|__pycache__)( [0-9]+)?/|(^|/)\.phase$|\.pyc$'; then
      say "scratch tracked: $f — fix: git rm --cached '$f'"
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

[ "$issues" -eq 0 ] && echo "hygiene($dir): clean"
exit 0
