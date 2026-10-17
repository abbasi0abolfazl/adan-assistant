# Adan - Nava Evidence Assistant

A small, explainable implementation of the supplied recruitment assignment: PDF RAG,
LLM-generated read-only SQL, two independent specialist components, a bounded
coordinator, a real calculator function call, a FastAPI endpoint, and Docker packaging.

**Domain:** a fictional electronics retailer. **Money:** IRR. **Dates:** Gregorian.
The sample policies and all customers/orders are synthetic. They are not real company data.

## Verification status - read this first

**134 local automated tests passed.** Real PDF extraction, preprocessing, SQLite execution,
SQL attack rejection and Decimal arithmetic were executed. HTTP provider contracts and
orchestration were tested with explicit test doubles. See `reports/unit-tests.txt`,
`reports/junit.xml`, `reports/deterministic-checks.json`, and `docs/TEST_REPORT.md`.

**Live provider generation/embeddings and Docker build/run were not executed in the authoring
environment:** no API key or Docker executable was available, and container network DNS
was unavailable. This is not a claim of live answer accuracy or a successfully built image.
The application has **no fake runtime mode**: a real API key is required for real operation.

A GitHub repository has **not** been published automatically. The assignment only accepts
an accessible GitHub repository link; publish this folder and grant the evaluation team
access after completing the live checks below. A ZIP is a transfer artifact, not the final
submission method specified by the assignment.

## Quick start with Docker

Prerequisites: Docker with Compose v2, outbound access to the package registry and a
supported model endpoint, and an API key with access to the configured models.

```bash
cp .env.example .env
# Choose PROVIDER=openai or PROVIDER=gemini and set its key in .env.
# Never commit the populated file. Do not paste keys into chat or source files.
docker compose up --build -d
docker compose logs -f api
```

The first startup creates the sample SQLite database and calls the selected provider's
real embeddings endpoint to build a six-chunk semantic index. Later startups reuse the
cache when its PDF/content/configuration fingerprint matches. Source PDFs are already committed;
ReportLab is only needed to regenerate them.

```bash
curl http://127.0.0.1:8000/health/ready
curl -X POST http://127.0.0.1:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"What was total completed-order revenue for Gregorian February 2026 in IRR?","language":"en"}'
```

The API documentation is served at `http://127.0.0.1:8000/docs`. English and Persian
question text are accepted; set `language` to `en` or `fa` (default). The PDFs are English.
Cross-language answer quality must be checked with the included Persian live case; it
has not been measured in this delivery environment.

### Run offline tests, then capture actual live outputs

```bash
# No provider credentials or network access are used by the TEST PROCESS.
# Building the test image still requires image/package downloads.
docker compose --profile test run --build --rm tests

# This command intentionally makes billable real model requests (10 scenarios).
docker compose exec api python scripts/evaluate_live.py \
  --live --output /app/runtime/live-evaluation-openai.json
mkdir -p reports
docker compose cp api:/app/runtime/live-evaluation-openai.json reports/live-evaluation-openai.json
```

To run the same live cases against Gemini, set `PROVIDER=gemini` in `.env`, set
`GEMINI_API_KEY`, then recreate the API container and use a separate output file:

```bash
docker compose up --build -d --force-recreate api
docker compose exec api python scripts/evaluate_live.py \
  --live --output /app/runtime/live-evaluation-gemini.json
docker compose cp api:/app/runtime/live-evaluation-gemini.json reports/live-evaluation-gemini.json
```

Run once for each provider and compare the two JSON reports. The Gemini adapter uses
Google's OpenAI-compatible Chat Completions endpoint for generation and native Gemini
embeddings. Its structured output and tool behavior still require a live compatibility
check on the selected model.

Review every failure and inspect answer text/quotes manually before submitting. The
live script checks routes/status, expected documents/pages, SQL values and calculator
results; it is not a semantic truth oracle. It exits nonzero when a case fails.

