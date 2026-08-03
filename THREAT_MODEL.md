# Threat model

## Trust boundaries

- User questions are untrusted input.
- Gemini output is untrusted model output.
- Uploaded CSV and Excel files are untrusted data.
- The host process, approved dataset roots, and generated-file validators are trusted application components.
- The sandbox is a restricted execution boundary, not a guarantee of complete security.

## Main attacker goals

- Read host secrets or files outside approved inputs.
- Execute network or shell commands through generated analysis code.
- Modify source datasets or application files.
- Cause misleading answers through malformed data or model output.
- Create oversized or unsafe generated files.

## Controls

- Schema validation and normalization during ingestion.
- Catalog-limited datasets and fields.
- Plan validation before execution.
- AST checks for imports, calls, paths, environment access, and shell behavior.
- Docker sandbox with no network, resource limits, read-only inputs, and restricted output roots.
- Result and generated-file validation before display.
- Evidence-backed final response contract and audit logs.

## Non-goals

- This project is not an ERP, real-time machine-control system, or safety-certified production isolation environment.
- The sample data is synthetic demonstration data, not live factory telemetry.

