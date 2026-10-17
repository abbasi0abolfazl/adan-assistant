# Engineering decisions and alternatives

The assignment explicitly prioritizes a small working prototype, AI behavior, answer
correctness, error handling, SQL safety and agent routing over framework count or a
production-scale platform. The following are design decisions, not extra requirements
attributed to the original brief. A fuller explanation in Persian is in `DECISIONS.fa.md`.

| Decision | Why selected here | Advantages | Costs / rejected alternatives |
|---|---|---|---|
| Fictional electronics retailer | One coherent domain exercises policies, sales and derived percentages | Realistic joins and document/SQL dependencies; no personal data | Synthetic diversity is limited; not evidence of real-business accuracy |
| Three English, text-based PDFs | Required PDF preprocessing without an OCR project | Inspectable text, reliable physical page citation, reproducible JSON sources | Does not test scanned PDFs or Persian PDF layout; Persian queries need live cross-language evaluation |
| Python + FastAPI + Pydantic | Typed API/contracts with a compact implementation | Input validation, OpenAPI and dependency injection for tests | Python-specific operational stack; PHP/Flask could also meet the brief |
| Modular monolith | Components are independent without network services | Short execution path, simple debugging and one container | No independent scaling or process-level tool isolation |
| Explicit bounded coordinator | Make routing and data dependencies observable | No unbounded agent loop; deterministic safety boundaries | New graph shapes require code changes; LangGraph would help larger durable workflows |
| Shared configurable hosted model | Avoid a local serving/GPU/download subsystem within the time limit | Same structured-output protocol across specialist components | Network, cost, provider access and data-disclosure dependency; a local model is a legitimate later alternative |
| Generation snapshot `gpt-5.4-mini-2026-03-17` | Available documented structured-output/function-call capabilities | Version selection is explicit; reasonable small-task candidate | No live task benchmark was run; model access/availability must be checked by the operator |
| `text-embedding-3-small` | Straightforward real embedding API | No local model runtime; cache avoids repeat indexing requests | API dependency and no immutable dated embedding snapshot; local multilingual E5 is an alternative |
| NumPy exact cosine search with NPZ persistence | There are only six chunks | Minimal dependency/operational burden; no approximate-neighbor tuning | Linear search and in-memory index; FAISS/Qdrant/pgvector become useful at larger scale or with ACL needs |
| Page-aware word windows | Preserve source-page attribution and bounded chunks | Easy audit, overlap support, no extra tokenizer download | Word count is not token count; context quality and OCR layout require a stronger splitter for larger corpora |
| Normalize Unicode and repeated page margins | Remove known retrieval noise without flattening meaningful facts | Preserves numbers and clauses; meaningful preprocessing | Generic margin heuristics can remove repeated content; tests and source review matter |
| Top-4 with initial score threshold 0.25 | Bound context size and discard plainly weak matches | Simple baseline and configurable behavior | Not calibrated, not a confidence probability; may cause false acceptance/rejection |
| LLM sufficiency + verified exact quotes | Similarity alone cannot establish answerability | Unknown IDs, invented quotes and unsupported numeric facts are rejected | Exact-quote validation is NOT full entailment verification; semantic hallucinations remain possible |
| SQLite with four related business tables | Satisfies joins/aggregation without a database server | Reproducible local seed and short Docker startup | No server roles/row-level tenancy; PostgreSQL is preferable for a larger multi-tenant system |
| Integer IRR and explicit metric rules | Avoid unit and line-discount ambiguity | Business calculations are reproducible and inspectable | SQLite AVG may return floating point; no implied tax/refunds/costs/calendar conversion |
| Engine compilation + authorizer | The engine validates the actual SQLite syntax and requested operations | Avoids brittle keyword checks; blocks writes/system access in the real engine | SQLite-specific policy; this implementation does not offer general cross-dialect AST analysis |
| Read-only connection + query_only + limits | The prompt is not a security boundary | Independent defenses against writes, unsafe functions and runaway queries | Not process isolation; a hostile host/database file is outside this demo's trust model |
| Parameter binding and one repair | Values are separated from generated SQL; fix syntax without loops | Safer value handling and controlled latency | SQL structure still needs authorization; one repair can fail and must remain an error |
| Real native calculator function call | Explicit task requirement and arithmetic determinism | Actual function_call/output protocol; result and operands are observable | Adds a model turn; basic arithmetic only |
| Evidence variables + Decimal AST evaluator | Prevent invented operands and arbitrary Python execution | Source-linked amounts, deterministic rounding, no eval/powers/calls | Does not prove the chosen formula is semantically correct; operators and magnitudes are deliberately limited |
| Per-request trace and sanitized logs | Make specialist/tool execution explainable | Debuggable step order without secret/plaintext logging | API responses still reveal sample SQL/data; production would need access controls and log policy |
| Test doubles separated from runtime | Verify code without pretending a model was called | Fast offline regression tests plus explicit paid live suite | Offline pass count is not LLM accuracy, retrieval recall or proof of Docker execution |
| Single non-root Docker container | Required packaging without adding services | Loopback binding, read-only root filesystem and isolated runtime volume | Docker was not executable in the authoring environment; image/dependency build must be verified |
| Exact package version closure | Reduce dependency drift | Locally tested versions are explicit | No wheel hashes; base image tag mutable by default; stronger reproducibility needs a resolved digest and hash lock |
| No frontend/auth/CI/GPU | They are explicitly not expected by the brief | Time spent on the actual acceptance criteria | Not an internet-facing production service |
| No automatic GitHub publication | Repository owner/visibility/access were not specified | Avoids unintended public release or account changes | An accessible GitHub link remains a required submission step |

## Important boundaries

Read-only SQL is not automatically correct SQL. Bound parameters do not make arbitrary SQL
structure safe. A matching quote is not automatically an entailed answer. A similarity
score is not automatically a confidence probability. A successful mock test is not a live
provider result. These distinctions are deliberately reflected in code, tests and reporting.

## Primary technical references

These references explain underlying APIs; the implementation's quality claims come from
its actual tests, not from vendor documentation.

- OpenAI Responses function calling: https://developers.openai.com/api/docs/guides/function-calling
- Structured outputs: https://developers.openai.com/api/docs/guides/structured-outputs
- Generation model: https://developers.openai.com/api/docs/models/gpt-5.4-mini
- Vector embeddings: https://developers.openai.com/api/docs/guides/embeddings
- FastAPI request validation: https://fastapi.tiangolo.com/tutorial/body/
- SQLite authorization: https://sqlite.org/c3ref/set_authorizer.html
- SQLite defense guidance: https://sqlite.org/security.html
- Python SQLite controls: https://docs.python.org/3.13/library/sqlite3.html
- Python Decimal arithmetic: https://docs.python.org/3.13/library/decimal.html
- Docker Compose environment configuration: https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/