`examples/reference_outputs.json` contains **fixture-driven contract examples**, clearly
labelled as such. Its SQL execution and calculator results are real, but its model replies
and retrieval rank are test fixtures. Never represent that file as a live provider run.

## Local development

Python 3.13 is the tested interpreter series. The exact local package versions and their
active dependency closure are recorded in the lock files.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.lock
cp .env.example .env
# Set API key in .env before starting the real service.
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Offline checks do not need a populated `.env`:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q
python scripts/offline_checks.py
python scripts/generate_pdfs.py
```

On PowerShell, activate `.venv\Scripts\Activate.ps1` and use
`$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"` before `python -m pytest -q`.

## Architecture

```text
POST /ask -> input validation + request budget
          -> LLM Coordinator (typed Plan; no keyword routing)
             |-- DocumentAgent
             |    PDF preprocessing -> cached real embeddings -> cosine top-k
             |    -> LLM answerability/answer -> exact-quote + source validation
             |-- DatabaseAgent
             |    schema + metric rules -> LLM-generated SQL + bound parameters
             |    -> SQLite compilation/authorizer -> bounded read-only execution
             |-- Calculator (when the plan requests it)
             |    native function_call -> evidence-bound Decimal arithmetic
             |    -> function_call_output returned to the LLM
             `-- final answer + sources + SQL/results + calculation + audit trace
