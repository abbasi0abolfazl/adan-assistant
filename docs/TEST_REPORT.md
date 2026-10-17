# Actual verification report

## Outcome

- Local automated suite: **134 passed, 0 failed**.
- Actual PDF corpus: **3 PDFs, 6 physical pages, 6 default chunks**.
- Actual SQLite reference totals: **100,000,000 IRR (January 2026)** and **125,000,000 IRR (February 2026)**.
- Actual Decimal results: **25.00% growth**, **6,250,000 IRR provisional reserve** at the fictional 5% policy rate.
- Unsafe/invalid SQL rejection: exercised against a real temporary SQLite database.
- PDF visual QA: all six rendered pages inspected; no clipping or overlap found.

## What was NOT run

- A live generation/embedding provider request: **not run; no API key available**.
- Live Persian or cross-language retrieval/answer quality: **not measured**.
- Docker image build, Compose startup or tests inside Docker: **not run; Docker executable unavailable**.
- Fresh network dependency installation: **not run; container DNS unavailable**.
- GitHub repository publication / evaluator access verification: **not performed**.

Do not interpret mock/provider-contract tests as model quality measurements. Do not
interpret Docker configuration files as proof of a successful container build. No
live-evaluation success report has been fabricated.

## Evidence files

`reports/unit-tests.txt` is the captured pytest output. `reports/junit.xml` is the
machine-readable test result. `reports/deterministic-checks.json` records actual PDF,
SQL and calculator checks using explicitly labelled reference inputs.
`examples/reference_outputs.json` records fixture-driven orchestration examples;
model outputs and retrieval rank in that file are not from a hosted model.

## Tested environment

Report time: 2026-10-16T11:43:03.204885+00:00

Python: 3.13.5

SQLite library: 3.46.1

Operating system: Linux (x86_64)

Key package versions: FastAPI 0.128.2; Pydantic 2.13.5;
NumPy 2.3.5; pypdf 5.9.0; HTTPX 0.28.1; pytest 9.0.2.

## Reproduction commands

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --junitxml=reports/junit.xml
python scripts/offline_checks.py
python scripts/generate_reference_outputs.py
```

Before official submission, follow the Docker and paid live evaluation commands in
README.md, manually review answer entailment and commit the genuine live report.
