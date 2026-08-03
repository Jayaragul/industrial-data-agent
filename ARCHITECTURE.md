# Industrial Data Agent architecture

The supported product is a CLI for read-only factory data analysis.

```text
User question
     |
     v
Question understanding (Gemini, or explicit offline fallback)
     |
     v
Catalog + plan validation
     |
     +--> deterministic query / operation executor
     |
     +--> generated analysis code -> AST validator -> Docker sandbox
     |
     v
Result and generated-file validation
     |
     v
Evidence-backed CLI response + audit record
```

The three approved source datasets are orders, machines, and inventory. Uploaded files are schema-checked, normalized, and copied into `runtime/ingested`; the source files under `data/input` are never modified.

Gemini can propose an analysis plan and analysis code, but it cannot execute host functions directly. Plans, operations, generated code, sandbox results, and generated files are validated before the final answer is returned.

For a live deployment, configure Gemini and use the Docker sandbox. For a reproducible presentation, set `INDUSTRIAL_AGENT_OFFLINE_MODE=true`; this uses the built-in deterministic fallback and does not require network access.

