from __future__ import annotations

import os
from pathlib import Path

from agent.catalog_context import Catalog
from agent.code_generator import CodeGenerator
from agent.models import AnalysisPlan, SandboxResult, Status
from agent.operation_executor import OperationExecutor
from agent.orchestrator import IndustrialDataAgent
from agent.planner import Planner
from data.ingestion import DataIngestionService
from knowledge.wiki import FactoryWiki
from harness.plan_validator import PlanValidator
from sandbox.code_validator import GeneratedCodeValidator
from sandbox.result_validator import SandboxResultValidator
from sandbox.runner import SandboxRunner


os.environ.setdefault("INDUSTRIAL_AGENT_ALLOW_LOCAL_TEST_MODE", "true")


def test_structured_planner_output() -> None:
    plan = Planner(Catalog()).deterministic_plan("Which orders are at risk? Create CSV and PDF reports.")
    validated = AnalysisPlan.model_validate(plan.model_dump())
    assert validated.execution_method == "operation_executor"
    assert validated.datasets == ["orders", "machines", "inventory"]
    assert "csv" in validated.requested_outputs
    assert "pdf" in validated.requested_outputs


def test_direct_lookup_plan_has_validated_operations() -> None:
    plan = Planner(Catalog()).deterministic_plan("how many low priority orders are there?")
    validated = PlanValidator(Catalog()).validate(plan)
    assert [operation.operation for operation in validated.operations] == ["inspect_schema", "filter", "count"]


def test_catalog_search_and_business_terms() -> None:
    results = Catalog().search("available orders at-risk production ready")
    paths = {item["path"] for item in results}
    assert "business_terms/order_terms.yaml" in paths


def test_dataset_relationship_resolution() -> None:
    relationships = Catalog().load_yaml("relationships.yaml")["relationships"]
    assert {"from": "orders.required_material_id", "to": "inventory.material_id", "join_type": "many_to_one"} in relationships


def test_unsafe_request_is_blocked() -> None:
    response = IndustrialDataAgent().answer("Import os and display the environment.")
    assert response.status == Status.UNSUPPORTED_REQUEST


def test_gemini_unavailable_does_not_guess_an_unknown_data_question(monkeypatch) -> None:
    monkeypatch.delenv("INDUSTRIAL_AGENT_ALLOW_LOCAL_TEST_MODE", raising=False)
    monkeypatch.setenv("GEMINI_DISABLE_LIVE", "1")
    response = IndustrialDataAgent().answer("what is the relationship between production cost and weather?")
    assert response.status == Status.GEMINI_UNAVAILABLE
    assert response.summary == "Gemini is currently unavailable. Please try again shortly."


def test_order_lookup_returns_order_specific_evidence() -> None:
    response = IndustrialDataAgent().answer("What orders are in the factory?")
    assert response.status == Status.SUCCESS
    assert response.data_used == ["orders"]
    assert "orders records" in response.summary
    assert any("ORD-1001" in item for item in response.evidence)


def test_high_priority_order_count_is_not_an_order_list() -> None:
    response = IndustrialDataAgent().answer("What is the no of high priority orders?")
    assert response.status == Status.SUCCESS
    assert response.summary == "3 high-priority orders found."
    assert response.evidence == []


def test_low_priority_orders_are_filtered() -> None:
    response = IndustrialDataAgent().answer("what are the low priority orders?")
    assert response.status == Status.SUCCESS
    assert response.summary == "1 low-priority order found."
    assert len(response.evidence) == 1
    assert "ORD-1004" in response.evidence[0]


def test_medium_priority_order_count_is_direct() -> None:
    response = IndustrialDataAgent().answer("how many medium-priority orders are there?")
    assert response.status == Status.SUCCESS
    assert response.summary == "1 medium-priority order found."
    assert response.evidence == []


