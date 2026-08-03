from __future__ import annotations

import json
from pathlib import Path

from agent.models import AnalysisOperation, AnalysisPlan, AnalysisStep, FinalResponse, Status
from agent.orchestrator import IndustrialDataAgent
from agent.planner import Planner
from agent.catalog_context import Catalog
from harness.plan_validator import PlanValidator
from gemini.client import GeminiClient
from agent.operation_executor import OperationExecutor


def test_gemini_json_parser_accepts_markdown_wrapped_json() -> None:
    client = GeminiClient()
    client.generate_text = lambda *args, **kwargs: type("Result", (), {"text": "```json\n{\"ok\": true}\n```"})()
    assert client.generate_json("ignored") == {"ok": True}


def test_gemini_json_parser_reports_malformed_json() -> None:
    client = GeminiClient()
    client.generate_text = lambda *args, **kwargs: type("Result", (), {"text": "not json"})()
    assert client.generate_json("ignored") is None
    assert client.last_error == "Gemini returned non-JSON text when JSON was required."


def test_gemini_plan_normalization_handles_realistic_shorthand() -> None:
    agent = IndustrialDataAgent()
    agent.gemini.generate_json = lambda *args, **kwargs: {
        "intent": "get_current_operational_status",
        "datasets": ["inventory", "machines"],
        "steps": [
            {"operation": "select", "dataset": "inventory", "fields": ["material_name", "available_quantity", "unit", "not_a_real_field"]},
            {"operation": "filter", "dataset": "machines", "fields": {"status": {"operator": "eq", "value": "RUNNING"}}},
        ],
        "operations": ["select", {"operation": "filter", "dataset": "machines", "fields": {"status": {"operator": "eq", "value": "RUNNING"}}}],
        "execution_method": "operation_executor",
        "requested_outputs": ["json"],
        "expected_result_columns": {"stock": ["material_name", "available_quantity"], "machines": ["machine_id"]},
        "risk_notes": "Stock units are not present in the catalog.",
    }
    understanding = Planner(Catalog()).fallback_understanding("Tell me current stock and working machines")
    plan = agent._create_plan("Tell me current stock and working machines", understanding, [], [])
    assert plan.intent == "catalog_analysis"
    assert plan.operations[0].operation == "select"
    assert plan.operations[1].parameters["conditions"][0]["field"] == "status"
    assert "not_a_real_field" not in plan.operations[0].fields
    assert "Gemini result-column groups were flattened for validation." in plan.risk_notes
    assert PlanValidator(Catalog()).validate(plan)


def test_gemini_understanding_normalizes_output_aliases() -> None:
    agent = IndustrialDataAgent()
    agent.gemini._client = object()
    agent.gemini.model = "test-model"
    agent.gemini.generate_json = lambda *args, **kwargs: {
        "intent": "data_lookup",
        "question_type": "data_lookup",
        "normalized_question": "Inspect inventory.",
        "requires_factory_data": True,
        "required_catalog_topics": ["inventory"],
        "requested_outputs": ["data", "graph"],
        "confidence": 0.9,
    }
    understanding = agent._understand("what stock do we have?")
    assert understanding.requested_outputs == ["cli", "charts"]
    assert understanding.intent == "catalog_analysis"


def test_plan_validator_is_a_hard_boundary() -> None:
    plan = Planner(Catalog()).fallback_plan("show orders", Planner(Catalog()).fallback_understanding("show orders"), [])
    plan.operations[0].fields = ["not_a_real_field"]
    try:
        PlanValidator(Catalog()).validate(plan)
    except ValueError as exc:
        assert "unknown field" in str(exc)
    else:
        raise AssertionError("invalid AI fields must be rejected")


def test_multi_dataset_executor_keeps_evidence_from_each_dataset() -> None:
    plan = AnalysisPlan(
        request_id="REQ-MULTI",
        user_question="show current stock and working machines",
        intent="catalog_analysis",
        datasets=["inventory", "machines"],
        steps=[AnalysisStep(step=1, description="Inspect stock and machine status.")],
        operations=[
            AnalysisOperation(operation="select", dataset="inventory", fields=["material_name", "available_quantity"]),
            AnalysisOperation(operation="filter", dataset="machines", fields=["status"], parameters={"conditions": [{"field": "status", "operator": "equals", "value": "RUNNING"}]}),
            AnalysisOperation(operation="select", dataset="machines", fields=["machine_id", "machine_type", "status"]),
        ],
        execution_method="operation_executor",
    )
    result = OperationExecutor(Catalog()).execute(plan)
    assert result["status"] == "success"
    datasets = {row["dataset"] for row in result["evidence"]}
    assert datasets == {"inventory", "machines"}


def test_final_response_accepts_only_validated_execution(monkeypatch) -> None:
    agent = IndustrialDataAgent()
    agent.gemini.generate_json = lambda *args, **kwargs: {
        "understanding": "Current inventory was inspected.",
        "summary": "2 materials are at or below reorder level.",
        "key_findings": ["MAT-RUBBER needs replenishment."],
        "evidence": ["MAT-RUBBER available quantity: 200"],
        "recommended_actions": ["Reorder MAT-RUBBER."],
        "confidence": "High",
        "limitations": [],
    }
    understanding = Planner(Catalog()).fallback_understanding("what materials are below reorder level?")
    plan = Planner(Catalog()).fallback_plan("what materials are below reorder level?", understanding, [])
    response = agent._final_answer(
        plan.user_question,
        understanding,
        [],
        plan,
        {"status": "success", "findings": [], "evidence": [], "limitations": [], "warnings": []},
        [],
    )
    assert response.status == Status.SUCCESS
    assert response.summary.startswith("2 materials")
    assert response.generated_files == []


def test_unavailable_response_writes_safe_diagnostic(tmp_path: Path, monkeypatch) -> None:
    agent = IndustrialDataAgent()
    monkeypatch.setattr("agent.orchestrator.PROJECT_ROOT", tmp_path)
    agent.gemini.last_error = "Gemini returned malformed JSON."
    response = agent._gemini_unavailable_response("REQ-TEST", stage="understanding", question="show stock")
    assert response.status == Status.GEMINI_UNAVAILABLE
    log = tmp_path / "runtime" / "logs" / "gemini.log"
    entry = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert entry["stage"] == "understanding"
    assert entry["error"] == "Gemini returned malformed JSON."
    if agent.gemini.api_key:
        assert agent.gemini.api_key not in log.read_text(encoding="utf-8")
