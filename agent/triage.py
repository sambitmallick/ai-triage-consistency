#!/usr/bin/env python3
"""
triage.py -- ep26: ask the agent the same question, again and again. Do the verdicts hold?

Input : the 7 difference groups from ep25's fuzzer, FROZEN (triage/evidence.txt). Every run
        judges exactly the same evidence.
Output: review/verdicts.json. The only file it may write.

Three modes, one paragraph of goal apart:
  free      MATTERS or NOISE per group, and why.                                  (ep25's question)
  evidence  ...and every factual claim carries a probe: a snippet the HARNESS runs against zod 3,
            the oracle and the merged build, comparing the output with what the agent said.
  rubric    the agent only answers fixed questions (each factual answer backed by verified probes).
            The HARNESS computes the verdict from the answers: policy() below. The model supplies
            facts; code applies the policy.

Reuses ep22-25's harness (agent.py): the model call + retry, the loop, budget, stuck detection, the log.
Exit 4 = handed back for a human. Always.

Usage:  python agent/triage.py --mode free|evidence|rubric [--max-steps N]
"""
import json, re, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent as A  # noqa: E402  the ep22-25 harness, reused

PROJECT = A.PROJECT
EVIDENCE = (PROJECT / "triage" / "evidence.txt").read_text(encoding="utf-8")
HEADINGS = re.findall(r"^\[\d+\] (.+)$", EVIDENCE, flags=re.M)
REPORT = "review/verdicts.json"
WRITABLE = (REPORT,)
MAX_STEPS = 20

# ─────────────────────────────── the probe tool ───────────────────────────────
def run_probe(code: str) -> str:
    """Run an agent-written snippet in its own sandboxed process (read-only, no spawn). Returns its print() output."""
    try:
        r = subprocess.run(["node", "--permission", f"--allow-fs-read={PROJECT}", str(PROJECT / "probe" / "sandbox.js")],
                           input=code, cwd=PROJECT, capture_output=True, text=True, encoding="utf-8", timeout=30)
        return (r.stdout or r.stderr or "(no output)").strip()
    except subprocess.TimeoutExpired:
        return "PROBE ERROR: timed out after 30s"


TOOLS = {"list_files": A.list_files, "read_file": A.read_file, "write_file": A.write_file_scoped, "run_probe": run_probe}

A.ACTION_SCHEMA = {
    "type": "object",
    "properties": {"thought": {"type": "string"},
                   "tool": {"type": "string", "enum": ["list_files", "read_file", "write_file", "run_probe", "done"]},
                   "args": {"type": "object"}},
    "required": ["thought", "tool", "args"], "additionalProperties": False,
}

SYSTEM = """You are the decision-maker inside a small agent. You have no tools of your own.
Each turn you choose ONE action; the harness executes it and shows you the result.

Tools:
  list_files()               -> the files in the project
  read_file(path, offset=0)  -> a file's contents (long files come in parts; the result says so)
  run_probe(code)            -> runs a JavaScript snippet in a sandbox and returns what it printed. Available
                                names: zod3, zod (the libraries), oracle.parseSignup / oracle.parseConfig (the
                                code BEFORE the upgrade, zod 3), main.parseSignup / main.parseConfig (the merged
                                build, zod 4), print(...). Each parse returns {ok, value} or {ok:false, problems}.
                                No require, no files, no network.
  write_file(path, content)  -> replace a file. Only review/verdicts.json is writable.
  done(summary)              -> finish. The harness checks the verdicts file before it accepts.

Rules: base every factual claim on evidence you got from a tool, and say when something is a judgement.
Reply with JSON only: {"thought": "...", "tool": "...", "args": {...}}"""

INTRO = ("signupkit was upgraded from zod 3.25 to zod 4.6 and merged. A differential fuzzer compared the code "
         "before the upgrade (zod 3) with the merged build on 10,000 generated inputs. Below are ALL the groups of "
         "different answers it found, with examples. For EACH group decide whether it MATTERS (a human must act "
         "before this ships) or is NOISE (no action needed). review/corpus-diffs.md is an earlier review a human "
         "already signed off; src/schemas.ts is the merged code.\n\nEVIDENCE:\n" + EVIDENCE + "\n")

