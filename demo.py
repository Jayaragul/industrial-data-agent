"""Run the deterministic two-minute hackathon demonstration."""

from __future__ import annotations

import os

os.environ.setdefault("INDUSTRIAL_AGENT_OFFLINE_MODE", "true")
os.environ.setdefault("GEMINI_DISABLE_LIVE", "1")

from agent.orchestrator import IndustrialDataAgent


QUESTIONS = [
    "How many high priority orders are there?",
    "What orders are delayed?",
    "Which machines are idle?",
    "What materials are below reorder level?",
    "Create a CSV report for high priority orders.",
]


def main() -> None:
    agent = IndustrialDataAgent()
    print("Industrial Data Agent - offline hackathon demo")
    print("Data: bundled orders, machines, and inventory CSV files\n")
    for question in QUESTIONS:
        print(f"> {question}")
        response = agent.answer(question)
        print(response.to_display_text())
        print("\n" + "-" * 72 + "\n")


if __name__ == "__main__":
    main()

