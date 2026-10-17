# Requirement-to-code traceability

Basis: supplied `adan-task.docx`, pages 2-5. The application domain, data, models and
implementation details below are chosen for the solution; the source brief leaves them open.

| Source requirement | Implementation | Evidence / remaining verification |
|---|---|---|
| Small real-world-like assistant, not production (p2) | Fictional store, modular monolith | Source, schema and sample PDFs |
| Several small realistic PDFs (p2) | 3 text-based PDFs, 2 pages each | Committed PDFs; generator and source JSON |
| Meaningful preprocessing (p2) | Unicode normalization, dehyphenation, repeated margin removal | PDF/normalization/overlap tests |
| Embeddings and semantic retrieval (p2) | Real embeddings API + normalized cosine search + persisted cache | Real adapter; algorithm/cache tests. Live embeddings NOT run here |
| LLM response with sources and honest insufficiency (p2) | DocumentAgent sufficiency and exact quote/source checks | Contract tests; live semantic behavior remains to verify |
| At least two related tables (p3) | customers, orders, order_items, products | Real database seed and FK checks |
| Genuine LLM-generated SQL, no question lookup (p3) | Typed SQLDraft from schema+question through Responses API | No runtime canned query table; mocked HTTP contract tested; live NL2SQL remains to verify |
| Filtering, aggregation, JOIN (p3) | Supported read-only SQLite queries | Actual seeded-database tests and deterministic reports |
| Inspect SQL and result (p3) | generated_sql, executed_sql, parameters, rows | API contract and fixture-driven examples |
| Read-only and safe invalid SQL handling (p3) | Compiler authorizer, mode=ro, query_only, engine/resource controls | Actual attack and error tests |
| At least two specialists and coordinator (p3) | Independent DocumentAgent/DatabaseAgent + typed Coordinator | Real orchestration tests with model doubles |
| Actual calculator and multi-step tool calling (p3) | Native function_call/output + restricted Decimal evaluator | HTTP protocol tests and actual SQL-to-calculator arithmetic |
| Observable agent/tool execution (p3) | Request trace and sanitized structured audit logs | Coordinator/API tests and example traces |
| Lightweight API and error handling (p3) | FastAPI /ask and health endpoints | TestClient validation/error/concurrency tests |
| Reproducible Docker setup (p4) | Dockerfile, Compose, exact package version closure, deterministic sample sources | Docker files prepared; Docker build/run NOT performed here; base digest not locked |
| >=2 RAG, >=2 SQL, 1 mixed case, negative cases (p4) | 10 live scenarios plus parametrized security tests | examples/cases.json; live run still required |
| README/env/examples/test instructions (p4) | README, env example, docs, fixtures and real deterministic reports | Included |
| Accessible GitHub URL is the only accepted delivery (p4) | Git-ready folder and publish instructions | NOT published; intended account/visibility/evaluator access must be set |
| Explain decisions and modify code at interview (p4) | Decisions, security notes, interview exercises | Included in English and Persian |
