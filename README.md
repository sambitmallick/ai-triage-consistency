# ai-triage-consistency

Companion repo to a [DevOps Autopilot](https://www.youtube.com/@DevOpsAutopilot) episode (work in progress).

The triage agent reads the 7 frozen difference groups in `triage/evidence.txt` and writes `review/verdicts.json`.

```bash
npm ci && npm run build
python agent/triage.py --mode free|evidence|rubric
python agent/test_triage.py
```
