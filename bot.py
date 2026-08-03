from __future__ import annotations

from agent.orchestrator import IndustrialDataAgent
from data.ingestion import DataIngestionService
from knowledge.wiki import FactoryWiki

try:
    from rich.console import Console
    from rich.panel import Panel
except Exception:  # pragma: no cover
    Console = None
    Panel = None


def print_help(console=None) -> None:
    lines = [
        "/help     Show supported commands.",
        "/examples Show sample factory questions.",
        "/status   Show Gemini, mode, and active dataset status.",
        "/data     Show uploaded datasets.",
        "/debug on|off  Toggle safe diagnostics.",
        "/wiki lint     Check factory wiki completeness.",
        "exit      Quit the agent.",
    ]
    (console.print if console else print)("\n".join(lines))


def print_examples(console=None) -> None:
    lines = [
        "How many high priority orders are there?",
        "What orders are delayed?",
        "Which machines are running?",
        "What materials are below reorder level?",
        "Create a CSV and PDF report for delayed orders.",
    ]
    (console.print if console else print)("\n".join(f"- {line}" for line in lines))


def print_status(agent, ingestion, console=None) -> None:
    active = ingestion.active_sources()
    lines = [
        f"Mode: {'Live Gemini' if agent.gemini.connected else 'Offline/unavailable'}",
        f"Model: {agent.gemini.model or 'not configured'}",
        f"Datasets: {', '.join(active) if active else 'bundled demonstration data'}",
        f"Diagnostic log: {agent.catalog.root.parent / 'runtime' / 'logs' / 'gemini.log'}",
    ]
    (console.print if console else print)("\n".join(lines))


def main() -> None:
    agent = IndustrialDataAgent()
    ingestion = DataIngestionService(agent.catalog)
    wiki = FactoryWiki()
    mode = "Live" if agent.gemini.connected else "Offline fallback"
    if Console:
        console = Console()
        console.print(Panel.fit(f"Industrial Data Agent\nProvider: Google Gemini\nModel: {agent.gemini.model or 'not configured'}\nThinking budget: {agent.gemini.thinking_budget}\nMode: {mode}\nDatasets: orders, machines, inventory"))
        while True:
            question = console.input("[bold cyan]You > [/bold cyan]").strip()
            if question.lower() in {"exit", "quit"}:
                break
            if question.lower() == "/help":
                print_help(console)
                continue
            if question.lower() == "/examples":
                print_examples(console)
                continue
            if question.lower() == "/status":
                print_status(agent, ingestion, console)
                continue
            if question.lower() == "/debug on":
                agent.debug_enabled = True
                console.print("Debug mode enabled.")
                continue
            if question.lower() == "/debug off":
                agent.debug_enabled = False
                console.print("Debug mode disabled.")
                continue
            if question.lower().startswith("/ingest "):
                try:
                    _, dataset, file_path = question.split(maxsplit=2)
                    result = ingestion.ingest(dataset, file_path.strip().strip('"'))
                    console.print(f"Loaded {result['records']} {result['dataset']} records. The factory wiki was updated and future questions will use this file.")
                except ValueError as exc:
                    console.print(f"Could not load data: {exc}")
                continue
            if question.lower() == "/data":
                active = ingestion.active_sources()
                console.print("Active uploaded datasets: " + (", ".join(active) if active else "none; using bundled demonstration data"))
                continue
            if question.lower() == "/wiki lint":
                console.print("\n".join(wiki.lint()))
                continue
            if not question:
                continue
            response = agent.answer(question)
            console.print(response.to_display_text())
            if agent.debug_enabled:
                console.print("\n".join(agent.debug_lines))
    else:
        print(f"Industrial Data Agent\nProvider: Google Gemini\nModel: {agent.gemini.model or 'not configured'}\nThinking budget: {agent.gemini.thinking_budget}\nMode: {mode}\nDatasets: orders, machines, inventory")
        while True:
            question = input("You > ").strip()
            if question.lower() in {"exit", "quit"}:
                break
            if question.lower() == "/help":
                print_help()
                continue
            if question.lower() == "/examples":
                print_examples()
                continue
            if question.lower() == "/status":
                print_status(agent, ingestion)
                continue
            if question.lower() == "/debug on":
                agent.debug_enabled = True
                print("Debug mode enabled.")
                continue
            if question.lower() == "/debug off":
                agent.debug_enabled = False
                print("Debug mode disabled.")
                continue
            if question.lower().startswith("/ingest "):
                try:
                    _, dataset, file_path = question.split(maxsplit=2)
                    result = ingestion.ingest(dataset, file_path.strip().strip('"'))
                    print(f"Loaded {result['records']} {result['dataset']} records. The factory wiki was updated and future questions will use this file.")
                except ValueError as exc:
                    print(f"Could not load data: {exc}")
                continue
            if question.lower() == "/data":
                active = ingestion.active_sources()
                print("Active uploaded datasets: " + (", ".join(active) if active else "none; using bundled demonstration data"))
                continue
            if question.lower() == "/wiki lint":
                print("\n".join(wiki.lint()))
                continue
            if question:
                print(agent.answer(question).to_display_text())
                if agent.debug_enabled:
                    print("\n".join(agent.debug_lines))


if __name__ == "__main__":
    main()
