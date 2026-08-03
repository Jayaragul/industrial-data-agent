from __future__ import annotations

from datetime import datetime
import re
from uuid import uuid4

from agent.catalog_context import Catalog
from agent.models import AnalysisOperation, AnalysisPlan, AnalysisStep, QuestionUnderstanding


UNSAFE_TERMS = ["../", "..\\", "secrets", "environment", "import os", "subprocess", "shell", "modify ", "delete ", "rename "]


class Planner:
    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog

    def make_request_id(self) -> str:
        return f"REQ-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:4].upper()}"

    def fallback_understanding(self, question: str) -> QuestionUnderstanding:
        lowered = question.lower().strip()
        words = set(re.findall(r"[a-z0-9]+", lowered))

        def has_count_term() -> bool:
            return any(phrase in lowered for phrase in ["how many", "number", "count", "no of"])

        outputs = ["cli"]
        if "csv" in lowered:
            outputs.append("csv")
        if "excel" in lowered or "xlsx" in lowered:
            outputs.append("xlsx")
        if "pdf" in lowered or "report" in lowered:
            outputs.append("pdf")
        if "json" in lowered:
            outputs.append("json")
        if any(word in lowered for word in ["chart", "graph", "plot", "bar graph"]):
            outputs.append("charts")
        if not lowered:
            return QuestionUnderstanding(intent="needs_clarification", question_type="needs_clarification", normalized_question="Ask a factory data question.", requires_factory_data=False, requested_outputs=outputs, confidence=0.0)
        if any(term in lowered for term in UNSAFE_TERMS):
            return QuestionUnderstanding(intent="unsafe_request", question_type="unsupported", normalized_question=question, requires_factory_data=False, requested_outputs=outputs, confidence=0.99)
        operational_terms = {"order", "orders", "machine", "machines", "working", "running", "idle", "maintenance", "stock", "stocks", "inventory", "material", "materials"}
        asks_for_operations = bool(words & operational_terms)
        if not asks_for_operations and any(phrase in lowered for phrase in ["company name", "company nam", "name of the company", "about the company", "company details", "factory name", "factory nam", "name of the factory", "about the factory", "factory details", "tell about the factory", "acme precision manufacturing"]):
            return QuestionUnderstanding(intent="company_profile", question_type="capability", normalized_question="Provide the fictional company profile configured for this demonstration.", requires_factory_data=False, requested_outputs=outputs, confidence=0.98)
        if any(phrase in lowered for phrase in ["no of data", "number of data", "how many data", "no of dataset", "no of data set", "number of dataset", "number of data set", "how many dataset", "how many data set", "data set we have", "datasets we have", "dataset we have", "what data", "what datas", "what data do you have", "which data do you have", "available data", "data available", "what datasets", "which datasets", "what information do you have"]):
            return QuestionUnderstanding(intent="dataset_inventory", question_type="capability", normalized_question="Report the configured factory datasets available to the agent.", requires_factory_data=False, requested_outputs=outputs, confidence=0.98)
        if lowered in {"hi", "hello", "hey", "good morning", "good afternoon"} or (len(words) < 6 and bool(words & {"hi", "hello", "hey"})):
            return QuestionUnderstanding(intent="greeting", question_type="greeting", normalized_question="Greet the user.", requires_factory_data=False, requested_outputs=outputs, confidence=0.98)
        if any(phrase in lowered for phrase in ["what can you do", "help", "capabilit", "who are you", "what are you"]):
            return QuestionUnderstanding(intent="describe_capabilities", question_type="capability", normalized_question="Describe the agent's available capabilities.", requires_factory_data=False, requested_outputs=outputs, confidence=0.98)
        if any(word in lowered for word in ["chart", "graph", "plot"]) and len(self.catalog.relevant_datasets(question)) > 1:
            return QuestionUnderstanding(intent="catalog_analysis", question_type="report_generation", normalized_question="Create the requested visual analysis from available factory datasets.", requires_factory_data=True, required_catalog_topics=self.catalog.relevant_datasets(question), requested_outputs=outputs, confidence=0.86)
        relevant_datasets = self.catalog.relevant_datasets(question)
        if len(relevant_datasets) > 1 and asks_for_operations:
            return QuestionUnderstanding(intent="catalog_analysis", question_type="data_analysis", normalized_question="Answer the multi-dataset factory question using validated orders, machines, and inventory data.", requires_factory_data=True, required_catalog_topics=relevant_datasets, requested_outputs=outputs, confidence=0.82)
        priority_match = re.search(r"\b(high|medium|low)[\s-]+priority\b", lowered)
        if priority_match:
            priority = priority_match.group(1).upper()
            label = priority.lower()
            if has_count_term():
                return QuestionUnderstanding(intent="count_priority_orders", question_type="data_lookup", normalized_question=f"Count factory orders marked {priority} priority.", requires_factory_data=True, required_catalog_topics=["orders", "priority"], requested_outputs=outputs, confidence=0.95)
            return QuestionUnderstanding(intent="priority_orders", question_type="report_generation" if len(outputs) > 1 else "data_lookup", normalized_question=f"List factory orders marked {priority} priority.", requires_factory_data=True, required_catalog_topics=["orders", "priority"], requested_outputs=outputs, confidence=0.92)
        if "delayed" in words and has_count_term():
            return QuestionUnderstanding(intent="count_delayed_orders", question_type="data_lookup", normalized_question="Count delayed factory orders.", requires_factory_data=True, required_catalog_topics=["orders", "status"], requested_outputs=outputs, confidence=0.92)
        if "delayed" in words and ("order" in words or "orders" in words):
            return QuestionUnderstanding(intent="delayed_orders", question_type="report_generation" if len(outputs) > 1 else "data_lookup", normalized_question="List delayed factory orders.", requires_factory_data=True, required_catalog_topics=["orders", "status"], requested_outputs=outputs, confidence=0.9)
        maintenance_terms = {"maintenance", "maintanace", "maintainance", "repair", "service"}
        if words & maintenance_terms and ("machine" in words or "machines" in words) and has_count_term():
            return QuestionUnderstanding(intent="count_maintenance_machines", question_type="data_lookup", normalized_question="Count factory machines currently in maintenance.", requires_factory_data=True, required_catalog_topics=["machines", "status"], requested_outputs=outputs, confidence=0.92)
        if words & maintenance_terms and ("machine" in words or "machines" in words):
            return QuestionUnderstanding(intent="maintenance_machine_lookup", question_type="report_generation" if len(outputs) > 1 else "data_lookup", normalized_question="List factory machines currently in maintenance.", requires_factory_data=True, required_catalog_topics=["machines", "status"], requested_outputs=outputs, confidence=0.9)
        if "idle" in words and ("machine" in words or "machines" in words) and has_count_term():
            return QuestionUnderstanding(intent="count_idle_machines", question_type="data_lookup", normalized_question="Count idle factory machines.", requires_factory_data=True, required_catalog_topics=["machines", "status"], requested_outputs=outputs, confidence=0.92)
        if "idle" in words and ("machine" in words or "machines" in words):
            return QuestionUnderstanding(intent="idle_machine_lookup", question_type="report_generation" if len(outputs) > 1 else "data_lookup", normalized_question="List idle factory machines.", requires_factory_data=True, required_catalog_topics=["machines", "status"], requested_outputs=outputs, confidence=0.9)
        if any(word in words for word in ["reorder", "shortage", "shortages"]) or "below reorder" in lowered:
            intent = "count_reorder_materials" if has_count_term() else "inventory_reorder_analysis"
            normalized = "Count materials at or below reorder level." if intent == "count_reorder_materials" else "List materials at or below reorder level."
            return QuestionUnderstanding(intent=intent, question_type="report_generation" if len(outputs) > 1 else "data_lookup", normalized_question=normalized, requires_factory_data=True, required_catalog_topics=["inventory", "reorder"], requested_outputs=outputs, confidence=0.9)
        if re.search(r"\bord-\d+\b", lowered) and any(phrase in lowered for phrase in ["due date", "meet its due", "meet due", "at risk", "risk"]):
            return QuestionUnderstanding(intent="order_due_date_check", question_type="data_analysis", normalized_question="Check whether a specific factory order has due-date risk.", requires_factory_data=True, required_catalog_topics=["orders", "inventory availability", "machine capacity"], requested_outputs=outputs, confidence=0.9)
        if any(word in lowered for word in ["bottleneck", "at risk", "risk", "can meet", "meet its due", "downtime", "simulate"]):
            return QuestionUnderstanding(intent="detect_order_bottlenecks", question_type="simulation" if any(word in lowered for word in ["downtime", "simulate"]) else "data_analysis", normalized_question="Identify production constraints affecting current factory orders.", requires_factory_data=True, required_catalog_topics=["orders", "inventory availability", "machine capacity", "order bottleneck"], requested_outputs=outputs, confidence=0.8)
        if any(word in lowered for word in ["order", "orders"]):
            return QuestionUnderstanding(intent="list_factory_orders", question_type="report_generation" if len(outputs) > 1 else "data_lookup", normalized_question="List factory orders with status and production progress.", requires_factory_data=True, required_catalog_topics=["orders"], requested_outputs=outputs, confidence=0.82)
        if any(word in lowered for word in ["machine", "machines", "capacity", "idle"]):
            return QuestionUnderstanding(intent="machine_lookup", question_type="data_lookup", normalized_question="Inspect machine status and capacity.", requires_factory_data=True, required_catalog_topics=["machines"], requested_outputs=outputs, confidence=0.82)
        if any(word in lowered for word in ["inventory", "material", "reorder", "shortage"]):
            return QuestionUnderstanding(intent="inventory_lookup", question_type="data_lookup", normalized_question="Inspect inventory availability and replenishment status.", requires_factory_data=True, required_catalog_topics=["inventory"], requested_outputs=outputs, confidence=0.82)
        return QuestionUnderstanding(intent="needs_clarification", question_type="needs_clarification", normalized_question=question, requires_factory_data=False, requested_outputs=outputs, confidence=0.3)

    def deterministic_plan(self, question: str) -> AnalysisPlan:
        """Compatibility entry point for local tests and non-Gemini development mode."""
        understanding = self.fallback_understanding(question)
        context = [entry["path"] for entry in self.catalog.search(" ".join([understanding.normalized_question, *understanding.required_catalog_topics]))]
        return self.fallback_plan(question, understanding, context)

    def fallback_plan(self, question: str, intent: QuestionUnderstanding, catalog_context: list[str]) -> AnalysisPlan:
        request_id = self.make_request_id()
        if intent.question_type == "unsupported":
            return AnalysisPlan(request_id=request_id, user_question=question, intent=intent.intent, execution_method="unsupported", steps=[AnalysisStep(step=1, description="Decline the unsafe request.")])
        if intent.intent == "dataset_inventory":
            return AnalysisPlan(request_id=request_id, user_question=question, intent=intent.intent, execution_method="catalog", steps=[AnalysisStep(step=1, description="List active approved datasets and their schemas.")], operations=[AnalysisOperation(operation="list_datasets")], expected_result_columns=["dataset", "row_count", "fields"])
        datasets = {
            "list_factory_orders": ["orders"], "delayed_orders": ["orders"], "priority_orders": ["orders"],
            "machine_lookup": ["machines"], "idle_machine_lookup": ["machines"], "maintenance_machine_lookup": ["machines"],
            "inventory_lookup": ["inventory"], "inventory_reorder_analysis": ["inventory"],
            "detect_order_bottlenecks": ["orders", "machines", "inventory"], "count_priority_orders": ["orders"],
            "count_delayed_orders": ["orders"], "count_idle_machines": ["machines"], "count_maintenance_machines": ["machines"], "count_reorder_materials": ["inventory"],
            "order_due_date_check": ["orders", "machines", "inventory"],
            "catalog_analysis": self.catalog.relevant_datasets(question),
        }.get(intent.intent, [])
        if intent.intent == "count_priority_orders":
            steps = ["Load order records.", "Filter records by the requested priority.", "Count the matching orders."]
        elif intent.intent == "count_delayed_orders":
            steps = ["Load order records.", "Filter records with DELAYED status.", "Count the matching orders."]
        elif intent.intent == "count_idle_machines":
            steps = ["Load machine records.", "Filter records with IDLE status.", "Count the matching machines."]
        elif intent.intent == "count_maintenance_machines":
            steps = ["Load machine records.", "Filter records with MAINTENANCE status.", "Count the matching machines."]
        elif intent.intent == "count_reorder_materials":
            steps = ["Load inventory records.", "Filter materials at or below reorder level.", "Count the matching materials."]
        elif intent.intent == "delayed_orders":
            steps = ["Load order records.", "Filter records with DELAYED status.", "Display delayed order evidence."]
        elif intent.intent == "priority_orders":
            steps = ["Load order records.", "Filter records by the requested priority.", "Display matching order evidence."]
        elif intent.intent == "idle_machine_lookup":
            steps = ["Load machine records.", "Filter records with IDLE status.", "Display idle machine evidence."]
        elif intent.intent == "maintenance_machine_lookup":
            steps = ["Load machine records.", "Filter records with MAINTENANCE status.", "Display maintenance machine evidence."]
        elif intent.intent == "inventory_reorder_analysis":
            steps = ["Load inventory records.", "Filter materials at or below reorder level.", "Display material evidence."]
        elif intent.intent == "order_due_date_check":
            steps = ["Load orders, machines, and inventory.", "Find the requested order.", "Check material availability and compatible machine availability.", "Return due-date risk evidence."]
        elif intent.intent == "list_factory_orders":
            steps = ["Load order records.", "Calculate remaining quantity and progress.", "Display order status, quantity, priority and due date."]
        elif intent.intent == "detect_order_bottlenecks":
            steps = ["Select incomplete orders.", "Calculate remaining quantity for each order.", "Compare material requirements with usable inventory.", "Identify compatible healthy machines and effective capacity.", "Compare expected completion with due dates and identify bottlenecks."]
        elif intent.intent == "catalog_analysis":
            steps = ["Inspect the selected dataset schemas.", "Use the requested fields to compute the answer.", "Return only validated result fields and limitations."]
        elif intent.intent == "machine_lookup":
            steps = ["Load machine records.", "Review status, health and available capacity.", "Return the requested machine evidence."]
        else:
            steps = ["Load inventory records.", "Compare available and reserved quantities with reorder levels.", "Return the requested inventory evidence."]
        deterministic_intents = {"list_factory_orders", "delayed_orders", "priority_orders", "machine_lookup", "idle_machine_lookup", "maintenance_machine_lookup", "inventory_lookup", "inventory_reorder_analysis", "count_priority_orders", "count_delayed_orders", "count_idle_machines", "count_maintenance_machines", "count_reorder_materials", "order_due_date_check"}
        method = "deterministic_query" if intent.intent in deterministic_intents else "operation_executor" if intent.intent == "catalog_analysis" or intent.question_type in {"data_analysis", "simulation", "report_generation"} else "deterministic_query"
        operations = [AnalysisOperation(operation="inspect_schema", dataset=dataset) for dataset in datasets]
        if intent.intent.startswith("count_"):
            operations.extend([AnalysisOperation(operation="filter", dataset=datasets[0], fields=["priority" if "priority" in intent.intent else "status"]), AnalysisOperation(operation="count", dataset=datasets[0])])
        elif intent.intent in {"delayed_orders", "priority_orders", "idle_machine_lookup", "maintenance_machine_lookup", "inventory_reorder_analysis"}:
            operations.append(AnalysisOperation(operation="filter", dataset=datasets[0]))
        elif intent.intent == "order_due_date_check":
            operations.extend([AnalysisOperation(operation="filter", dataset="orders", fields=["order_id"]), AnalysisOperation(operation="join", fields=["required_material_id", "material_id", "required_machine_type", "machine_type"]), AnalysisOperation(operation="compare")])
        elif datasets:
            operations.append(AnalysisOperation(operation="select", dataset=datasets[0]))
        if intent.intent == "catalog_analysis" and "inventory" in datasets and "machines" in datasets and any(term in question.lower() for term in ["working", "running"]):
            operations = [
                AnalysisOperation(operation="select", dataset="inventory", fields=["material_name", "available_quantity", "reserved_quantity", "unit"]),
                AnalysisOperation(operation="filter", dataset="machines", fields=["status"], parameters={"conditions": [{"field": "status", "operator": "equals", "value": "RUNNING"}]}),
                AnalysisOperation(operation="select", dataset="machines", fields=["machine_id", "machine_type", "status"]),
            ]
        return AnalysisPlan(request_id=request_id, user_question=question, intent=intent.intent, catalog_context=catalog_context, datasets=datasets, steps=[AnalysisStep(step=index + 1, description=step) for index, step in enumerate(steps)], operations=operations, execution_method=method, requested_outputs=intent.requested_outputs, expected_result_columns=["record_id", "finding", "evidence"])