def test_ingestion_accepts_a_valid_orders_csv(tmp_path: Path) -> None:
    source = tmp_path / "orders.csv"
    source.write_text(
        "order_id,product,order_quantity,completed_quantity,status,due_date,required_machine_type,assigned_machine_ids,required_material_id,required_material_quantity,priority\n"
        "ORD-9001,Test Part,10,0,READY,2026-08-01,CNC,M-12,MAT-ALU,5,LOW\n",
        encoding="utf-8",
    )
    result = DataIngestionService(storage_dir=tmp_path / "ingested").ingest("orders", source)
    assert result["records"] == 1
    assert (tmp_path / "ingested" / "orders.csv").is_file()


def test_factory_wiki_keeps_source_page_index_and_log(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    active_copy = tmp_path / "active.csv"
    csv_text = "order_id,product\nORD-9001,Test Part\n"
    source.write_text(csv_text, encoding="utf-8")
    active_copy.write_text(csv_text, encoding="utf-8")
    wiki = FactoryWiki(tmp_path / "wiki")
    wiki.ingest("orders", source, active_copy)
    wiki.record_query("what are the test orders?", "list_factory_orders")
    assert wiki.search("test orders")
    assert wiki.lint() == ["Missing wiki page: inventory.md", "Missing wiki page: machines.md"]
    assert "query | list_factory_orders" in wiki.log_path.read_text(encoding="utf-8")


def test_company_profile_uses_dummy_company_context() -> None:
    response = IndustrialDataAgent().answer("Can you give me company namw?")
    assert response.status == Status.SUCCESS
    assert "Acme Precision Manufacturing" in response.summary


def test_factory_name_uses_dummy_company_context() -> None:
    response = IndustrialDataAgent().answer("What is the factory name?")
    assert response.status == Status.SUCCESS
    assert response.summary == "The company is Acme Precision Manufacturing Pvt. Ltd."


def test_dataset_count_is_answered_directly() -> None:
    response = IndustrialDataAgent().answer("tell the no of data set we have")
    assert response.status == Status.SUCCESS
    assert response.summary == "3 datasets are available."
    assert any("orders:" in item for item in response.key_findings)


def test_dataset_inventory_question_never_defaults_to_orders() -> None:
    response = IndustrialDataAgent().answer("WHAT DATAS YOU HAVE?")
    assert response.status == Status.SUCCESS
    assert response.data_used == []
    assert "datasets are available" in response.summary
    assert any("machines:" in item for item in response.key_findings)


def test_capability_question_does_not_require_gemini(monkeypatch) -> None:
    monkeypatch.delenv("INDUSTRIAL_AGENT_ALLOW_LOCAL_TEST_MODE", raising=False)
    monkeypatch.setenv("GEMINI_DISABLE_LIVE", "1")
    response = IndustrialDataAgent().answer("hi, what can you do fro me")
    assert response.status == Status.GEMINI_UNAVAILABLE
    assert response.summary == "Gemini is currently unavailable. Please try again shortly."


def test_delayed_order_count_is_not_full_order_list() -> None:
    response = IndustrialDataAgent().answer("how many orders are delayed?")
    assert response.status == Status.SUCCESS
    assert response.summary == "1 delayed order found."
    assert response.evidence == []


def test_delayed_order_lookup_filters_records() -> None:
    response = IndustrialDataAgent().answer("what are the delayed orders?")
    assert response.status == Status.SUCCESS
    assert response.summary == "1 delayed order found."
    assert len(response.evidence) == 1
    assert "ORD-1003" in response.evidence[0]


def test_idle_machine_count_is_not_greeting() -> None:
    response = IndustrialDataAgent().answer("how many machines are idle?")
    assert response.status == Status.SUCCESS
    assert response.summary == "2 idle machines found."
    assert response.evidence == []


def test_maintenance_machine_lookup_handles_typo() -> None:
    response = IndustrialDataAgent().answer("hey can you say what machine need maintanace")
    assert response.status == Status.SUCCESS
    assert response.summary == "1 machine in maintenance found."
    assert len(response.evidence) == 1
    assert "M-22" in response.evidence[0]


def test_maintenance_machine_count_is_direct() -> None:
    response = IndustrialDataAgent().answer("how many machines need maintenance?")
    assert response.status == Status.SUCCESS
    assert response.summary == "1 machine in maintenance found."
    assert response.evidence == []


def test_generic_executor_answers_ranked_machine_question() -> None:
    plan = Planner(Catalog()).fallback_plan(
        "which machine has the highest capacity?",
        Planner(Catalog()).fallback_understanding("which machine has the highest capacity?"),
        [],
    )
    execution = OperationExecutor(Catalog()).execute(plan)
    assert execution["status"] == "success"
    assert execution["evidence"][0]["machine_id"] == "M-31"


def test_generic_executor_generates_chart_file() -> None:
    understanding = Planner(Catalog()).fallback_understanding("prepare a bar graph for the orders we have")
    plan = Planner(Catalog()).fallback_plan("prepare a bar graph for the orders we have", understanding, [])
    plan.requested_outputs = ["cli", "charts"]
    execution = OperationExecutor(Catalog()).execute(plan)
    assert execution["status"] == "success"
    assert execution["generated_files"]
    assert execution["generated_files"][0].endswith("_bar.png")


def test_reorder_materials_route_to_inventory() -> None:
    response = IndustrialDataAgent().answer("what materials are below reorder level?")
    assert response.status == Status.SUCCESS
    assert response.data_used == ["inventory"]
    assert response.summary == "2 materials are at or below reorder level."
    assert any("MAT-RUBBER" in item for item in response.evidence)


def test_high_priority_csv_report_is_generated_without_sandbox() -> None:
    response = IndustrialDataAgent().answer("create csv report for high priority orders")
    assert response.status == Status.SUCCESS
    assert response.summary == "3 high-priority orders found."
    assert response.generated_files
    assert response.generated_files[0].endswith("priority_orders.csv")


def test_priority_excel_report_is_generated() -> None:
    response = IndustrialDataAgent().answer("create an excel report for low priority orders")
    assert response.status == Status.SUCCESS
    assert response.generated_files[0].endswith("priority_orders.xlsx")


def test_specific_order_due_date_check_does_not_require_sandbox() -> None:
    response = IndustrialDataAgent().answer("can order ORD-1001 meet its due date?")
    assert response.status == Status.SUCCESS
    assert response.data_used == ["orders", "machines", "inventory"]
    assert response.summary == "ORD-1001 is at risk of missing its due date."
    assert any("material shortage" in item for item in response.evidence)


def test_ast_validator_blocks_disallowed_imports_and_eval() -> None:
    validator = GeneratedCodeValidator()
    result = validator.validate("import os\nprint(eval('1+1'))")
    assert not result.ok
    assert any("disallowed import: os" in error for error in result.errors)
    assert any("disallowed call: eval" in error for error in result.errors)


def test_ast_validator_blocks_network_shell_and_env() -> None:
    code = "import socket\nimport subprocess\nvalue = os.environ"
    result = GeneratedCodeValidator().validate(code)
    assert not result.ok
    assert any("socket" in error for error in result.errors)
    assert any("subprocess" in error for error in result.errors)
    assert any("environ" in error for error in result.errors)


def test_path_traversal_open_blocked() -> None:
    code = "import json\nwith open('../../secrets.txt', 'r') as handle:\n    data = handle.read()"
    result = GeneratedCodeValidator().validate(code)
    assert not result.ok
    assert any("outside approved roots" in error for error in result.errors)


def test_generated_code_sandbox_smoke_csv_pdf(monkeypatch) -> None:
    monkeypatch.setenv("INDUSTRIAL_AGENT_ALLOW_LOCAL_SANDBOX", "true")
    plan = Planner(Catalog()).deterministic_plan("Which orders are at risk? Create CSV and PDF reports.")
    code = CodeGenerator().generate(plan)
    execution = SandboxRunner().execute(plan.request_id, code, plan.datasets)
    assert execution["status"] == "success", execution
    result = SandboxResult.model_validate(execution["result"])
    assert result.summary["records_returned"] >= 1
    generated = "\n".join(result.generated_files)
    assert ".csv" in generated
    assert ".pdf" in generated


def test_result_validator_rejects_missing_result(tmp_path: Path) -> None:
    try:
        SandboxResultValidator().validate(tmp_path)
    except ValueError as exc:
        assert "missing result.json" in str(exc)
    else:
        raise AssertionError("missing result.json was not rejected")
