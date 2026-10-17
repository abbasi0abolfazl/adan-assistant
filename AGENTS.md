# Adan Assistant project memory

## Project purpose and architecture

- This is a Persian/English evidence assistant for a fictional electronics retailer.
- FastAPI entry point: `app/main.py`; primary endpoint: `POST /ask`.
- The coordinator in `app/coordinator.py` routes to document RAG, read-only SQLite, and/or a bounded Decimal calculator.
- PDF parsing/chunking lives in `app/documents.py`; vector retrieval and cache construction in `app/retrieval.py`.
- Specialists live in `app/agents/`. SQLite access is guarded in `app/tools/database.py`; arithmetic is restricted in `app/tools/calculator.py`.
- Runtime settings are read from `.env`. Never print, commit, copy into reports, or include values from `.env` in prompts or artifacts. `.env.example` must contain blank API key values.

## Data and ground-truth semantics

- Data is synthetic; money is integer IRR and database dates are Gregorian ISO dates.
- Revenue is `SUM(quantity * unit_price_irr - discount_irr)` for completed orders. `discount_irr` is the total line discount.
- There are no cost, profit, actual refund transaction, or inventory-balance data. Do not infer these metrics.
- Reference values: January 2026 revenue 100,000,000 IRR; February 2026 revenue 125,000,000 IRR; growth 25.00%; provisional reserve at 5% is 6,250,000 IRR; February Tehran revenue 65,000,000 IRR.
- Return policy page 1 explicitly says: “Customers may request a return within 7 calendar days after delivery.” Page 2 only says that the 7-day window does not shorten the warranty. Cite page 1 for the delivery time anchor.
- A live evaluation previously exposed a Persian retrieval failure that cited the warranty sentence for a delivery-window claim. The document prompt and agent validation were tightened; the deployed API should return insufficient evidence if the retrieved/cited text does not support the complete claim. Re-test before changing these safeguards.

## How to verify

- Offline suite: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q` and `python scripts/offline_checks.py`.
- Live API evaluation is billable: `python scripts/evaluate_live.py --live --base-url http://192.168.1.60:8501 --output reports/live-evaluation-agy.json`.
- `examples/cases.json` contains 10 live cases across PDF retrieval, SQL, calculations, hybrid answers, insufficient evidence, destructive request rejection, and Persian retrieval.
- Review source filenames, pages, and exact quotes manually. Passing the script's structural checks does not prove semantic entailment; inspect every response for answer-to-quote support.
- Do not run live cases without the user's explicit request in the current task. Do not deploy or modify the remote service unless requested.

## Change discipline

- Preserve SQL read-only authorization, request bounds, citation verification, evidence-bound calculations, and provenance validation.
- Add or update focused tests for behavior changes. Do not loosen evidence checks to make a live case pass.
- Keep generated live reports under `reports/`; never include credentials or provider secrets.
