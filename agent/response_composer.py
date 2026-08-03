from __future__ import annotations

from agent.models import AnalysisPlan, FinalResponse, SandboxResult, Status


class ResponseComposer:
    def from_sandbox_result(self, plan: AnalysisPlan, result: SandboxResult, generated_files: list[str]) -> FinalResponse:
        findings = [item.get("message", str(item)) if isinstance(item, dict) else str(item) for item in result.findings]
        evidence = []
        for item in result.evidence[:10]:
            if isinstance(item, dict):
                record_id = item.get("record_id", "record")
                details = ", ".join(f"{key}={value}" for key, value in item.items() if key != "record_id")
                evidence.append(f"{record_id}: {details}")
            else:
                evidence.append(str(item))
        summary = findings[0] if findings else "The analysis completed successfully."
        return FinalResponse(
            understanding=plan.user_question,
            plan=[step.description for step in plan.steps],
            tools_used=["catalog_search", "sandbox_execute_python", "validate_sandbox_result"],
            data_used=plan.datasets,
            summary=summary,
            key_findings=findings,
            evidence=evidence,
            recommended_actions=self._recommendations(plan.intent, findings),
            confidence="High" if evidence or result.summary.get("records_returned", 0) == 0 else "Medium",
            limitations=result.limitations + result.warnings,
            generated_files=generated_files,
            request_id=plan.request_id,
        )

    def unsupported(self, plan: AnalysisPlan) -> FinalResponse:
        return FinalResponse(
            status=Status.UNSUPPORTED_REQUEST,
            understanding=plan.user_question,
            plan=[step.description for step in plan.steps],
            data_used=[],
            summary="Status: UNSUPPORTED_REQUEST",
            key_findings=["The request would require unsafe host, credential, shell, environment, or source-file access."],
            confidence="High",
            limitations=["The agent only analyzes approved industrial datasets through registered tools."],
            request_id=plan.request_id,
        )

    def execution_failed(self, plan: AnalysisPlan, error: str) -> FinalResponse:
        return FinalResponse(
            status=Status.EXECUTION_FAILED,
            understanding=plan.user_question,
            plan=[step.description for step in plan.steps],
            data_used=plan.datasets,
            summary="Status: EXECUTION_FAILED",
            key_findings=["The analysis code could not complete safely inside the sandbox."],
            confidence="High",
            limitations=[error],
            request_id=plan.request_id,
        )

    def deterministic(self, plan: AnalysisPlan, summary: str, findings: list[str], evidence: list[str]) -> FinalResponse:
        return FinalResponse(
            understanding=plan.user_question,
            plan=[step.description for step in plan.steps],
            tools_used=["catalog_search", "data_preview"],
            data_used=plan.datasets,
            summary=summary,
            key_findings=findings,
            evidence=evidence,
            recommended_actions=self._recommendations(plan.intent, findings),
            confidence="High",
            request_id=plan.request_id,
        )

    def _recommendations(self, intent: str, findings: list[str]) -> list[str]:
        if intent == "order_risk_analysis" and findings:
            return ["Review material shortages and machine availability before committing production dates."]
        if intent == "inventory_reorder_analysis" and findings:
            return ["Create replenishment actions for materials at or below reorder level."]
        if intent == "idle_machine_lookup" and findings:
            return ["Consider assigning idle compatible machines to high-priority open orders."]
        return []
