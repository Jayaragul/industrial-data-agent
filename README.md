# Industrial Data Agent

`industrial-data-agent` is a CLI-first, Gemini-backed agent for asking questions about industrial orders, machines, and inventory. The supported hackathon product is the CLI; the older web files are not part of the supported demo.

Run it with:

```bash
python bot.py
```

For a reproducible demo that does not need an API key or network access:

```bash
python demo.py
```

The demo asks five representative questions and creates a CSV report. It uses the bundled demonstration datasets and explicit offline fallback.

## Two-minute judge demo

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python demo.py
```

During the presentation, explain the flow: a natural-language question becomes a validated plan; simple questions use deterministic operations; complex analysis is checked and run in a restricted sandbox; the response includes evidence and generated files.

Try these questions interactively with `python bot.py`:

- `How many high priority orders are there?`
- `What orders are delayed?`
- `Which machines are idle?`
- `What materials are below reorder level?`
- `Create a CSV report for high priority orders.`

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Set these values in `.env`:

```env
GEMINI_API_KEY=your_key
GEMINI_MODEL=your_configured_model
GEMINI_TEMPERATURE=0
INDUSTRIAL_AGENT_OFFLINE_MODE=false
```

The model name is never hardcoded. It must come from `GEMINI_MODEL`. For local presentations without Gemini, set `INDUSTRIAL_AGENT_OFFLINE_MODE=true` in `.env`; this is an intentional deterministic fallback, not a test-only setting.

If a live request returns `GEMINI_UNAVAILABLE`, inspect `runtime/logs/gemini.log`. Each line is a JSON diagnostic containing the timestamp, question, request ID, connection state, configuration flags, and provider error. API keys are never written to this log.

## Load Your Data

While the agent is running, load a CSV or Excel file with one of these commands:

```text
/ingest orders "C:\\path\\to\\orders.csv"
/ingest machines "C:\\path\\to\\machines.xlsx"
/ingest inventory "C:\\path\\to\\inventory.csv"
```

Each file is checked against the required columns before it is accepted. The agent stores a normalized copy under `runtime/ingested` and uses it for all later questions. Type `/data` to see which uploaded datasets are active.

## AI Harness And Factory Wiki

The agent uses a persistent knowledge harness inspired by Karpathy's LLM Wiki pattern:

- `runtime/factory_wiki/raw/` keeps immutable copies of uploaded source files.
- `runtime/factory_wiki/pages/` keeps maintained dataset pages.
- `runtime/factory_wiki/index.md` is searched as additional context for planning.
- `runtime/factory_wiki/log.md` records ingests and completed data queries.
- `runtime/factory_wiki/HARNESS.md` states the rules: the wiki provides context and provenance, while validated active CSV data remains the source of truth for quantities, dates, and counts.

Use `/wiki lint` in the running app to check for missing dataset pages or an empty activity log.

## Sandbox

Generated analysis code is validated with Python AST rules, then run through the sandbox runner. Docker is the production path and uses:

```bash
docker build -t industrial-data-agent-sandbox sandbox
```

The sandbox mounts request-specific folders:

- `runtime/sandbox_inputs/<request_id>` as `/sandbox/input`, read-only
- `runtime/sandbox_work/<request_id>` as `/sandbox/work`
- `runtime/outputs/<request_id>` as `/sandbox/output`

Docker runs without network access, without privileged mode, with CPU and memory limits, and without host secrets.

For local test environments without Docker, tests may set `INDUSTRIAL_AGENT_ALLOW_LOCAL_SANDBOX=true`. Do not use that mode for production analysis.

## File Generation

Files are generated only when requested or clearly required:

- CSV details
- JSON outputs
- PDF reports with ReportLab
- Matplotlib charts under `runtime/outputs/<request_id>/charts`

All generated files are validated before the agent shows their paths.

## Safety Restrictions

Generated code may only read `/sandbox/input`, write `/sandbox/output`, and use `/sandbox/work` for temporary files. It cannot import network, process, operating-system, dynamic-import, credential, or unsafe serialization modules. It cannot use `eval`, `exec`, `compile`, `__import__`, shell commands, environment variables, or unapproved paths.

Unsafe user requests such as reading secrets, importing `os`, running shell commands, or modifying source CSV files return `UNSUPPORTED_REQUEST`.

## Tests

```bash
python -m pytest -q
```

The sandbox smoke test requires either the built Docker image or the explicit local-test setting. If Docker is unavailable, run the non-sandbox checks with:

```bash
$env:INDUSTRIAL_AGENT_OFFLINE_MODE="true"
python -m pytest -q -k "not sandbox"
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the system diagram and security boundaries. Runtime request folders, ingested files, audit logs, and generated outputs are intentionally ignored by Git; only source data, code, and documentation belong in a clean submission.
