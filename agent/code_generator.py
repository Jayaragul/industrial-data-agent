from __future__ import annotations

from agent.models import AnalysisPlan


class CodeGenerator:
    def generate(self, plan: AnalysisPlan) -> str:
        outputs = set(plan.requested_outputs)
        intent = plan.intent
        include_csv = "csv" in outputs
        include_xlsx = "xlsx" in outputs
        include_pdf = "pdf" in outputs
        include_json = "json" in outputs
        include_charts = "charts" in outputs
        return f'''
import json
import pandas as pd
from datetime import datetime

REQUEST_ID = {plan.request_id!r}
INTENT = {intent!r}
GENERATE_CSV = {include_csv!r}
GENERATE_XLSX = {include_xlsx!r}
GENERATE_PDF = {include_pdf!r}
GENERATE_JSON = {include_json!r}
GENERATE_CHARTS = {include_charts!r}

orders = pd.read_csv("/sandbox/input/orders.csv") if "orders" in {plan.datasets!r} else pd.DataFrame()
machines = pd.read_csv("/sandbox/input/machines.csv") if "machines" in {plan.datasets!r} else pd.DataFrame()
inventory = pd.read_csv("/sandbox/input/inventory.csv") if "inventory" in {plan.datasets!r} else pd.DataFrame()

findings = []
evidence = []
warnings = []
limitations = []
generated_files = []
records_analysed = 0
records_returned = 0
detail_rows = []

if INTENT == "delayed_orders":
    source = orders.copy()
    records_analysed = len(source)
    if "status" in source.columns:
        delayed = source[source["status"].astype(str).str.upper().eq("DELAYED")].copy()
    else:
        delayed = source.iloc[0:0].copy()
    records_returned = len(delayed)
    findings.append({{"message": f"{{records_returned}} delayed orders found."}})
    for _, row in delayed.iterrows():
        detail_rows.append(row.to_dict())
        evidence.append({{"record_id": row.get("order_id"), "status": row.get("status"), "due_date": row.get("due_date")}})
elif INTENT == "inventory_reorder_analysis":
    source = inventory.copy()
    records_analysed = len(source)
    low = source[source["available_quantity"] <= source["reorder_level"]].copy()
    records_returned = len(low)
    findings.append({{"message": f"{{records_returned}} materials are at or below reorder level."}})
    for _, row in low.iterrows():
        detail_rows.append(row.to_dict())
        evidence.append({{"record_id": row.get("material_id"), "available_quantity": row.get("available_quantity"), "reorder_level": row.get("reorder_level")}})
elif INTENT == "idle_machine_lookup":
    source = machines.copy()
    records_analysed = len(source)
    idle = source[source["status"].astype(str).str.upper().eq("IDLE")].copy()
    records_returned = len(idle)
    findings.append({{"message": f"{{records_returned}} machines are currently idle."}})
    for _, row in idle.iterrows():
        detail_rows.append(row.to_dict())
        evidence.append({{"record_id": row.get("machine_id"), "machine_type": row.get("machine_type"), "status": row.get("status")}})
elif INTENT == "list_factory_orders":
    source = orders.copy()
    records_analysed = len(source)
    records_returned = len(source)
    findings.append({{"message": f"{{records_returned}} factory orders found."}})
    for _, row in source.iterrows():
        item = row.to_dict()
        quantity = float(item.get("order_quantity", 0) or 0)
        completed = float(item.get("completed_quantity", 0) or 0)
        item["remaining_units"] = quantity - completed
        item["progress_percent"] = round((completed / quantity) * 100, 1) if quantity else 0
        detail_rows.append(item)
        evidence.append({{"record_id": item.get("order_id"), "status": item.get("status"), "remaining_units": item["remaining_units"], "due_date": item.get("due_date")}})
elif INTENT in ["order_risk_analysis", "detect_order_bottlenecks"]:
    source = orders.copy()
    records_analysed = len(source)
    incomplete = source[~source["status"].astype(str).str.upper().isin(["COMPLETE", "CANCELLED"])].copy()
    inv_map = {{row["material_id"]: row for _, row in inventory.iterrows()}} if not inventory.empty else {{}}
    machine_types = set(machines[machines["status"].astype(str).str.upper().isin(["IDLE", "RUNNING"])]["machine_type"]) if not machines.empty else set()
    for _, row in incomplete.iterrows():
        reasons = []
        usable_inventory = None
        material_id = row.get("required_material_id")
        required_qty = row.get("required_material_quantity", 0)
        if material_id in inv_map:
            inv = inv_map[material_id]
            usable_inventory = float(inv.get("available_quantity", 0)) - float(inv.get("reserved_quantity", 0))
            if usable_inventory < float(required_qty):
                reasons.append("inventory shortage")
        else:
            reasons.append("missing material relationship")
        if row.get("required_machine_type") not in machine_types:
            reasons.append("machine availability")
        if str(row.get("status", "")).upper() == "DELAYED":
            reasons.append("already delayed")
        if reasons:
            item = row.to_dict()
            item["risk_reasons"] = "; ".join(reasons)
            item["usable_inventory"] = usable_inventory
            detail_rows.append(item)
            evidence.append({{"record_id": row.get("order_id"), "main_bottleneck": reasons[0], "risk_reasons": item["risk_reasons"], "required_material": material_id, "usable_inventory": usable_inventory, "due_date": row.get("due_date")}})
    records_returned = len(detail_rows)
    findings.append({{"message": f"{{records_returned}} incomplete orders have identified production bottlenecks."}})
else:
    warnings.append("No approved analysis branch exists for this intent.")
    limitations.append("The sandbox did not substitute an unrelated order query.")

detail = pd.DataFrame(detail_rows)
if GENERATE_CSV and not detail.empty:
    csv_path = f"/sandbox/output/{{INTENT}}.csv"
    detail.to_csv(csv_path, index=False)
    generated_files.append(csv_path)

if GENERATE_XLSX and not detail.empty:
    xlsx_path = f"/sandbox/output/{{INTENT}}.xlsx"
    detail.to_excel(xlsx_path, index=False)
    generated_files.append(xlsx_path)

if GENERATE_JSON:
    json_path = f"/sandbox/output/{{INTENT}}_details.json"
    detail.to_json(json_path, orient="records", indent=2)
    generated_files.append(json_path)

if GENERATE_CHARTS and not detail.empty:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    chart_dir = "/sandbox/output/charts"
    from pathlib import Path
    Path(chart_dir).mkdir(parents=True, exist_ok=True)
    fig_path = f"{{chart_dir}}/{{INTENT}}_counts.png"
    detail.iloc[:, 0].astype(str).value_counts().head(10).plot(kind="bar")
    plt.tight_layout()
    plt.savefig(fig_path)
    generated_files.append(fig_path)

if GENERATE_PDF:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet
    pdf_path = f"/sandbox/output/{{INTENT}}_report.pdf"
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(pdf_path, pagesize=letter)
    story = [Paragraph("Industrial Data Agent Report", styles["Title"]), Paragraph(f"Request ID: {{REQUEST_ID}}", styles["Normal"]), Spacer(1, 12)]
    story.append(Paragraph(findings[0]["message"] if findings else "No findings.", styles["Heading2"]))
    if not detail.empty:
        table_data = [list(detail.columns[:6])] + detail.astype(str).iloc[:40, :6].values.tolist()
        table = Table(table_data, repeatRows=1)
        table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey)]))
        story.append(table)
    else:
        story.append(Paragraph("No detail rows returned.", styles["Normal"]))
    doc.build(story)
    generated_files.append(pdf_path)

result = {{
    "status": "success",
    "summary": {{"records_analysed": records_analysed, "records_returned": records_returned}},
    "findings": findings,
    "evidence": evidence,
    "warnings": warnings,
    "limitations": limitations,
    "generated_files": generated_files,
}}
with open("/sandbox/output/result.json", "w", encoding="utf-8") as handle:
    json.dump(result, handle, indent=2, default=str)
'''
