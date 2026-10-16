# ai-triage-consistency: I asked my AI the same question 15 times

Companion repo to a [DevOps Autopilot](https://www.youtube.com/@DevOpsAutopilot) episode.

Two episodes in a row, the AI's review of an upgrade had a problem that wasn't in the code: an
invented database column (ep24), and runs that disagreed with each other on the same evidence (ep25).
So this episode measures it. The input is **frozen**: the 7 groups of zod 3 vs zod 4 differences from
ep25's fuzzer, in [`triage/evidence.txt`](triage/evidence.txt). Every run judges exactly the same
evidence. 15 runs, 3 modes, 5 runs each. $0: a local model call (`claude -p`, its own tools off).

| mode | the agent writes | the harness |
|---|---|---|
| **free** | MATTERS or NOISE per group, and why | checks the file covers every group |
| **evidence** | ...and every factual claim with a **probe**: a snippet run against zod 3, the oracle and the merged build | **runs every probe itself** ([`probe/sandbox.js`](probe/sandbox.js): read-only, no `require`, 30 s) and refuses the file if any output lacks the claimed text |
| **rubric** | no verdict: answers to fixed questions (does a verdict change? looser or stricter? is a stored value different? already signed off? could a real client send it?) | runs the probes, then **computes the verdict** with [`policy()`](agent/triage.py) |

```bash
npm ci && npm run build
python agent/triage.py --mode free|evidence|rubric
python agent/test_triage.py                        # 18 checks, no model
python triage/compare.py "evidence" results/ev-1 results/ev-2 results/ev-3 results/ev-4 results/ev-5
python triage/false_claims.py
```

## Results ([`results/agreement.txt`](results/agreement.txt))

| group | free | evidence | rubric |
|---|---|---|---|
| config `hosts` newly ACCEPTED | MATTERS 5/5 | MATTERS 5/5 | MATTERS 5/5 |
| config `timeoutMs: Infinity` newly REJECTED | NOISE 4/5 | NOISE 5/5 | NOISE 4/5 |
| signup `ip` newly ACCEPTED | MATTERS 5/5 | MATTERS 5/5 | MATTERS 5/5 |
| signup `age` (unsafe integers) newly REJECTED | NOISE 5/5 | NOISE 5/5 | SIGNED OFF 5/5 |
| rejected by both, different fields (x2) | NOISE 5/5 | NOISE 5/5 | NOISE 5/5 |
| signup `website` stored trimmed | NOISE 5/5 | NOISE 5/5 | **MATTERS 5/5** |
| **unanimous** | **6 of 7** | **7 of 7** | **6 of 7** |

**Far more consistent than ep25 suggested.** With frozen evidence and a triage-only job, the free mode
agreed on 6 of 7 groups. But not with ep25: there, all three reports called the `Infinity` timeout
MATTERS. Here 13 of 15 runs called it NOISE. Same model, same facts, a different framing, the opposite
majority.

## Consistent isn't correct ([`results/false_claims.txt`](results/false_claims.txt))

The `Infinity` verdict hangs on one factual question: can a real config contain `Infinity`? Many runs
reasoned that it can't, because "JSON can't carry Infinity". It can:

```js
JSON.parse('{"timeoutMs": 1e999}').timeoutMs   // Infinity
```

Labelled by hand (a run counts when it uses the claim to conclude no real config or client can send it):

| mode | runs that used the false claim | runs that found the `1e999` route |
|---|---|---|
| free | 2 of 5 | 1 of 5 |
| evidence | **1 of 5** | **3 of 5** |
| rubric | 3 of 5 (in the unchecked reasoning behind *real_clients = no*) | 2 of 5 |

When every fact costs a probe, the agent goes and looks, and mostly finds the truth. Rubric mode
checked the factual answers but not the reasoning behind the judgement, and that's where the false
claim lived.

**And the one that got through.** Run `ev-3` made it a formal claim, with a probe, and the harness
**verified** it:

```text
claim : JSON cannot carry Infinity: JSON.stringify nulls an Infinity field, JSON.parse of a body
        with a bare Infinity throws SyntaxError, and Number('1e999') is Infinity.
output: stringify={"t":null} parse=SyntaxError numStr=Infinity          verified: true
```

Every fact in the probe is true. The conclusion isn't: it tested `Number('1e999')`, never
`JSON.parse('{"t":1e999}')`. A probe proves what it tests, not what you conclude.

## The policy moved the disagreement, it didn't remove it

In rubric mode the harness computes the verdict. For the trimmed `website`, all five runs gave the same
answers (no verdict change, stored value changes, real clients do send surrounding whitespace) and the
policy said MATTERS, 5 of 5. Free and evidence runs, judging for themselves, said NOISE, 10 of 10: "the
new value is the better one". The rubric didn't make the model agree with itself; it replaced the
model's judgement with mine, written in [`policy()`](agent/triage.py). That judgement is now a
reviewable function, not a mood.

## The rules

1. **Measure it.** Run the triage more than once. Where runs disagree is where a human must look.
2. **Consistent isn't correct.** The majority verdict on `Infinity` rested on a false fact.
3. **Make facts cost a probe.** The false claim dropped to 1 of 5 runs, and 3 of 5 found the truth.
4. **Review the probe, not the checkmark.** A verified claim proves what its probe tested.
5. **Put the policy in code.** Then the disagreement is about a function you can read.

---
🎬 Full walkthrough: **[DevOps Autopilot](https://www.youtube.com/@DevOpsAutopilot)**
