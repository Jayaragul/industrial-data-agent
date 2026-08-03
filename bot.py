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
