# ios-xcuitest — a qa-loop driver backend

A scriptable XCUITest (`Sources/QADriver.swift`) that runs as a long-lived
server on ONE simulator and executes commands a client writes to
`/private/tmp/qa-driver/<udid>/cmd/`. It exists because the MCP
simulator-control tool needs a per-device access grant that only a human at
the keyboard can give; the driver needs none, and it can do things the MCP
tool cannot (launch with an environment, rotate the device, query
accessibility identifiers, dump every visible label in one call — a field
loop using it cut screenshot volume 3.4×).

The target app is a PARAMETER. Nothing app-specific lives in this backend:
app quirks belong in the target repo's `HARNESS_NOTES.md`.

## Setup (the skill does this)

Copy this directory into the target repo — builds must never happen inside
the plugin cache (a plugin update sweeps it away):

```bash
cp -R "${CLAUDE_PLUGIN_ROOT}/drivers/ios-xcuitest/" .qa-loop/driver/
bash .qa-loop/driver/start.sh <udid> <app-bundle-id>   # build once (cached in dd/), serve in background
python3 .qa-loop/driver/qa.py <udid> <cmd…>            # one command; prints "OK …" or "ERR …"
python3 .qa-loop/driver/qa.py <udid> --alive           # is it serving?
bash .qa-loop/driver/stop.sh <udid>
```

## The driver contract

These verbs are the platform-neutral contract the qa loop's tester prompts
speak. Any future backend (`android-appium/`, `web-playwright/`) implements
this same table against its own platform; everything above the driver line
stays unchanged. Coordinates are DEVICE POINTS in the app's frame; replies
are `OK …` / `ERR …`; element queries use accessibility identifiers/labels.

| command | what it does |
|---|---|
| `launch [K=V …]` | (re)launch the app with that environment, e.g. `launch MYAPP_TODAY_OVERRIDE=2026-08-15` |
| `activate` / `terminate` / `home` / `state` / `frame` | lifecycle; `terminate`+`launch` = the real relaunch path |
| `tap X Y`, `doubletap X Y`, `press X Y SECS` | coordinate touches |
| `drag X1 Y1 X2 Y2 [HOLD]`, `swipe …` | press-hold then drag (hold 0.15 s / 0.05 s default) — drives manual DragGestures |
| `dragslow X1 Y1 X2 Y2 VELOCITY HOLD` | drag at a set points/sec |
| `type TEXT`, `key return\|delete\|space\|tab\|escape`, `selectall` | keyboard into the focused field |
| `shot /abs/path.png` | full-resolution screenshot written to the HOST path |
| `find ID`, `findall ID`, `wait ID [SECS]` | element by accessibility identifier: exists / hittable / frame / label / value |
| `tapid ID`, `tapoffset ID DX DY`, `tapbtn LABEL`, `taptext LABEL`, `btn LABEL`, `text LABEL` | tap or inspect by identifier / button label / static-text label; `tapoffset` for stacked elements whose centre lies on a sibling |
| `labels [texts\|buttons\|textfields\|images\|cells\|any] [SUBSTRING]` | every matching element's `[x,y,w,h] #id label`, ONE snapshot (≈0.3 s) — the cheapest assertion there is |
| `alert` | the frontmost alert's title, texts and buttons with frames |
| `tree [DEPTH]` | indented accessibility hierarchy |
| `rotate portrait\|landscapeLeft\|landscapeRight`, `orientation` | device orientation |
| `sleep SECS`, `ping`, `quit` | |

XCUITest "issues" (not hittable, snapshot failed) never kill the server:
they come back appended to the reply as `issues=…`. One server per
simulator; parallel workers never share a directory. The server exits by
itself after 5 h — `start.sh` is idempotent, call it again.

## Files

- `Sources/QADriver.swift` — the server (reads the app bundle id from
  `QA_DRIVER_BUNDLE_ID`, which `start.sh` passes via xcodebuild's
  `TEST_RUNNER_` prefix).
- `qa.py` — the only client you should use (`--batch -` for one command per
  stdin line).
- `start.sh <udid> <bundle-id>` / `stop.sh <udid>` — lifecycle. Build is
  cached in `dd/` next to the scripts (never shipped, never committed — the
  loop's `.gitignore` allowlist ignores it by default).
- `QADriver.xcodeproj` — pre-generated so xcodegen is not required;
  `project.yml` regenerates it if you ever edit the target.

Provenance: generalized from a field-built driver in the Causeway qa loop
(2026-09-09 run) that produced 130 screenshots in 3,161 requests vs 440 the
loop before, and removed the per-device grant step from autonomous runs.
