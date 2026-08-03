from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any

from agent.catalog_context import Catalog
from agent.code_generator import CodeGenerator
from agent.models import AnalysisOperation, AnalysisPlan, AnalysisStep, AuditRecord, FinalResponse, PROJECT_ROOT, QuestionUnderstanding, SandboxResult, Status
from agent.operation_executor import OperationExecutor
from agent.execution_router import ExecutionRouter
from agent.planner import Planner
from agent.result_interpreter import sandbox_file_paths
from gemini.client import GeminiClient
from harness.audit_logger import AuditLogger
from harness.orchestrator import build_tool_registry
from harness.plan_validator import PlanValidator
from knowledge.wiki import FactoryWiki
from data.repository import DatasetRepository


class IndustrialDataAgent:
    def __init__(self) -> None:
        self.catalog = Catalog()
        self.planner = Planner(self.catalog)
        self.plan_validator = PlanValidator(self.catalog)
        self.code_generator = CodeGenerator()
        self.operation_executor = OperationExecutor(self.catalog)
        self.repository = DatasetRepository(self.catalog)
        self.execution_router = ExecutionRouter(self.repository, self.operation_executor, self._execute_query)
        self.registry = build_tool_registry(self.catalog)
        self.audit = AuditLogger()
        self.gemini = GeminiClient()
        self.company_profile = (PROJECT_ROOT / ".codex" / "skills" / "industrial-answer-contract" / "references" / "company-profile.md").read_text(encoding="utf-8")
        self.debug_enabled = False
        self.debug_lines: list[str] = []
        self.gemini_unavailable = False
        self._current_question = ""

    def answer(self, question: str) -> FinalResponse:
        self.debug_lines = []
        self.gemini_unavailable = False
        self._current_question = question
        understanding = self._understand(question)
        if self.gemini_unavailable:
            return self._gemini_unavailable_response(stage="understanding")
        if understanding.question_type == "needs_clarification" or understanding.confidence < 0.5:
            response = FinalResponse(status=Status.NEEDS_CLARIFICATION, understanding="The request could not be matched to a supported factory question.", summary="Please ask about factory orders, machines, inventory, bottlenecks, simulations, or a CSV/PDF report.", confidence="Low", request_id=self.planner.make_request_id())
            return response
        if understanding.question_type == "unsupported":
            plan = AnalysisPlan(request_id=self.planner.make_request_id(), user_question=question, intent=understanding.intent, execution_method="unsupported", steps=[AnalysisStep(step=1, description="Decline the unsafe request.")])
            response = FinalResponse(status=Status.UNSUPPORTED_REQUEST, understanding="The request requires unsafe access outside approved factory data.", summary="Status: UNSUPPORTED_REQUEST", key_findings=["Only read-only analysis of approved factory datasets is available."], confidence="High", request_id=plan.request_id)
            self._audit(plan, response)
            return response

        if understanding.intent == "dataset_inventory":
            catalog_entries = self.catalog.search(understanding.normalized_question)
            catalog_context = [entry["path"] for entry in catalog_entries]
            plan = self._create_plan(question, understanding, catalog_entries, catalog_context)
            try:
                plan = self.plan_validator.validate(plan)
            except ValueError as exc:
                self.gemini_unavailable = True
                return self._gemini_unavailable_response(stage="catalog_plan_validation")
            if plan.execution_method != "catalog":
                self.gemini_unavailable = True
                return self._gemini_unavailable_response(plan.request_id, stage="catalog_execution_method")
            execution = self.execution_router.execute(plan)
            self._attach_execution_metadata(execution, plan.datasets)
            response = self._final_answer(question, understanding, catalog_entries, plan, execution, [])
            self._audit(plan, response, None, execution)
            return response
        if not understanding.requires_factory_data:
            plan = AnalysisPlan(request_id=self.planner.make_request_id(), user_question=question, intent=understanding.intent, execution_method="deterministic_query", requested_outputs=["cli"], steps=[])
            response = self._final_answer(question, understanding, [], plan, {"status": "success", "findings": [], "evidence": [], "limitations": [], "warnings": []}, [])
            self._audit(plan, response)
            return response

        catalog_entries = self.catalog.search(" ".join([understanding.normalized_question, *understanding.required_catalog_topics]))
        catalog_context = [entry["path"] for entry in catalog_entries]
        self.debug_lines.append(f"Catalog entries used: {len(catalog_context)}")
        plan = self._create_plan(question, understanding, catalog_entries, catalog_context)
        try:
            plan = self.plan_validator.validate(plan)
        except ValueError as exc:
            response = FinalResponse(status=Status.NEEDS_CLARIFICATION, understanding=understanding.normalized_question, summary=f"Status: NEEDS_CLARIFICATION\n{exc}", confidence="Low", request_id=plan.request_id)
            self._audit(plan, response)
            return response
        if plan.execution_method == "insufficient_data":
            self.gemini_unavailable = True
            response = self._gemini_unavailable_response(plan.request_id, stage="insufficient_data_plan")
            self._audit(plan, response)
            return response
        self.debug_lines.append(f"Datasets selected: {', '.join(plan.datasets)}")
        self.debug_lines.append(f"Execution method: {plan.execution_method}")

        if plan.execution_method in {"deterministic", "deterministic_query"} and plan.intent not in {"machine_lookup", "inventory_lookup"}:
            execution = self.execution_router.execute(plan)
            self._attach_execution_metadata(execution, plan.datasets)
            if execution.get("status") != "success":
                response = FinalResponse(status=Status.INSUFFICIENT_DATA, understanding=understanding.normalized_question, data_used=plan.datasets, summary="Status: INSUFFICIENT_DATA", key_findings=execution.get("limitations", ["No safe read-only query is defined for this request."]), confidence="High", request_id=plan.request_id)
                self._audit(plan, response, None, execution)
                return response
            generated_files = self._write_deterministic_outputs(plan, execution)
            code = None
        else:
            execution = self.execution_router.execute(plan)
            self._attach_execution_metadata(execution, plan.datasets)
            if execution.get("status") == "success" and not execution.get("limitations"):
                generated_files = execution.get("generated_files", [])
                code = None
                response = self._final_answer(question, understanding, catalog_entries, plan, execution, generated_files)
                self._audit(plan, response, code, execution)
                return response
            code = self._generate_code(question, understanding, plan, catalog_entries)
            if self.gemini_unavailable:
                response = self._gemini_unavailable_response(plan.request_id, stage="code_generation")
                self._audit(plan, response)
                return response
            execution = self.registry.call("sandbox_execute_python", request_id=plan.request_id, code=code, datasets=plan.datasets, requested_outputs=plan.requested_outputs)
            self.debug_lines.append(f"Sandbox execution: {'success' if execution.get('status') == 'success' else 'failed'}")
            if execution.get("status") != "success":
                response = FinalResponse(status=Status.EXECUTION_FAILED, understanding=understanding.normalized_question, plan=[step.description for step in plan.steps], data_used=plan.datasets, summary="Status: EXECUTION_FAILED", key_findings=["The approved analysis could not complete safely."], limitations=[str(execution.get("error") or execution.get("stderr") or execution.get("validation") or "sandbox execution failed")], confidence="High", request_id=plan.request_id)
                self._audit(plan, response, code, execution)
                return response
            result = SandboxResult.model_validate(execution["result"])
            execution = result.model_dump()
            generated_files = sandbox_file_paths(plan.request_id, result)
            self._attach_execution_metadata(execution, plan.datasets)

        response = self._final_answer(question, understanding, catalog_entries, plan, execution, generated_files)
        self._audit(plan, response, code, execution)
        return response

    def _understand(self, question: str) -> QuestionUnderstanding:
        local_result = self.planner.fallback_understanding(question)
        if not self.gemini.connected:
            if self._offline_mode():
                self.debug_lines.append("Gemini planning call: offline fallback")
                return local_result
            self.gemini_unavailable = True
            self.debug_lines.append("Gemini planning call: unavailable")
            return local_result
        available_data = {name: self.repository.get_schema(name) for name in ("orders", "machines", "inventory")}
        prompt = f"""You are the understanding stage of a data-analysis agent. Interpret the user's question using the available data catalog and return JSON only with intent, question_type (greeting, capability, data_lookup, data_analysis, simulation, report_generation, unsupported, needs_clarification), normalized_question, requires_factory_data, required_catalog_topics, requested_outputs, confidence.

Accept natural wording, typos, implied comparisons, rankings, counts, summaries, and report requests when they can be answered from the catalog. Set requires_factory_data=true when the question can be answered from the datasets. Use needs_clarification only when the requested entity, metric, or time basis is genuinely absent or ambiguous. Do not invent columns, values, relationships, or data outside the catalog. A request for CSV means requested_outputs includes csv; Excel/XLSX means xlsx.

Questions asking who you are, your name, what you can do, or for help are capability questions: use intent describe_capabilities, question_type capability, and requires_factory_data false. Mixed identity/capability questions remain capability questions and must not select a dataset. Questions asking for the company or factory name are company_profile capability questions and must not select a dataset.

Available data catalog: {json.dumps(available_data)}
User message: {question}"""
        payload = self.gemini.generate_json(prompt)
        if payload:
            try:
                if payload.get("required_catalog_topics") is None:
                    payload["required_catalog_topics"] = []
                if payload.get("requested_outputs") is None:
                    payload["requested_outputs"] = ["cli"]
                output_aliases = {"data": "cli", "text": "cli", "excel": "xlsx", "spreadsheet": "xlsx", "chart": "charts", "graph": "charts"}
                if isinstance(payload.get("requested_outputs"), list):
                    payload["requested_outputs"] = [output_aliases.get(str(output).lower(), str(output).lower()) for output in payload["requested_outputs"]]
                    payload["requested_outputs"] = [output for output in payload["requested_outputs"] if output in {"cli", "csv", "xlsx", "pdf", "json", "charts"}] or ["cli"]
                result = QuestionUnderstanding.model_validate(payload)
                data_question_types = {"data_lookup", "data_analysis", "simulation", "report_generation"}
                if not result.requested_outputs:
                    result.requested_outputs = ["cli"]
                if local_result.requires_factory_data and not result.requires_factory_data:
                    self.debug_lines.append("Gemini intent corrected: operational catalog data detected")
                    result.intent = local_result.intent
                    result.question_type = local_result.question_type
                    result.normalized_question = local_result.normalized_question
                    result.requires_factory_data = True
                    result.required_catalog_topics = local_result.required_catalog_topics
                    result.requested_outputs = sorted(set(result.requested_outputs + local_result.requested_outputs))
                    result.confidence = max(result.confidence, local_result.confidence)
                if result.question_type in data_question_types:
                    result.requires_factory_data = True
                    result.confidence = max(result.confidence, 0.7)
                intent_aliases = {
                    "greet": "greeting",
                    "hello": "greeting",
                    "capability": "describe_capabilities",
                    "help": "describe_capabilities",
                    "data_inventory": "dataset_inventory",
                }
                result.intent = intent_aliases.get(result.intent, result.intent)
                known_intents = {
                    "greeting", "describe_capabilities", "company_profile", "dataset_inventory",
                    "list_factory_orders", "delayed_orders", "priority_orders", "count_priority_orders",
                    "count_delayed_orders", "machine_lookup", "idle_machine_lookup", "maintenance_machine_lookup", "count_idle_machines", "count_maintenance_machines",
                    "inventory_lookup", "inventory_reorder_analysis", "count_reorder_materials",
                    "order_due_date_check", "detect_order_bottlenecks", "order_risk_analysis",
                    "needs_clarification", "unsafe_request", "catalog_analysis",
                }
                if result.intent not in known_intents | data_question_types:
                    result.intent = "catalog_analysis"
                elif result.intent in data_question_types:
                    result.intent = "catalog_analysis"
                if result.intent == "catalog_analysis":
                    result.question_type = "data_analysis"
                    result.requires_factory_data = True
                    result.confidence = max(result.confidence, 0.7)
                self.debug_lines.append("Gemini planning call: completed")
                self.debug_lines.append(f"Detected intent: {result.intent}")
                return result
            except Exception:
                pass
        if self._offline_mode():
            self.debug_lines.append("Gemini planning call: offline fallback")
            return local_result
        if local_result.requires_factory_data:
            self.debug_lines.append("Gemini planning call: validated local routing fallback")
            return local_result
        if not self.gemini.last_error:
            self.gemini.last_error = "Gemini understanding response failed validation."
        self.gemini_unavailable = True
        self.debug_lines.append("Gemini planning call: unavailable")
        return local_result

    def _create_plan(self, question: str, intent: QuestionUnderstanding, entries: list[dict[str, Any]], context_paths: list[str]) -> AnalysisPlan:
        compact_context = [{"path": item["path"], "content": item["content"]} for item in entries]
        available_data = {name: self.repository.get_schema(name) for name in ("orders", "machines", "inventory")}
        relationships = self.catalog.load_yaml("relationships.yaml").get("relationships", [])
        prompt = f"""You are a data-analysis planner. Do not answer the question directly. Return JSON only with intent, datasets, steps, operations, execution_method, requested_outputs, expected_result_columns, risk_notes.

For every plan, identify the value or entity requested; select only catalog datasets and fields; decide whether filtering, ranking, aggregation, grouping, joining, comparison, calculation, or time analysis is needed; and provide exact ordered steps. If the data cannot answer the question, set execution_method to insufficient_data and explain why in risk_notes.

Each operation must have operation, optional dataset, fields, and parameters. Allowed operations are: list_datasets, inspect_schema, filter, select, sort, limit, group_by, count, sum, average, minimum, maximum, distinct, join, calculate, compare, date_difference, trend. Never invent fields, records, values, or relationships. Use catalog for dataset inventory, operation_executor for structured data analysis, deterministic_query only as an optimization for exact registered lookups, and sandbox_python only for complex analysis the operation executor cannot express. Include csv or xlsx in requested_outputs only when the user asks for that file.

Question: {question}
Understanding: {intent.model_dump_json()}
Complete active catalog: {json.dumps(available_data, default=str)}
Permitted relationships: {json.dumps(relationships, default=str)}
Relevant catalog: {json.dumps(compact_context, default=str)}"""
        budget = 4096 if intent.question_type in {"data_analysis", "simulation", "report_generation"} else 2048
        payload = self.gemini.generate_json(prompt, thinking_budget=budget)
        if payload:
            try:
                risk_notes = payload.get("risk_notes", [])
                if isinstance(risk_notes, str):
                    risk_notes = [risk_notes] if risk_notes.strip() else []
                normalized_steps = []
                for index, item in enumerate(payload.get("steps", []), start=1):
                    if isinstance(item, str):
                        item = {"description": item}
                    if isinstance(item, dict) and "description" not in item:
                        operation_name = item.get("operation") or item.get("type") or "analysis"
                        item = {**item, "description": f"Execute {operation_name} operation."}
                    if isinstance(item, dict) and "step" not in item:
                        item = {**item, "step": index}
                    normalized_steps.append(item)
                steps = [AnalysisStep.model_validate(item) for item in normalized_steps]
                raw_operations = payload.get("operations", [])
                step_operations = [item for item in payload.get("steps", []) if isinstance(item, dict) and item.get("operation")]
                if step_operations and (not raw_operations or any(isinstance(item, str) for item in raw_operations) or len(raw_operations) < len(step_operations)):
                    raw_operations = step_operations
                    risk_notes.append("Gemini operations were completed from the detailed ordered steps.")
                operations = [self._normalize_gemini_operation(item, payload.get("datasets", []), risk_notes) for item in raw_operations]
                known_intents = {"greeting", "describe_capabilities", "company_profile", "dataset_inventory", "list_factory_orders", "delayed_orders", "priority_orders", "count_priority_orders", "count_delayed_orders", "machine_lookup", "idle_machine_lookup", "maintenance_machine_lookup", "count_idle_machines", "count_maintenance_machines", "inventory_lookup", "inventory_reorder_analysis", "count_reorder_materials", "detect_order_bottlenecks", "order_risk_analysis", "order_due_date_check", "catalog_analysis"}
                planned_intent = payload.get("intent", intent.intent)
                if planned_intent not in known_intents:
                    risk_notes.append(f"Gemini intent '{planned_intent}' was normalized to catalog_analysis.")
                    planned_intent = "catalog_analysis"
                requested_outputs = payload.get("requested_outputs", intent.requested_outputs)
                if not isinstance(requested_outputs, list) or not requested_outputs:
                    requested_outputs = intent.requested_outputs
                expected_columns = payload.get("expected_result_columns", ["record_id", "finding", "evidence"])
                if isinstance(expected_columns, dict):
                    expected_columns = [str(column) for columns in expected_columns.values() if isinstance(columns, list) for column in columns]
                    risk_notes.append("Gemini result-column groups were flattened for validation.")
                elif isinstance(expected_columns, list) and any(isinstance(column, dict) for column in expected_columns):
                    expected_columns = [str(column_name) for column in expected_columns for column_name in (column.get("fields", []) if isinstance(column, dict) else [column])]
                    risk_notes.append("Gemini result-column objects were flattened for validation.")
                plan = AnalysisPlan(request_id=self.planner.make_request_id(), user_question=question, intent=planned_intent, catalog_context=context_paths, datasets=payload.get("datasets", []), steps=steps, operations=operations, execution_method=payload.get("execution_method", "deterministic_query"), requested_outputs=requested_outputs, expected_result_columns=expected_columns, risk_notes=risk_notes)
                if plan.datasets and plan.steps and self._plan_matches_question(question, plan):
                    return plan
            except Exception as exc:
                self.debug_lines.append(f"Gemini plan rejected: {exc}")
        if self._offline_mode():
            self.debug_lines.append("Gemini plan: offline fallback plan")
            return self.planner.fallback_plan(question, intent, context_paths)
        if intent.requires_factory_data:
            self.debug_lines.append("Gemini plan: validated local plan fallback")
            return self.planner.fallback_plan(question, intent, context_paths)
        return AnalysisPlan(request_id=self.planner.make_request_id(), user_question=question, intent=intent.intent, catalog_context=context_paths, execution_method="insufficient_data", risk_notes=["Gemini did not return a valid analysis plan."])

    def _normalize_gemini_operation(self, item: Any, datasets: list[str], risk_notes: list[str]) -> AnalysisOperation:
        """Convert common Gemini shorthand into the strict operation contract."""
        if isinstance(item, str):
            item = {"operation": item}
        if not isinstance(item, dict):
            raise ValueError("Gemini returned an invalid operation.")
        item = dict(item)
        if item.get("operation") == "data_analysis":
            item["operation"] = "inspect_schema"
        fields = item.get("fields", [])
        parameters = dict(item.get("parameters") or {})
        if isinstance(fields, dict):
            conditions = []
            for field, condition in fields.items():
                if isinstance(condition, dict):
                    conditions.append({"field": field, **condition})
                else:
                    conditions.append({"field": field, "operator": "equals", "value": condition})
            fields = list(fields)
            if conditions:
                parameters.setdefault("conditions", conditions)
        if not isinstance(fields, list):
            fields = [str(fields)]
        allowed = {column["name"] for dataset in datasets for column in self.catalog.dataset(dataset).get("columns", [])}
        safe_fields = [field for field in fields if field in allowed or field == "*"]
        dropped = sorted(set(str(field) for field in fields) - set(safe_fields))
        if dropped:
            risk_notes.append(f"Gemini referenced unavailable field(s); ignored: {', '.join(dropped)}.")
        item["fields"] = safe_fields
        item["parameters"] = parameters
        item["dataset"] = item.get("dataset") or (datasets[0] if datasets else None)
        return AnalysisOperation.model_validate(item)

    def _plan_matches_question(self, question: str, plan: AnalysisPlan) -> bool:
        lowered = question.lower()
        if re.search(r"\b(high|medium|low)[\s-]+priority\b", lowered):
            is_count = any(word in lowered for word in ["how many", "number", "count", "no of"])
            expected_intent = "count_priority_orders" if is_count else "priority_orders"
            return plan.intent == expected_intent and plan.datasets == ["orders"]
        return True

    def _execute_query(self, plan: AnalysisPlan) -> dict[str, Any]:
        rows = self._read_dataset(plan.datasets[0])
        evidence: list[dict[str, Any]] = []
        if plan.intent == "list_factory_orders":
            for row in rows:
                quantity, completed = float(row["order_quantity"]), float(row["completed_quantity"])
                evidence.append({"record_id": row["order_id"], "product": row["product"], "status": row["status"], "progress_percent": round(completed / quantity * 100) if quantity else 0, "remaining_units": int(quantity - completed), "priority": row["priority"], "due_date": row["due_date"]})
        elif plan.intent == "delayed_orders":
            delayed = [row for row in rows if row.get("status", "").upper() == "DELAYED"]
            for row in delayed:
                quantity, completed = float(row["order_quantity"]), float(row["completed_quantity"])
                evidence.append({"record_id": row["order_id"], "product": row["product"], "status": row["status"], "progress_percent": round(completed / quantity * 100) if quantity else 0, "remaining_units": int(quantity - completed), "priority": row["priority"], "due_date": row["due_date"]})
            return {"status": "success", "summary": {"records_analysed": len(rows), "records_returned": len(evidence)}, "findings": [{"message": self._count_message(len(evidence), "delayed order")}], "evidence": evidence, "warnings": [], "limitations": []}
        elif plan.intent == "priority_orders":
            priority = self._requested_priority(plan.user_question)
            matching_orders = [row for row in rows if row.get("priority", "").upper() == priority]
            for row in matching_orders:
                quantity, completed = float(row["order_quantity"]), float(row["completed_quantity"])
                evidence.append({"record_id": row["order_id"], "product": row["product"], "status": row["status"], "progress_percent": round(completed / quantity * 100) if quantity else 0, "remaining_units": int(quantity - completed), "priority": row["priority"], "due_date": row["due_date"]})
            return {"status": "success", "summary": {"records_analysed": len(rows), "records_returned": len(evidence)}, "findings": [{"message": self._count_message(len(evidence), f"{priority.lower()}-priority order")}], "evidence": evidence, "warnings": [], "limitations": []}
        elif plan.intent == "count_priority_orders":
            priority = self._requested_priority(plan.user_question)
            matching_orders = [row for row in rows if row.get("priority", "").upper() == priority]
            return {"status": "success", "summary": {"records_analysed": len(rows), "records_returned": len(matching_orders)}, "findings": [{"message": self._count_message(len(matching_orders), f"{priority.lower()}-priority order")}], "evidence": [], "warnings": [], "limitations": []}
        elif plan.intent == "count_delayed_orders":
            delayed = [row for row in rows if row.get("status", "").upper() == "DELAYED"]
            return {"status": "success", "summary": {"records_analysed": len(rows), "records_returned": len(delayed)}, "findings": [{"message": self._count_message(len(delayed), "delayed order")}], "evidence": [], "warnings": [], "limitations": []}
        elif plan.intent == "machine_lookup":
            evidence = [{"record_id": row["machine_id"], "machine_type": row["machine_type"], "status": row["status"], "capacity_per_hour": row["capacity_per_hour"], "health_score": row["health_score"]} for row in rows]
        elif plan.intent == "idle_machine_lookup":
            idle = [row for row in rows if row.get("status", "").upper() == "IDLE"]
            evidence = [{"record_id": row["machine_id"], "machine_type": row["machine_type"], "status": row["status"], "capacity_per_hour": row["capacity_per_hour"], "health_score": row["health_score"]} for row in idle]
            return {"status": "success", "summary": {"records_analysed": len(rows), "records_returned": len(evidence)}, "findings": [{"message": self._count_message(len(evidence), "idle machine")}], "evidence": evidence, "warnings": [], "limitations": []}
        elif plan.intent == "maintenance_machine_lookup":
            maintenance = [row for row in rows if row.get("status", "").upper() == "MAINTENANCE"]
            evidence = [{"record_id": row["machine_id"], "machine_type": row["machine_type"], "status": row["status"], "capacity_per_hour": row["capacity_per_hour"], "health_score": row["health_score"], "next_available_at": row["next_available_at"]} for row in maintenance]
            return {"status": "success", "summary": {"records_analysed": len(rows), "records_returned": len(evidence)}, "findings": [{"message": self._count_message(len(evidence), "machine in maintenance", "machines in maintenance")}], "evidence": evidence, "warnings": [], "limitations": []}
        elif plan.intent == "count_idle_machines":
            idle = [row for row in rows if row.get("status", "").upper() == "IDLE"]
            return {"status": "success", "summary": {"records_analysed": len(rows), "records_returned": len(idle)}, "findings": [{"message": self._count_message(len(idle), "idle machine")}], "evidence": [], "warnings": [], "limitations": []}
        elif plan.intent == "count_maintenance_machines":
            maintenance = [row for row in rows if row.get("status", "").upper() == "MAINTENANCE"]
            return {"status": "success", "summary": {"records_analysed": len(rows), "records_returned": len(maintenance)}, "findings": [{"message": self._count_message(len(maintenance), "machine in maintenance", "machines in maintenance")}], "evidence": [], "warnings": [], "limitations": []}
        elif plan.intent == "inventory_lookup":
            evidence = [{"record_id": row["material_id"], "material_name": row["material_name"], "available_quantity": row["available_quantity"], "reserved_quantity": row["reserved_quantity"], "reorder_level": row["reorder_level"]} for row in rows]
        elif plan.intent == "inventory_reorder_analysis":
            reorder = [row for row in rows if float(row.get("available_quantity", 0) or 0) <= float(row.get("reorder_level", 0) or 0)]
            evidence = [{"record_id": row["material_id"], "material_name": row["material_name"], "available_quantity": row["available_quantity"], "reserved_quantity": row["reserved_quantity"], "reorder_level": row["reorder_level"]} for row in reorder]
            return {"status": "success", "summary": {"records_analysed": len(rows), "records_returned": len(evidence)}, "findings": [{"message": self._reorder_message(len(evidence))}], "evidence": evidence, "warnings": [], "limitations": []}
        elif plan.intent == "count_reorder_materials":
            reorder = [row for row in rows if float(row.get("available_quantity", 0) or 0) <= float(row.get("reorder_level", 0) or 0)]
            return {"status": "success", "summary": {"records_analysed": len(rows), "records_returned": len(reorder)}, "findings": [{"message": self._reorder_message(len(reorder))}], "evidence": [], "warnings": [], "limitations": []}
        elif plan.intent == "order_due_date_check":
            return self._check_order_due_date(plan)
        else:
            return {"status": "error", "findings": [], "evidence": [], "limitations": ["No safe read-only query is defined for this intent."]}
        return {"status": "success", "summary": {"records_analysed": len(rows), "records_returned": len(evidence)}, "findings": [{"message": f"{len(evidence)} matching {plan.datasets[0]} records found."}], "evidence": evidence, "warnings": [], "limitations": []}

    def _check_order_due_date(self, plan: AnalysisPlan) -> dict[str, Any]:
        match = re.search(r"\bORD-\d+\b", plan.user_question, flags=re.IGNORECASE)
        if not match:
            return {"status": "error", "findings": [], "evidence": [], "limitations": ["Please include an order ID, for example ORD-1001."]}
        order_id = match.group(0).upper()
        orders = self._read_dataset("orders")
        machines = self._read_dataset("machines")
        inventory = self._read_dataset("inventory")
        order = next((row for row in orders if row.get("order_id", "").upper() == order_id), None)
        if not order:
            return {"status": "error", "findings": [], "evidence": [], "limitations": [f"No order found for {order_id}."]}

        material = next((row for row in inventory if row.get("material_id") == order.get("required_material_id")), None)
        usable_inventory = None
        material_shortage = False
        if material:
            usable_inventory = float(material.get("available_quantity", 0) or 0) - float(material.get("reserved_quantity", 0) or 0)
            material_shortage = usable_inventory < float(order.get("required_material_quantity", 0) or 0)
        else:
            material_shortage = True

        compatible_machines = [
            row for row in machines
            if row.get("machine_type") == order.get("required_machine_type") and row.get("status", "").upper() in {"IDLE", "RUNNING"}
        ]
        reasons = []
        if material_shortage:
            reasons.append("material shortage")
        if not compatible_machines:
            reasons.append("no compatible available machine")
        if order.get("status", "").upper() == "DELAYED":
            reasons.append("order is already delayed")

        summary = f"{order_id} is at risk of missing its due date." if reasons else f"{order_id} has no current due-date risk in the available data."
        evidence = [{
            "record_id": order_id,
            "product": order.get("product"),
            "status": order.get("status"),
            "due_date": order.get("due_date"),
            "main_bottleneck": reasons[0] if reasons else "none found",
            "risk_reasons": "; ".join(reasons) if reasons else "none found",
            "required_material": order.get("required_material_id"),
            "required_material_quantity": order.get("required_material_quantity"),
            "usable_inventory": usable_inventory,
            "compatible_available_machines": ", ".join(row["machine_id"] for row in compatible_machines) or "none",
        }]
        return {"status": "success", "summary": {"records_analysed": len(orders), "records_returned": 1}, "findings": [{"message": summary}], "evidence": evidence, "warnings": [], "limitations": []}

    def _count_message(self, count: int, singular: str, plural: str | None = None) -> str:
        noun = singular if count == 1 else plural or f"{singular}s"
        return f"{count} {noun} found."

    def _requested_priority(self, question: str) -> str:
        match = re.search(r"\b(high|medium|low)[\s-]+priority\b", question, flags=re.IGNORECASE)
        return match.group(1).upper() if match else "HIGH"

    def _reorder_message(self, count: int) -> str:
        noun = "material is" if count == 1 else "materials are"
        return f"{count} {noun} at or below reorder level."

    def _write_deterministic_outputs(self, plan: AnalysisPlan, execution: dict[str, Any]) -> list[str]:
        evidence = execution.get("evidence", [])
        if not evidence:
            return []
        output_dir = PROJECT_ROOT / "runtime" / "outputs" / plan.request_id
        output_dir.mkdir(parents=True, exist_ok=True)
        generated_files: list[str] = []
        safe_name = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in plan.intent)
        if "csv" in plan.requested_outputs:
            csv_path = output_dir / f"{safe_name}.csv"
            fieldnames = list(evidence[0].keys())
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(evidence)
            generated_files.append(str(csv_path))
        if "json" in plan.requested_outputs:
            json_path = output_dir / f"{safe_name}.json"
            json_path.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
            generated_files.append(str(json_path))
        if "xlsx" in plan.requested_outputs:
            import pandas as pd
            xlsx_path = output_dir / f"{safe_name}.xlsx"
            pd.DataFrame(evidence).to_excel(xlsx_path, index=False)
            generated_files.append(str(xlsx_path))
        return generated_files

    def _generate_code(self, question: str, intent: QuestionUnderstanding, plan: AnalysisPlan, entries: list[dict[str, Any]]) -> str:
        prompt = f"""Generate only safe Python code for the approved sandbox. The code may read only /sandbox/input/{', /sandbox/input/'.join(f'{name}.csv' for name in plan.datasets)}, must write only /sandbox/output, and must create /sandbox/output/result.json with status, summary, findings, evidence, warnings, limitations, generated_files. Use pandas; no network, shell, environment access, or imports outside standard analysis libraries.\nQuestion: {question}\nIntent: {intent.intent}\nPlan: {plan.model_dump_json()}\nCatalog: {json.dumps(entries, default=str)}"""
        result = self.gemini.generate_text(prompt, thinking_budget=4096)
        code = result.text.strip().removeprefix("```python").removeprefix("```").removesuffix("```").strip()
        if code and "result.json" in code:
            self.debug_lines.append("Generated code: yes (Gemini)")
            return code
        if self.gemini.last_error:
            self.gemini_unavailable = True
            self.debug_lines.append("Generated code: Gemini unavailable")
            return ""
        self.debug_lines.append("Generated code: Gemini returned unusable code")
        return ""

    def _final_answer(self, question: str, intent: QuestionUnderstanding, entries: list[dict[str, Any]], plan: AnalysisPlan, execution: dict[str, Any], generated_files: list[str]) -> FinalResponse:
        prompt = f"""You are producing the final answer for an industrial data agent. Return JSON only with understanding, summary, key_findings, evidence, recommended_actions, confidence, limitations. Answer using only validated execution results. Do not invent IDs, quantities, dates, or causes. Do not reveal chain-of-thought. Give only the direct answer and essential factual details; do not mention plans, tools, confidence, request IDs, or internal processing. Include generated files only when the user requested a file and it exists in Generated files. For greetings/capabilities, be concise and do not mention data, evidence, or a plan. For a company_profile question, answer using the supplied Company demonstration context, even when no operational dataset is required. For a direct count, return the count as the complete answer without record details unless requested. If the evidence is insufficient, say exactly what data is needed. Every list field (key_findings, evidence, recommended_actions, limitations) must be a JSON array; use [] when empty.\nCompany demonstration context (not operational evidence): {self.company_profile}\nOriginal question: {question}\nIntent: {intent.model_dump_json()}\nRelevant catalog paths: {[item['path'] for item in entries]}\nAnalysis plan: {plan.model_dump_json()}\nValidated execution result: {json.dumps(execution, default=str)}\nGenerated files: {generated_files}"""
        budget = 4096 if plan.execution_method == "sandbox_python" else 2048
        payload = self.gemini.generate_json(prompt, thinking_budget=budget)
        if payload:
            try:
                def list_field(name: str) -> list[str]:
                    value = payload.get(name, [])
                    if value is None:
                        return []
                    if isinstance(value, str):
                        return [value]
                    return [str(item) for item in value] if isinstance(value, list) else [str(value)]

                confidence = str(payload.get("confidence", "Medium")).capitalize()
                if confidence not in {"High", "Medium", "Low"}:
                    confidence = "Medium"
                response = FinalResponse(request_id=plan.request_id, understanding=payload["understanding"], plan=[] if not intent.requires_factory_data else [step.description for step in plan.steps], tools_used=[] if not intent.requires_factory_data else (["catalog_search", "sandbox_execute_python", "validate_sandbox_result"] if plan.execution_method == "sandbox_python" else ["catalog_search", "data_query"]), data_used=[] if not intent.requires_factory_data else plan.datasets, summary=payload["summary"], key_findings=list_field("key_findings"), evidence=list_field("evidence"), recommended_actions=list_field("recommended_actions"), confidence=confidence, limitations=list_field("limitations"), generated_files=generated_files)
                self.debug_lines.append("Gemini final-answer call: completed")
                self.debug_lines.append("Fallback used: no")
                return response
            except Exception:
                pass
        if self._offline_mode():
            self.debug_lines.append("Gemini final answer: offline fallback answer")
            return self._local_final(intent, plan, execution, generated_files)
        if intent.requires_factory_data:
            self.debug_lines.append("Gemini final answer: validated evidence fallback")
            return self._local_final(intent, plan, execution, generated_files)
        self.gemini_unavailable = True
        self.debug_lines.append("Gemini final-answer call: unavailable")
        return self._gemini_unavailable_response(plan.request_id, stage="final_answer")

    def _gemini_unavailable_response(self, request_id: str | None = None, *, stage: str = "unknown", question: str | None = None) -> FinalResponse:
        log_path = self._log_gemini_issue(request_id, stage, question)
        return FinalResponse(
            status=Status.GEMINI_UNAVAILABLE,
            understanding="Gemini could not process the question.",
            summary="Gemini is currently unavailable. Please try again shortly.",
            key_findings=[f"Diagnostic log: {log_path}"],
            confidence="High",
            request_id=request_id or self.planner.make_request_id(),
        )

    def _log_gemini_issue(self, request_id: str | None = None, stage: str = "unknown", question: str | None = None) -> str:
        """Append safe Gemini diagnostics without recording credentials."""
        log_path = PROJECT_ROOT / "runtime" / "logs" / "gemini.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "question": question if question is not None else self._current_question,
            "stage": stage,
            "model_configured": bool(self.gemini.model),
            "api_key_configured": bool(self.gemini.api_key),
            "connected": self.gemini.connected,
            "error": self.gemini.last_error or "No error returned; check model and API configuration.",
        }
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return str(log_path)

    def _offline_mode(self) -> bool:
        """Return whether deterministic/local fallback is explicitly enabled."""
        return any(os.getenv(name, "false").lower() == "true" for name in (
            "INDUSTRIAL_AGENT_OFFLINE_MODE",
            "INDUSTRIAL_AGENT_ALLOW_LOCAL_TEST_MODE",
        ))

    def _local_final(self, intent: QuestionUnderstanding, plan: AnalysisPlan, execution: dict[str, Any], generated_files: list[str]) -> FinalResponse:
        if intent.question_type in {"greeting", "capability"}:
            if intent.intent == "company_profile":
                return FinalResponse(understanding="Company profile request.", summary="The company is Acme Precision Manufacturing Pvt. Ltd.", key_findings=["Fictional demonstration company based in Pune, Maharashtra, India.", "It manufactures industrial components using CNC machining, lathe work, press forming, and assembly."], confidence="High", request_id=plan.request_id)
            if intent.intent == "dataset_inventory":
                datasets = []
                for name in ("orders", "machines", "inventory"):
                    schema = self.catalog.dataset(name)
                    fields = ", ".join(column["name"] for column in schema.get("columns", []))
                    datasets.append(f"{name}: {fields}")
                execution_evidence = execution.get("evidence", [])
                return FinalResponse(understanding="Configured dataset inventory request.", summary=execution.get("findings", [{"message": "The active dataset catalog is available."}])[0].get("message", "The active dataset catalog is available."), key_findings=[str(item) for item in execution_evidence] or datasets, data_used=[], confidence="High", request_id=plan.request_id, dataset_versions=execution.get("dataset_versions", {}))
            return FinalResponse(understanding="You asked what this agent can help with.", summary="Hello! I can analyse your factory's orders, machines and inventory.", key_findings=["Show current, pending or delayed orders", "Check machine status and capacity", "Find inventory shortages and order bottlenecks", "Estimate due-date risk, simulate downtime, and generate CSV or PDF reports"], confidence="High", request_id=plan.request_id)
        evidence = execution.get("evidence", [])
        findings = execution.get("findings", [])
        finding_text = [item.get("message", str(item)) if isinstance(item, dict) else str(item) for item in findings]
        evidence_text = [", ".join(f"{key.replace('_', ' ')}: {value}" for key, value in item.items()) if isinstance(item, dict) else str(item) for item in evidence]
        summary = finding_text[0] if finding_text else "The approved analysis completed."
        return FinalResponse(understanding=intent.normalized_question, plan=[step.description for step in plan.steps], tools_used=["catalog_search", "data_query"] if plan.execution_method == "deterministic_query" else ["catalog_search", "sandbox_execute_python", "validate_sandbox_result"], data_used=plan.datasets, summary=summary, key_findings=finding_text[1:] if finding_text and finding_text[0] == summary else finding_text, evidence=evidence_text, confidence="High" if evidence else "Medium", limitations=execution.get("limitations", []) + execution.get("warnings", []), generated_files=generated_files, request_id=plan.request_id, dataset_versions=execution.get("dataset_versions", {}))

    def _read_dataset(self, dataset: str) -> list[dict[str, str]]:
        return self.repository.read(dataset).astype(str).to_dict(orient="records")

    def _attach_execution_metadata(self, execution: dict[str, Any], datasets: list[str]) -> None:
        if datasets and execution.get("status") == "success":
            execution.setdefault("dataset_versions", self.repository.versions(datasets))

    def _audit(self, plan: AnalysisPlan, response: FinalResponse, code: str | None = None, execution: dict[str, Any] | None = None) -> None:
        self.audit.save(AuditRecord(request_id=plan.request_id, user_question=plan.user_question, catalog_entries_used=plan.catalog_context, analysis_plan=plan.model_dump(), generated_code_hash=hashlib.sha256(code.encode("utf-8")).hexdigest() if code else None, code_validation_result=(execution or {}).get("validation", {}), sandbox_execution_status=(execution or {}).get("status"), sandbox_execution_time=(execution or {}).get("execution_time"), datasets_used=plan.datasets, generated_files=response.generated_files, evidence_validation={"status": "validated" if response.status == Status.SUCCESS else "not_successful"}, final_status=response.status.value, model_name=self.gemini.model or None, token_usage={"mode": "gemini_configured" if self.gemini.connected else "offline_fallback"}, warnings=response.limitations, errors=[] if response.status == Status.SUCCESS else response.key_findings))
        FactoryWiki().record_query(plan.user_question, plan.intent)
