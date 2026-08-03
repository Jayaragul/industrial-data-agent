from __future__ import annotations

from agent.models import AnalysisPlan
from agent.catalog_context import Catalog


class PlanValidator:
    def __init__(self, catalog: Catalog | None = None) -> None:
        self.catalog = catalog or Catalog()

    def validate(self, plan: AnalysisPlan) -> AnalysisPlan:
        if plan.execution_method in {"sandbox", "sandbox_python"} and not plan.datasets:
            raise ValueError("sandbox plans must name at least one dataset")
        if plan.execution_method in {"deterministic", "deterministic_query", "operation_executor"} and plan.intent not in {"greeting", "describe_capabilities", "company_profile", "dataset_inventory"} and not plan.datasets:
            raise ValueError("data plans must name at least one dataset")
        expected_datasets = {
            "list_factory_orders": ["orders"],
            "delayed_orders": ["orders"],
            "priority_orders": ["orders"],
            "count_priority_orders": ["orders"],
            "count_delayed_orders": ["orders"],
            "machine_lookup": ["machines"],
            "idle_machine_lookup": ["machines"],
            "maintenance_machine_lookup": ["machines"],
            "count_idle_machines": ["machines"],
            "count_maintenance_machines": ["machines"],
            "inventory_lookup": ["inventory"],
            "inventory_reorder_analysis": ["inventory"],
            "count_reorder_materials": ["inventory"],
            "detect_order_bottlenecks": ["orders", "machines", "inventory"],
            "order_risk_analysis": ["orders", "machines", "inventory"],
            "order_due_date_check": ["orders", "machines", "inventory"],
        }
        if plan.intent in expected_datasets and plan.datasets != expected_datasets[plan.intent]:
            raise ValueError(f"{plan.intent} must use datasets: {', '.join(expected_datasets[plan.intent])}")
        deterministic_intents = {
            "list_factory_orders",
            "delayed_orders",
            "priority_orders",
            "count_priority_orders",
            "count_delayed_orders",
            "machine_lookup",
            "idle_machine_lookup",
            "maintenance_machine_lookup",
            "count_idle_machines",
            "count_maintenance_machines",
            "inventory_lookup",
            "inventory_reorder_analysis",
            "count_reorder_materials",
            "order_due_date_check",
        }
        if plan.intent in deterministic_intents and plan.execution_method != "deterministic_query":
            raise ValueError(f"{plan.intent} must use deterministic_query")
        if plan.datasets and not plan.operations:
            raise ValueError("data plans must include at least one validated analysis operation")
        if plan.execution_method == "catalog" and plan.intent == "dataset_inventory" and not any(operation.operation == "list_datasets" for operation in plan.operations):
            raise ValueError("dataset inventory plans must request list_datasets")
        all_fields = {column["name"] for dataset in plan.datasets for column in self.catalog.dataset(dataset).get("columns", [])}
        for operation in plan.operations:
            if operation.dataset and operation.dataset not in plan.datasets:
                raise ValueError(f"operation {operation.operation} references an unselected dataset: {operation.dataset}")
            invalid_fields = sorted(set(operation.fields) - all_fields - {"*"})
            if invalid_fields:
                raise ValueError(f"operation {operation.operation} uses unknown field(s): {', '.join(invalid_fields)}")
        if "cli" not in plan.requested_outputs:
            plan.requested_outputs.insert(0, "cli")
        return plan