SCHEMAS = {
    "free": ('Write review/verdicts.json: {"groups": [{"heading": "<the group heading, copied exactly>", '
             '"verdict": "MATTERS" | "NOISE", "why": "<your reasoning>"}, ...]} with one entry per group.'),
    "evidence": ('Write review/verdicts.json: {"groups": [{"heading": "<copied exactly>", "verdict": "MATTERS" | "NOISE", '
                 '"why": "<reasoning>", "claims": [{"claim": "<one factual statement>", "probe": "<JavaScript for '
                 'run_probe that prints evidence>", "expect": "<text the probe output must contain>"}, ...]}, ...]}. '
                 'Every group needs at least one claim, and every factual statement in "why" must be one of its claims. '
                 'The harness runs every probe itself and refuses the file if any probe output does not contain its '
                 '"expect" text. Judgements (who sends what, what is risky) are not claims: label them as judgement in "why".'),
    "rubric": ('Do NOT give verdicts. For each group, answer these questions, and the harness computes the verdict:\n'
               '  verdict_changes      true/false: does some input get accepted by one version and rejected by the other?\n'
               '  direction            "looser" (now accepts what zod 3 rejected) | "stricter" | "none"\n'
               '  stored_value_changes true/false: is some input accepted by both but stored differently?\n'
               '  already_signed_off   true/false: did a human already sign off this exact change in review/corpus-diffs.md?\n'
               '  real_clients         "yes" | "no" | "unknown": could a real, well-behaved client plausibly send such input? (judgement)\n'
               '  why                  your reasoning, judgement labelled as judgement\n'
               '  claims               [{"claim", "probe", "expect"}] backing the factual answers (at least one per group)\n'
               'Write review/verdicts.json: {"groups": [{"heading": "<copied exactly>", "answers": {...the six fields above...}, '
               '"claims": [...]}, ...]}. The harness runs every probe and refuses the file if any output lacks its "expect" text.'),
}
GOALS = {m: INTRO + SCHEMAS[m] for m in SCHEMAS}


# ──────────────────────────── the policy (rubric mode) ────────────────────────
def policy(a: dict) -> str:
    """The decision lives in code, not in the model. Reviewable, testable, the same every run."""
    if a.get("already_signed_off") is True:
        return "SIGNED OFF"
    if a.get("verdict_changes") is not True and a.get("stored_value_changes") is not True:
        return "NOISE"                      # nobody is accepted, rejected or stored differently
    if a.get("direction") == "looser":
        return "MATTERS"                    # accepts what the old code refused: a decision nobody made
    if a.get("real_clients") == "no":
        return "NOISE"                      # stricter / re-stored, but only for input no real client sends
    return "MATTERS"                        # stricter or re-stored, and real clients may send it (or nobody knows)


# ──────────────────────────────── the done-gate ───────────────────────────────
def check_verdicts(mode: str) -> tuple:
    """(ok, message, results). The harness validates the file and RUNS every claimed probe itself."""
    p = PROJECT / REPORT
    if not p.exists():
        return False, f"NOT DONE -- {REPORT} doesn't exist.", None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        groups = {g["heading"]: g for g in data["groups"]}
    except Exception as e:
        return False, f"NOT DONE -- {REPORT} is not valid: {type(e).__name__}: {e}", None
    missing = [h for h in HEADINGS if h not in groups]
    if missing:
        return False, "NOT DONE -- no entry for these groups (copy each heading exactly): " + "; ".join(missing), None
    problems, results = [], {}
    for h in HEADINGS:
        g = groups[h]
        if mode in ("free", "evidence") and g.get("verdict") not in ("MATTERS", "NOISE"):
            problems.append(f"{h}: verdict must be MATTERS or NOISE")
        if mode == "rubric":
            a = g.get("answers") or {}
            bad = [k for k, ok in (("verdict_changes", isinstance(a.get("verdict_changes"), bool)),
                                   ("direction", a.get("direction") in ("looser", "stricter", "none")),
                                   ("stored_value_changes", isinstance(a.get("stored_value_changes"), bool)),
                                   ("already_signed_off", isinstance(a.get("already_signed_off"), bool)),
                                   ("real_clients", a.get("real_clients") in ("yes", "no", "unknown"))) if not ok]
            if bad:
                problems.append(f"{h}: invalid answers: {', '.join(bad)}")
        claims = g.get("claims") or []
        if mode != "free":
            if not claims:
                problems.append(f"{h}: needs at least one claim with a probe")
            for i, c in enumerate(claims):
                out = run_probe(str(c.get("probe", "")))
                expect = str(c.get("expect", ""))
                verified = bool(expect) and expect in out and "PROBE ERROR" not in out
                results.setdefault(h, []).append({"claim": c.get("claim"), "verified": verified, "output": out[:300]})
                if not verified:
                    problems.append(f'{h}: claim {i + 1} NOT VERIFIED: "{str(c.get("claim"))[:90]}" -- expected "{expect[:60]}", probe printed "{out[:120]}"')
    if problems:
        return False, "NOT DONE --\n" + "\n".join(problems[:20]), results
    computed = {h: (policy(groups[h]["answers"]) if mode == "rubric" else groups[h]["verdict"]) for h in HEADINGS}
    return True, "verdicts: " + "; ".join(f"{h.split(':')[0]}:{h.split(': ')[1][:18]}={v}" for h, v in computed.items()), {"computed": computed, "claims": results}


