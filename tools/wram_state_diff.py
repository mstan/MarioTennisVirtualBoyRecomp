#!/usr/bin/env python3
"""wram_state_diff.py — find WRAM bytes that encode a game sub-state.

A sub-state byte is one that is STABLE while the game sits in a given state but
DIFFERS between states (e.g. change-service vs rally vs results). A naive diff
of two arbitrary frames is useless: WRAM is full of per-frame volatile bytes
(ball position, animation/RNG/timer counters) that change regardless of state.
This tool filters those out by capturing MULTIPLE snapshots per state and
keeping only bytes that are constant across every snapshot of a state — then
reports the bytes whose constant value differs between states.

It talks to the runtime/oracle TCP debug server (read_ram), so it works against
whichever process is at the state of interest. It does not arm anything: each
snapshot is a full read of the always-live WRAM at capture time.

Workflow (capture each reproducible state, then diff):
    # at the change-service screen:
    python tools/wram_state_diff.py capture 4390 change_svc .tmp/states -n 5
    # drive into a rally, then:
    python tools/wram_state_diff.py capture 4390 rally      .tmp/states -n 5
    # (later, after the user plays to a game end:)
    python tools/wram_state_diff.py capture 4390 results    .tmp/states -n 5
    # find discriminators across all captured states:
    python tools/wram_state_diff.py diff .tmp/states change_svc rally results

`diff` prints each WRAM address that is constant within every state's snapshots
and not all-equal across states, with the per-state value — ready to drop into
a recolor `detect.ram` predicate (addr 0x0500XXXX).
"""
from __future__ import annotations
import json, os, socket, sys, time

WRAM_BASE = 0x05000000
WRAM_SIZE = 0x00010000   # 64 KB
CHUNK     = 4096


def _cmd(port, c, **kw):
    req = {"cmd": c, "id": 1}; req.update(kw)
    with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
        s.sendall((json.dumps(req) + "\n").encode())
        data = b""
        while not data.endswith(b"\n"):
            ch = s.recv(65536)
            if not ch:
                break
            data += ch
    return json.loads(data.decode())


def dump_wram(port):
    buf = bytearray()
    for base in range(WRAM_BASE, WRAM_BASE + WRAM_SIZE, CHUNK):
        r = _cmd(port, "read_ram", addr="0x%08X" % base, len=CHUNK)
        buf += bytes.fromhex(r["hex"])
    return bytes(buf)


def capture(port, label, outdir, n, interval):
    os.makedirs(outdir, exist_ok=True)
    for i in range(n):
        snap = dump_wram(port)
        path = os.path.join(outdir, "%s_%02d.bin" % (label, i))
        with open(path, "wb") as f:
            f.write(snap)
        print("captured", path, len(snap), "bytes")
        if i < n - 1:
            time.sleep(interval)


def _load_group(outdir, label):
    snaps = []
    i = 0
    while True:
        path = os.path.join(outdir, "%s_%02d.bin" % (label, i))
        if not os.path.exists(path):
            break
        with open(path, "rb") as f:
            snaps.append(f.read())
        i += 1
    if not snaps:
        sys.exit("no snapshots for label %r in %s (run capture first)" % (label, outdir))
    return snaps


def diff(outdir, labels):
    groups = {lab: _load_group(outdir, lab) for lab in labels}
    size = min(len(s) for snaps in groups.values() for s in snaps)

    # For each state, a byte offset is "stable" if it has one value across all
    # that state's snapshots; record that value (or None if it jitters).
    stable = {}
    for lab, snaps in groups.items():
        vals = bytearray(snaps[0][:size])
        ok = bytearray([1]) * size
        for s in snaps[1:]:
            for off in range(size):
                if ok[off] and s[off] != vals[off]:
                    ok[off] = 0
        stable[lab] = (vals, ok)

    print("# states: " + ", ".join("%s(%d snaps)" % (l, len(groups[l])) for l in labels))
    print("# addr        " + "  ".join("%-10s" % l for l in labels))
    hits = 0
    for off in range(size):
        if not all(stable[lab][1][off] for lab in labels):
            continue   # volatile in at least one state -> not a clean sub-state byte
        vals = [stable[lab][0][off] for lab in labels]
        if len(set(vals)) == 1:
            continue   # same value in every state -> not a discriminator
        hits += 1
        addr = WRAM_BASE + off
        print("0x%08X    " % addr +
              "  ".join("%-10s" % ("0x%02X" % v) for v in vals))
    print("# %d discriminator byte(s): stable within each state, differ across states" % hits)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    mode = sys.argv[1]
    if mode == "capture":
        port = int(sys.argv[2]); label = sys.argv[3]; outdir = sys.argv[4]
        n = 5; interval = 0.4
        rest = sys.argv[5:]
        if "-n" in rest:
            n = int(rest[rest.index("-n") + 1])
        if "-i" in rest:
            interval = float(rest[rest.index("-i") + 1])
        capture(port, label, outdir, n, interval)
    elif mode == "diff":
        outdir = sys.argv[2]; labels = sys.argv[3:]
        if len(labels) < 2:
            sys.exit("diff needs >=2 labels")
        diff(outdir, labels)
    else:
        sys.exit("unknown mode %r (capture|diff)" % mode)


if __name__ == "__main__":
    main()
