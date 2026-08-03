# Repository Improvement Plan

## Recommended public identity

Repository name:

```text
industrial-data-agent
```

Repository description:

```text
Safety-first Gemini-powered CLI for evidence-backed analysis of industrial orders, machine utilization, and inventory, with an offline demo and sandboxed code execution.
```

Suggested topics:

```text
industrial-ai
manufacturing
manufacturing-analytics
gemini
ai-agent
data-agent
python
cli
sandbox
inventory-management
machine-utilization
llm
```

## Priority 0: clean the first impression

1. Rename `Industory-ai-harness` to `industrial-data-agent`.
2. Rename the default branch from `branch-2` to `main`.
3. Replace the initial commit message typo with a clean history if the repository has not been shared widely, or make the next commits professional and descriptive.
4. Replace the current README with the included README.
5. Add a repository description, topics, and a social preview image.
6. Add a license only after choosing the terms you want. MIT is simple and permissive; Apache-2.0 also includes an explicit patent grant.
7. Publish a `v0.1.0` release after CI is green.

## Priority 1: remove confusing and accidental files

1. Remove `marker.tmp`.
2. Remove `web/` and `web_app.py`, or move them to a clearly named `legacy/` branch. The supported product is described as CLI-only, so shipping unused web code weakens the message.
3. Remove FastAPI, Uvicorn, and `python-multipart` from `requirements.txt` if the web app is removed.
4. Make `pyproject.toml` the source of truth for dependencies and generate any requirements lock file from it.
5. Fix the sample inventory value `MAT-STEEL,njr`; replace `njr` with the intended material name.
6. State that the sample dataset is a fixed snapshot, or generate relative demo dates so the example does not become stale.

## Priority 2: make the project trustworthy

1. Add the included GitHub Actions workflow.
2. Add a CI badge only after the workflow passes.
3. Enable Dependabot alerts, security updates, secret scanning, push protection, and code scanning.
4. Add a license, `CONTRIBUTING.md`, `SECURITY.md`, issue templates, and a pull-request template.
5. Add test coverage reporting and a minimum coverage target.
6. Add a short threat-model document covering trust boundaries, attacker goals, sandbox assumptions, and non-goals.
7. Avoid describing the sandbox as fully secure or production-safe until it has been reviewed independently.

## Priority 3: improve installation and developer experience

1. Add a build backend to `pyproject.toml`.
2. Move package code under `src/industrial_data_agent/`.
3. Add a console entry point:

```toml
[project.scripts]
industrial-data-agent = "industrial_data_agent.cli:main"
```

4. Support `pip install -e .` for contributors.
5. Add `/help`, `/examples`, and `/status` commands to the CLI.
6. Add clearer progress feedback for live Gemini requests and sandbox analysis.
7. Add a dependency lock file with a reproducible update process.

## Priority 4: prove the product

1. Record a 60-90 second terminal demo and add it near the top of the README.
2. Publish an example generated CSV, PDF, and chart under `docs/examples/`.
3. Add a benchmark with at least 25 questions, expected answers, expected evidence, and safety-rejection cases.
4. Publish metrics such as deterministic accuracy, Gemini-plan validation rate, sandbox rejection rate, and median response time.
5. Add a comparison section explaining why the project differs from a generic CSV chatbot:
   - deterministic fallback
   - explicit schema catalog
   - provenance wiki
   - AST validation
   - restricted sandbox
   - evidence validation
   - generated-file validation
6. Create `good first issue` tasks for documentation, new deterministic intents, test fixtures, and CLI improvements.

## Priority 5: grow visibility

1. Create a polished release and attach example outputs.
2. Write a technical article explaining the validated-plan and sandbox architecture.
3. Share a short demo clip with one clear use case: finding delayed high-priority orders blocked by materials or machines.
4. Post progress regularly instead of sharing only once at launch.
5. Ask users for real schema examples and turn common mappings into documented adapters.
6. Respond quickly to issues and keep a small public roadmap.

## Suggested first five commits

```text
docs: replace README with public project overview
chore: remove legacy web files and accidental marker
fix: correct sample inventory data and clarify snapshot date
ci: add offline and Docker test workflows
community: add contribution, security, and issue templates
```
