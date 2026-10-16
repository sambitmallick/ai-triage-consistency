#!/usr/bin/env python3
"""One factual question decided the timeout verdict: can a config carry Infinity?
Many runs reasoned that it can't, because "JSON can't". It can: JSON.parse('{"t": 1e999}').t === Infinity.

Labelled BY HAND (a regex over-counts: "JSON has no Infinity literal" is true; "so no client can send it"
is not). A run counts when it uses the claim to conclude that a real config/client can't produce Infinity.
Each label quotes the run's own words, from results/<run>/verdicts.json.
Usage:  python triage/false_claims.py"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LABELS = {
    "free-1": (False, "uses 'JSON cannot express Infinity' to argue Config is built in code, so Infinity IS plausible (verdict MATTERS)"),
    "free-2": (True,  "\"JSON cannot express Infinity, so only the fuzzer's number generator produces it\""),
    "free-3": (False, "found the 1e999 route"),
    "free-4": (True,  "\"Infinity is not expressible in JSON, so a config loaded from env/JSON can never carry it\""),
    "free-5": (False, "-"),
    "ev-1":   (False, "found the 1e999 route"),
    "ev-2":   (False, "found the 1e999 route"),
    "ev-3":   (True,  "CLAIM \"JSON cannot carry Infinity\" -- probe printed JSON.stringify -> null, JSON.parse('Infinity') throws, Number('1e999') -> Infinity; VERIFIED"),
    "ev-4":   (False, "-"),
    "ev-5":   (False, "-"),
    "rb-1":   (False, "found the 1e999 route"),
    "rb-2":   (False, "-"),
    "rb-3":   (True,  "real_clients=no: \"...and Infinity is not expressible in JSON\""),
    "rb-4":   (True,  "real_clients=no: \"JSON cannot carry Infinity (JSON.stringify ... emits null, probed) ... a well-behaved client cannot produce this value\""),
    "rb-5":   (True,  "real_clients=no: \"JSON cannot transport Infinity ... so only an in-process caller could supply it\""),
}
print("Can a config parsed from JSON carry Infinity?   JSON.parse('{\"t\":1e999}').t  ->  Infinity\n")
for run, (false, quote) in LABELS.items():
    print(f"{run:7} {'FALSE CLAIM' if false else 'ok':12} {quote}")
print()
for mode in ("free", "ev", "rb"):
    n = sum(f for r, (f, _) in LABELS.items() if r.startswith(mode + "-"))
    print(f"{ {'free': 'free', 'ev': 'evidence', 'rb': 'rubric'}[mode]:9} used the false claim in {n} of 5 runs")
print("\nev-3's claim PASSED the harness's probe check: the probe tested Number('1e999'), not JSON.parse.")
