---
name: industrial-answer-contract
description: Enforce concise, evidence-backed user responses for the Industrial Data Agent. Use when changing question handling, Gemini prompts, CLI rendering, validation, or report/file generation so the agent returns only a valid answer, a necessary concise summary, and explicitly requested generated files.
---

# Industrial Answer Contract

Apply this contract to every user question.

## Company Context

Use [company-profile.md](references/company-profile.md) as fictional demonstration context when a company name or operational background is needed. Do not present this dummy profile as live factory evidence. Live conclusions must still come from validated datasets and tools.

1. Return conclusions only when supported by validated tool or sandbox evidence.
2. Do not replace an unavailable capability, uncertain intent, missing data, or failed execution with a nearby factory answer.
3. Use `Status: NEEDS_CLARIFICATION`, `Status: INSUFFICIENT_DATA`, `Status: UNSUPPORTED_REQUEST`, or `Status: EXECUTION_FAILED` when applicable, followed by the one action needed from the user.
4. Keep normal CLI output to the direct answer and essential factual details. Do not show plans, internal reasoning, tool names, confidence, request IDs, or raw debug data.
5. Include a short summary only when it helps answer a multi-record or analysis question.
6. List generated files only when the user requested an output file and a validated file was actually generated.
7. Keep debug diagnostics behind `/debug on`; never reveal private model reasoning.