```

The two specialists are independent classes with different responsibilities and contracts,
not aliases for one prompt. They share a provider adapter, not state. The coordinator is
an explicit finite flow: at most one document pass, one SQL attempt plus one syntax repair,
one calculator call and one final synthesis. It never grants broader privileges on retry.

The application is a modular monolith rather than a distributed multi-agent product.
See `docs/DECISIONS.md` and `docs/DECISIONS.fa.md` for alternatives and tradeoffs,
`docs/SECURITY.md` for the trust boundary, and `docs/INTERVIEW_GUIDE.md` for defense questions.

## Repository map

| Path | Responsibility |
|---|---|
| `app/main.py`, `contracts.py`, `config.py` | API, typed inputs/outputs, settings, bounded concurrency |
| `app/coordinator.py`, `prompts.py` | LLM routing, typed flow, evidence binding, final provenance |
| `app/agents/document_agent.py` | Document answerability, exact citations, sourced numeric facts |
| `app/agents/database_agent.py` | Real NL2SQL generation and at most one constrained repair |
| `app/documents.py`, `retrieval.py` | PDF normalization, page-aware chunks, real vector search/cache |
| `app/tools/database.py`, `calculator.py` | Read-only engine controls and bounded decimal arithmetic |
| `app/llm.py` | Responses, Embeddings and native function-calling HTTP contracts |
| `data/pdfs`, `data/source`, `data/db` | Three PDFs, reproducible source JSON, schema and seed scripts |
| `tests`, `examples`, `reports`, `docs` | Automated checks, live cases, actual test evidence, documentation |

## Data model and metric semantics

```text
customers 1 ---- N orders 1 ---- N order_items N ---- 1 products
```

There are 3 customers, 3 products, 10 orders and 12 order lines. One order is cancelled.
A discounted January line deliberately exercises the distinction between a total line
discount and a per-unit discount. A March order exercises half-open monthly filters.

`revenue_irr = SUM(quantity * unit_price_irr - discount_irr)` for completed orders.
The historical selling price is stored on the order line. All money is integer IRR.
`discount_irr` is the entire line discount. There are no tax, shipping-cost, cost-of-goods,
refund-transaction or inventory-balance tables. Profit and actual refunds are unavailable.

Expected deterministic reference values (confirmed by actual SQL and calculator execution):

| Reference metric | Expected value |
|---|---:|
| January 2026 completed-order revenue | 100,000,000 IRR |
| February 2026 completed-order revenue | 125,000,000 IRR |
| February versus January growth | 25.00% |
| Provisional reserve at the documented 5% rate | 6,250,000 IRR |
| February revenue for Tehran customers | 65,000,000 IRR |

The reserve is a fictional planning rule, **not an actual refund total**. The API must not
silently convert rials to toman or Gregorian periods to the Solar Hijri calendar.

## API response contract

`POST /ask` takes `question` (3-2000 nonblank characters) and `language` (`fa`/`en`).
A 16 KiB request-body cap also applies. Successful HTTP responses contain:

```json
{
  "request_id": "unique-per-request",
  "status": "answered | insufficient_evidence | clarification_required",
  "answer": "grounded answer in the requested language",
  "route": "documents | database | hybrid | calculator | clarify",
  "sources": [{"source_id": "...", "filename": "...pdf", "page": 2, "quote": "..."}],
  "sql": [{"generated_sql": "...", "executed_sql": "...", "parameters": [], "rows": []}],
  "calculations": [{"expression": "...", "variables": {}, "rounded_result": "..."}],
  "trace": [{"step": 1, "component": "coordinator", "action": "planning"}],
  "warnings": []
}
```

This block is a schema illustration, not a live response. The actual full schema is in
OpenAPI and `app/contracts.py`. Exact executed SQL includes a defensive outer limit;
the unmodified model-generated SQL and its parameters are exposed separately.

Common errors: 422 for bad input/SQL/calculation or model refusal, 413 for an oversized
body, 502 for invalid/unavailable provider responses, 503 for missing configuration or
saturated concurrency, and 504 for timeouts. Public errors omit provider response bodies,
secret values, internal stack traces and filesystem paths.

## Model and retrieval configuration

Default generation snapshot: `gpt-5.4-mini-2026-03-17`. Default embedding model:
`text-embedding-3-small`, 1536 dimensions. These are configurable, not a claim that this
pair is globally optimal or benchmarked on the assignment. The adapter requires the
OpenAI Responses/Embeddings contracts, structured output and native function calling;
an arbitrary server advertising only Chat Completions compatibility is not sufficient.

Chunks use 180 words, 30-word overlap and do not cross PDF pages. The six small source
pages each currently fit in one chunk. Top-k is 4. The 0.25 similarity threshold is an
initial heuristic, not calibrated confidence. A second LLM sufficiency decision plus
verified quotes is required. A quote existing in a document does not prove every answer
claim is entailed; manual/live evaluation remains necessary.

## Scope, limits and safe operations

No authentication, frontend, CI/CD, GPU service, OCR, document upload API, production
monitoring, live carrier integration or distributed state is included. These are not
required by the supplied brief. The Compose port is bound to loopback intentionally.
Do not expose this sample service to the internet or connect private business data
without authorization, authentication and a reviewed data-disclosure policy.

All retrieved text, schema/context sent to the generator, SQL result rows and user questions
may be transmitted to the configured model provider. `store=false` is used, but is not a
claim that every provider-side retention mechanism is disabled. Only synthetic data is
included here. `.env` is a demo convenience, not a production secret-manager replacement.

The cache is rebuilt on PDF/model/dimension/preprocessing changes. The database is seeded
once and is not silently overwritten. To regenerate it, **back up the runtime volume first**;
do not run destructive volume removal commands as a routine restart procedure.

Package versions are pinned, but package artifact hashes and the default Python base-image
digest are not locked. A `PYTHON_IMAGE` build argument accepts a reviewed immutable image
digest for stricter reproducibility. Docker build/run still needs to be verified on the target.

## Publish for the evaluation team

After the live suite passes and its text answers are reviewed:

```bash
git init
git add .
git status --short
# Confirm .env and runtime data are NOT staged; inspect live reports for secrets.
git commit -m "Implement evidence-grounded RAG, NL2SQL and calculator assistant"
```

Create a repository in the intended GitHub account, add that repository as `origin`, and
push the branch. Public visibility is not assumed. For a private repository, invite the
evaluation team and verify their access. Submit its actual GitHub URL. Do not claim a URL
exists until the repository has actually been created and pushed.
