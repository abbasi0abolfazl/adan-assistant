---
name: test-live-api
description: Run and assess the Adan Assistant's 10 real API scenarios, including Persian and English PDF retrieval, read-only SQL, calculations, hybrid answers, insufficient evidence, and destructive-request rejection. Use when the user asks to test or validate the deployed API with Google Antigravity.
---

# Test the live Adan API

## Project memory

- Read the workspace `AGENTS.md` first. It is the persistent project memory and contains architecture, data semantics, reference values, prior retrieval issue, and safe verification commands.
- The deployed development API is `http://192.168.1.60:8501`; check `/health/ready` before sending test requests.
- The live case set is `examples/cases.json` and currently contains 10 scenarios.
- Live model calls can incur provider charges. The user must explicitly ask for a live run in the current task. This skill does not authorize changes or deployment.

## Procedure

1. Read `AGENTS.md`, `README.md`, `examples/cases.json`, and `scripts/evaluate_live.py`.
2. Check `http://192.168.1.60:8501/health/ready`. If it is unreachable or not ready, report that and stop; do not redeploy.
3. Run the full real HTTP suite:

   ```bash
   python scripts/evaluate_live.py --live --base-url http://192.168.1.60:8501 --output reports/live-evaluation-agy.json
   ```

   This sends real API requests. If `httpx` is missing, use the repository's documented development environment. Never read or print `.env`, and never substitute fixture/fake providers for this live run.

4. Inspect `reports/live-evaluation-agy.json`. Report the total and pass count, then summarize each failure with case ID and concrete evidence. Do not paste the entire report into chat.
5. Independently review answer grounding. Every claim must follow from a returned exact quote, including numeric values, units, dates, and time anchors. In the Persian return case, verify that the result either cites `returns_policy.pdf` page 1 with a quote containing both “7 calendar days” and “after delivery”, or returns `insufficient_evidence`. A page 2 warranty quote does not support the delivery anchor.
6. Compare SQL and calculations with workspace `AGENTS.md`: January revenue 100,000,000 IRR, February revenue 125,000,000 IRR, month-over-month growth 25.00%, provisional 5% reserve 6,250,000 IRR, and February Tehran revenue 65,000,000 IRR.
7. Confirm that the dangerous request is rejected without any `read_only_sql_executed` event.
8. Do not modify code, weaken evidence checks, or deploy as part of this test skill. Report concrete defects and wait for a separate fix request.
