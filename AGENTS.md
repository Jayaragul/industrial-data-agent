# Industrial Data Agent Notes

This project is CLI-only. Do not add a web app, bot adapter, dashboard, or API unless the owner explicitly changes the product shape.

The essential security rule is unchanged across all modules:

Gemini may plan and write analysis code, but Gemini never executes host functions directly. The harness validates plans, tool calls, generated code, sandbox results, generated files, and evidence before a final answer is shown.

Treat `data/input/orders.csv`, `data/input/machines.csv`, and `data/input/inventory.csv` as source data. They are copied into request-specific sandbox input folders and must never be modified in place.
