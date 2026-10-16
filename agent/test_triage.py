#!/usr/bin/env python3
"""No model, no API call: the triage harness's parts, tested.  python agent/test_triage.py"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import triage as T  # noqa: E402

ok, n = 0, 0


def check(name, cond):
    global ok, n
    n += 1; ok += bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {name}")


# the evidence is frozen and complete
check("the frozen evidence has the 7 groups", len(T.HEADINGS) == 7)

# the policy: the decision lives in code
P = T.policy
check("signed off -> SIGNED OFF", P({"already_signed_off": True, "verdict_changes": True, "direction": "stricter"}) == "SIGNED OFF")
check("nothing accepted/rejected/stored differently -> NOISE", P({"verdict_changes": False, "stored_value_changes": False}) == "NOISE")
check("looser -> MATTERS, even if no real client sends it", P({"verdict_changes": True, "direction": "looser", "real_clients": "no"}) == "MATTERS")
check("stricter + real clients 'no' -> NOISE", P({"verdict_changes": True, "direction": "stricter", "real_clients": "no"}) == "NOISE")
check("stricter + real clients 'unknown' -> MATTERS", P({"verdict_changes": True, "direction": "stricter", "real_clients": "unknown"}) == "MATTERS")
check("stored value changes + real clients 'yes' -> MATTERS", P({"verdict_changes": False, "stored_value_changes": True, "direction": "none", "real_clients": "yes"}) == "MATTERS")

# the probe sandbox
out = T.run_probe('print(oracle.parseConfig({hosts:["2001:db8::1%eth0"]}).ok, main.parseConfig({hosts:["2001:db8::1%eth0"]}).ok)')
check("a probe sees the oracle and the merged build", out == "false true")
check("a probe can't require anything", "require is not defined" in T.run_probe('require("fs").writeFileSync("x","y")'))
check("a probe can't loop forever", "timed out" in T.run_probe("while(true){}"))

# the claim checker: the harness runs the probe, not the model
rep = T.PROJECT / T.REPORT
saved = rep.read_text(encoding="utf-8") if rep.exists() else None
rep.parent.mkdir(exist_ok=True)
def write(groups):
    rep.write_text(json.dumps({"groups": groups}), encoding="utf-8")
true_claim = {"claim": "zod 3 rejects 2001:db8::1%eth0", "probe": 'print(oracle.parseConfig({hosts:["2001:db8::1%eth0"]}).ok)', "expect": "false"}
false_claim = {"claim": "the merged build rejects it too", "probe": 'print(main.parseConfig({hosts:["2001:db8::1%eth0"]}).ok)', "expect": "false"}
try:
    write([{"heading": h, "verdict": "MATTERS", "why": "x", "claims": [true_claim]} for h in T.HEADINGS])
    good, msg, _ = T.check_verdicts("evidence")
    check("evidence mode: verified claims pass the gate", good)
    write([{"heading": h, "verdict": "MATTERS", "why": "x", "claims": [false_claim]} for h in T.HEADINGS])
    good, msg, _ = T.check_verdicts("evidence")
    check("evidence mode: a claim its own probe contradicts is refused", not good and "NOT VERIFIED" in msg)
    write([{"heading": h, "verdict": "MATTERS", "why": "x"} for h in T.HEADINGS])
    check("evidence mode: a verdict with no claims is refused", not T.check_verdicts("evidence")[0])
    check("free mode: the same file is accepted", T.check_verdicts("free")[0])
    write([{"heading": h, "verdict": "MATTERS", "why": "x"} for h in T.HEADINGS[:6]])
    check("a missing group is refused", "no entry" in T.check_verdicts("free")[1])
    ans = {"verdict_changes": True, "direction": "looser", "stored_value_changes": False, "already_signed_off": False, "real_clients": "unknown"}
    write([{"heading": h, "answers": ans, "claims": [true_claim]} for h in T.HEADINGS])
    good, msg, res = T.check_verdicts("rubric")
    check("rubric mode: the HARNESS computes the verdicts", good and set(res["computed"].values()) == {"MATTERS"})
finally:
    if saved is None:
        rep.unlink(missing_ok=True)
    else:
        rep.write_text(saved, encoding="utf-8")

# scope
check("only review/verdicts.json is writable", T.execute({"tool": "write_file", "args": {"path": "src/schemas.ts", "content": "x"}}).startswith("REFUSED"))
check("the evidence is not writable", T.execute({"tool": "write_file", "args": {"path": "triage/evidence.txt", "content": "x"}}).startswith("REFUSED"))

print(f"\n{ok}/{n} checks passed -- no model, no API call.")
sys.exit(0 if ok == n else 1)