# ────────────────────────────────── the loop ──────────────────────────────────
def execute(action: dict) -> str:
    tool, args = action["tool"], dict(action.get("args") or {})
    if tool not in TOOLS:
        return f"ERROR: unknown tool '{tool}'"
    if tool == "write_file":
        path = str(args.get("path", "")).replace("\\", "/")
        if path not in WRITABLE:
            return f"REFUSED: only {REPORT} is writable."
    try:
        out = str(TOOLS[tool](**args))
        return out if tool == "read_file" or len(out) <= A.MAX_RESULT_CHARS + 300 else \
            out[:A.MAX_RESULT_CHARS] + f"\n[... output truncated: {len(out) - A.MAX_RESULT_CHARS} more chars not shown]"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


def run(mode: str, max_steps: int = MAX_STEPS) -> int:
    A.RUNS.mkdir(exist_ok=True)
    log_path = A.RUNS / time.strftime(f"triage-{mode}-%Y%m%d-%H%M%S.jsonl")
    goal, history, seen = GOALS[mode], [], {}
    print(f"agent: triage   mode = {mode}   budget = {max_steps} steps   log = {log_path.name}", flush=True)
    for step in range(1, max_steps + 1):
        try:
            action = A.ask_model(SYSTEM, A.render(goal, history, max_steps))
        except RuntimeError as e:
            A._log(log_path, step, {"tool": "(model)", "thought": "", "args": {}}, str(e))
            return A._finish(5, f"⛔ the model is unavailable ({e}). Handing back to a human.")
        argtxt = ", ".join(f"{k}={str(v)[:60]!r}" for k, v in (action.get("args") or {}).items() if k != "content")
        print(f"── step {step} ── {action['tool']}({argtxt})", flush=True)
        print(f"   thought: {action['thought'][:160]}", flush=True)
        if action["tool"] == "done":
            ok, msg, res = check_verdicts(mode)
            if ok:
                A._log(log_path, step, action, "DONE · " + msg)
                (PROJECT / "review" / "verdicts.harness.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
                return A._finish(4, f"🟡 handing back to a human after {step} steps — {msg}")
            result = msg
        else:
            result = execute(action)
        A._log(log_path, step, action, result)
        preview = result if len(result) < 400 else result[:400] + " …"
        print("   result : " + preview.replace("\n", "\n            "), flush=True)
        history.append({"step": step, "action": action, "result": result})
        if A._repeating(seen, action, result):
            return A._finish(3, f"⛔ stuck: repeated {action['tool']} {A.MAX_REPEATS}× with the same arguments.")
    return A._finish(2, f"⛔ hit the {max_steps}-step budget without finishing. Handing back to a human.")


if __name__ == "__main__":
    argv = sys.argv[1:]
    mode = argv[argv.index("--mode") + 1] if "--mode" in argv else "free"
    steps = int(argv[argv.index("--max-steps") + 1]) if "--max-steps" in argv else MAX_STEPS
    sys.exit(run(mode, steps))
