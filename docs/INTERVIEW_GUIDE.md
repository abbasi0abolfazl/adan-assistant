# Interview defense and small-change exercises

## Explain the design in 90 seconds

"I built a small evidence-grounded assistant for a fictional retailer. Documents carry
policies; four related SQLite tables carry transactional facts. A typed LLM coordinator
routes to separate document and database specialists. The document path performs real
embedding retrieval and requires verifiable quotes. The database path generates fresh SQL
from a schema and metric rules; the SQLite engine enforces read-only access. Calculations
use native function calling, a restricted Decimal evaluator and evidence-bound variables.
Every response exposes provenance, query results and tool steps. I deliberately avoided a
frontend, distributed agents and GPU infrastructure because the brief prioritizes core
behavior. Offline tests passed; live model/Docker checks must be verified separately."

## Questions worth preparing

**Why not just prompt the model to be read-only?**
A prompt governs desired behavior, not database capability. The database connection and
compiler authorizer independently deny changes even if the model generates a DELETE.

**Why no SQLGlot?**
The implementation targets one dialect. SQLite already parses the exact syntax and reports
authorization actions for the real query. The read-only URI, authorizer, resource limits and
result wrapper provide the enforcement boundary. A separate AST library could improve
cross-dialect analysis but is not itself a replacement for engine permissions.

**Why not LangChain/LangGraph?**
A bounded four-capability flow fits explicit classes and typed contracts. Frameworks become
more attractive for durable checkpoints, human approval, resumable runs and larger graphs.
The current design keeps the control flow directly visible during review.

**Is the calculator really a tool call?**
Yes. `choose_calculator()` sends a function schema to the Responses API, receives a
`function_call` with a `call_id`, executes the local tool, and returns a matching
`function_call_output` before final synthesis. Merely asking the LLM to print arithmetic
would not satisfy this requirement.

**Why calculate sums in SQL but growth with a calculator?**
Database aggregation extracts the correct facts close to the data. A later percentage is a
separate deterministic transformation and demonstrates the requested multi-step tool flow.
Moving every SUM to the calculator would needlessly transfer rows and risk truncation.

**What prevents the model inventing a reserve percentage?**
The rate is extracted as a numeric fact with an exact quote and source ID. It must occur in
that quote and is bound as a named calculator variable. The calculator cannot accept an
arbitrary literal 5, 7 or a fabricated revenue amount instead of that variable.
This still does not prove a retrieved policy is applicable to every question; evaluation matters.

**Why integer IRR?**
The dataset uses integer rials to avoid accidental float handling and rial/toman ambiguity.
Line discounts are subtracted once. Historical unit prices belong to order lines. Profit,
refund totals and tax cannot be inferred from absent tables.

**Why isn't a score above 0.25 proof of relevance?**
Cosine scores depend on the embedding model and corpus. The threshold is only an initial
filter. The specialist must also judge answerability and provide verifiable supporting quotes.
A held-out evaluation set is required before treating a threshold as calibrated.

**What does the 134-test count prove?**
Deterministic safety/business logic, preprocessing, API validation and provider protocol
handling were exercised. It does not prove hosted-model accuracy, multilingual retrieval
quality, end-to-end latency or successful Docker execution.

**Why are PDFs English when the user may ask in Persian?**
The brief does not restrict document language. English text PDFs keep the baseline focused
on RAG rather than Persian PDF layout/OCR. The API supports Persian text; a Persian live
case is included. Real cross-language quality has not been measured yet.

**Why not add a production login now?**
The brief explicitly does not require authentication. Loopback binding reduces accidental
exposure. Authentication would be essential before exposing private data or public access,
but adding it does not replace the core AI acceptance criteria.

**What if the policy or database schema changes?**
PDF/model/preprocessing changes invalidate the index fingerprint. Existing databases are
not silently overwritten; schema changes need an explicit migration. Update the schema
contract and metric tests together rather than only changing the prompt.

## Small changes to demonstrate live

1. Change the provisional reserve from 5% to 7% in `data/source/documents.json`, regenerate
   PDFs, restart and verify automatic cache invalidation. Expected February reserve becomes
   8,750,000 IRR. Update reference expectations; do not hard-code 7 in application logic.
2. Change `SQL_MAX_ROWS` to 2 and ask for all completed orders. Show `truncated=true`; a
   calculation over that partial listing should refuse instead of inventing a complete total.
3. Add a rejected-function test for `randomblob`. Explain why a SELECT can still be unsafe.
4. Ask for actual profit. Explain the absence of cost data rather than renaming revenue.
5. Ask for growth with a zero baseline and demonstrate the explicit zero-division error.
6. Add a new legitimate policy PDF and show filename/page references and a rebuilt index.

## Pre-submission gate

Run tests inside Docker, run `evaluate_live.py --live`, manually review both successful and
abstained answers, commit the genuine live report without secrets, publish to the intended
GitHub account, grant evaluator access, and verify the submitted link from an account that
has the same access as the evaluation team. Do not mislabel fixture traces as live evidence.
