#!/usr/bin/env python3
"""Compare triage runs: the same evidence, N runs. Do the verdicts hold?
Usage:  python triage/compare.py <label> <run-dir> [<run-dir> ...]
Each run-dir holds review/verdicts.json (and, for evidence/rubric runs, review/verdicts.harness.json)."""
import json, sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
label, dirs = sys.argv[1], [Path(d) for d in sys.argv[2:]]
EVIDENCE = (Path(__file__).resolve().parent / "evidence.txt").read_text(encoding="utf-8")
import re
HEADINGS = re.findall(r"^\[(\d+)\] (.+)$", EVIDENCE, flags=re.M)


def verdicts(d: Path) -> dict:
    h = d / "review" / "verdicts.harness.json"
    if h.exists():
        computed = json.loads(h.read_text(encoding="utf-8")).get("computed")
        if computed:
            return computed
    p = d / "review" / "verdicts.json"
    if not p.exists():
        return {}
    return {g["heading"]: g.get("verdict", "?") for g in json.loads(p.read_text(encoding="utf-8"))["groups"]}


runs = [verdicts(d) for d in dirs]
done = [r for r in runs if r]
print(f"{label}: {len(done)} of {len(runs)} runs produced verdicts\n")
print(f"{'group':58} " + " ".join(f"r{i + 1:<6}" for i in range(len(runs))) + " agree")
unanimous = 0
for count, h in HEADINGS:
    vs = [r.get(h, "-") for r in runs]
    top, k = Counter(v for v in vs if v != "-").most_common(1)[0] if any(v != "-" for v in vs) else ("-", 0)
    agree = k == len(done) and len(done) > 0
    unanimous += agree
    short = f"[{count}] {h}"[:57]
    print(f"{short:58} " + " ".join(f"{v[:7]:<7}" for v in vs) + f" {'yes' if agree else f'{k}/{len(done)}'}")
print(f"\nunanimous on {unanimous} of {len(HEADINGS)} groups")
