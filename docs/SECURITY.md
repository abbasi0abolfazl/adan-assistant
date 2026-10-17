# Trust boundary and security review

## Assumptions

The source PDFs, application code, schema and seed scripts are operator-controlled demo
assets. User questions, retrieved content and generated model outputs are untrusted.
The host, SQLite library, dependency supply chain and model endpoint are not adversarial
in this prototype. No authenticated tenant boundary is claimed. Only synthetic data is used.

## SQL execution boundary

`ReadOnlySQL` opens a new `mode=ro` connection per tool call. It sets `query_only`, disables
trusted schema and extension loading, and enables SQLite defensive mode where supported.
The connection authorizer defaults to DENY. Only SELECT, reads of four named business
tables, and a small set of read functions are permitted. ATTACH, PRAGMA, DDL, DML,
recursive CTE actions, extension functions and internal/schema table reads are denied.

Both the original query and the capped result query are compiled by SQLite under the
same authorizer. Compilation of the original uses EXPLAIN; the model query itself is not
executed until authorization succeeds. An approved data-table read is required, so a
constant-only manufactured answer cannot masquerade as a database lookup.

SQLite sometimes supplies a NULL database name and an empty column for `COUNT(*)`.
The callback permits that specific case only for the named table allowlist; ordinary
column reads with no database name remain denied. A regression test covers this behavior.

An outer LIMIT fetches at most 101 rows for the default 100-row response cap and reports
truncation. This limit does not bound aggregation or join work. Independent wall-clock,
virtual-machine-step, SQL-length, expression-depth, column, variable, and compound-query
limits address resource use. Unsupported binary, non-finite and oversized result payloads
are rejected before response synthesis. NULL is not silently converted to zero.

Bound positional parameters are used for user filter values. The agent may repair one
invalid SQL query; authorization failures are not retried with looser settings.

## Calculator boundary

The LLM emits an actual native function call. The application validates its arguments,
parses the expression with Python AST and recursively interprets a restricted grammar.
There is no `eval`, `exec`, shell, attribute access, indexing, function call, exponentiation,
comprehension or arbitrary module import in the calculator. Only +, -, *, / and unary
signs are accepted. Expression size, AST node count and numeric magnitude are bounded.

Numbers other than 0, 1 and 100 must be supplied as named evidence variables. SQL values
come directly from result cells; document values must be present in a verified quote;
user numbers are extracted from the question. The answer records those origins.
Zero division fails explicitly. Decimal precision is 40; display rounding uses ROUND_HALF_UP.
This validates arithmetic and operand provenance, not the user's intended mathematical model.

## Documents and model output

RAG contexts are marked as untrusted data in prompts. Answers require valid source IDs
and exact quotes from retrieved chunks. Extracted numeric facts must match numbers
actually present in their quotes without silent percentage/unit conversion. The final
response also validates claimed document, SQL and calculator provenance.

These controls reduce hallucination/injection risk; they do not guarantee entailment or
perfect resistance to semantic prompt injection. An answer can cite a real but insufficient
quote. The live scenarios and human review remain necessary. No tool has write privileges
regardless of what a document or model says.

## API and operations

Request-body and question-length limits, typed contracts, bounded concurrent requests,
provider timeouts, a global request budget and bounded retries are implemented. Public
errors omit provider bodies, secrets and stacks. Logs contain request IDs and step names,
not document bodies, SQL values or questions. Response traces expose synthetic business
data for evaluator inspection and therefore are not suitable for public multi-tenant use.

Compose uses a non-root user, dropped capabilities, a read-only root filesystem, loopback
host binding and a dedicated writable runtime volume. These are configured controls,
not a claim that a Docker run was performed in the authoring environment.

`.env` is ignored by Git and Docker; it must never be committed. Operator-configured model
endpoints are trusted destinations for credentials. Do not send private source documents
or customer records without authorization. `store=false` is not a complete privacy policy.

## Deliberately not claimed

No production authentication, tenant isolation, external secrets manager, process-level SQL
sandbox, secure handling of malicious host files, exhaustive fuzzing, supply-chain audit,
perfect hallucination prevention, guaranteed semantic SQL accuracy or guaranteed provider
availability is claimed. Those would require a separate production threat model and tests.
