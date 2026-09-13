#!/usr/bin/env python3
"""qa.py — client for the QADriver XCUITest server (the ios-xcuitest backend
of the qa-loop driver contract; see QADriver.swift for the command list).

    python3 qa.py <udid> <command...>        # one command
    python3 qa.py <udid> --batch -            # one command per stdin line
    python3 qa.py <udid> --alive              # is the driver serving?

Examples:
    qa.py $U launch MYAPP_TODAY_OVERRIDE=2026-08-15
    qa.py $U tap 279 175
    qa.py $U shot /abs/path/evidence.png
    qa.py $U labels texts Checkout
    qa.py $U find daily.play
    qa.py $U rotate landscapeLeft
Prints the driver's reply ("OK ..." / "ERR ..."). Exit code 2 when the driver
is not serving (run start.sh <udid> <bundle-id>), 1 on ERR, 0 on OK.
"""
import os, sys, time

def root(udid): return f"/private/tmp/qa-driver/{udid}"

def alive(udid, max_age=120.0):
    p = root(udid) + "/alive"
    try: return time.time() - os.path.getmtime(p) < max_age
    except OSError: return False

def send(udid, cmd, timeout=None):
    r = root(udid)
    os.makedirs(r + "/cmd", exist_ok=True); os.makedirs(r + "/out", exist_ok=True)
    seq = int(time.time() * 1000)
    while os.path.exists(f"{r}/cmd/{seq}.txt") or os.path.exists(f"{r}/out/{seq}.txt"): seq += 1
    tmp = f"{r}/cmd/{seq}.tmp"
    with open(tmp, "w") as fh: fh.write(cmd + "\n")
    os.replace(tmp, f"{r}/cmd/{seq}.txt")
    if timeout is None:
        timeout = 90
        if cmd.startswith("sleep "):
            try: timeout = float(cmd.split()[1]) + 30
            except ValueError: pass
    out = f"{r}/out/{seq}.txt"
    t0 = time.time()
    while time.time() - t0 < timeout:
        if os.path.exists(out):
            with open(out) as fh: res = fh.read()
            os.remove(out)
            return res
        time.sleep(0.05)
    try: os.remove(f"{r}/cmd/{seq}.txt")
    except OSError: pass
    return f"ERR timeout after {timeout}s waiting for the driver (alive={alive(udid)})"

def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(2)
    udid = sys.argv[1]
    if sys.argv[2] == "--alive":
        print("alive" if alive(udid) else "not serving"); sys.exit(0 if alive(udid) else 2)
    if not alive(udid):
        print(f"ERR driver not serving on {udid} — run: bash start.sh {udid} <bundle-id>"); sys.exit(2)
    cmds = [l.strip() for l in sys.stdin if l.strip()] if sys.argv[2] == "--batch" else [" ".join(sys.argv[2:])]
    rc = 0
    for c in cmds:
        res = send(udid, c)
        print(res if len(cmds) == 1 else f"> {c}\n{res}")
        if not res.startswith("OK"):
            rc = 1
            if len(cmds) > 1: break
    sys.exit(rc)

if __name__ == "__main__": main()
