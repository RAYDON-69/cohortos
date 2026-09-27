"""
Copilot function-calling layer (Hermes-style structured JSON tool calls).

Format (OpenAI/Hermes compatible):
  tools: [{ "type": "function", "function": { "name", "description", "parameters" } }]
  tool_calls: [{ "type": "function", "function": { "name", "arguments": "<json string or object>" } }]

Tools:
  - create_automation_rule (write)
  - set_automation_enabled (write)
  - count_students_in_batch (read)
  - list_batches (read)

Ambiguous phrasing: optional local GGUF (LFM2.5 / Qwen via local_model) emits tool_calls JSON.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple


TOOL_SPECS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "create_automation_rule",
            "description": "Create a centre automation rule (trigger/action) via the rules engine.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "trigger_type": {
                        "type": "string",
                        "enum": [
                            "manual",
                            "schedule.daily",
                            "schedule.weekly",
                            "event.fee_overdue",
                            "event.attendance_marked",
                        ],
                    },
                    "action_type": {
                        "type": "string",
                        "enum": [
                            "fee_reminder",
                            "fee_reminder_escalation",
                            "notify_owner",
                            "notify_guardian",
                            "log_only",
                        ],
                    },
                    "enabled": {"type": "boolean"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_automation_enabled",
            "description": "Enable or disable an existing automation rule by id or name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "rule_id": {"type": "string"},
                    "rule_name": {"type": "string"},
                    "enabled": {"type": "boolean"},
                },
                "required": ["enabled"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "count_students_in_batch",
            "description": "Return how many students are in a batch (by batch name or id).",
            "parameters": {
                "type": "object",
                "properties": {
                    "batch_name": {"type": "string", "description": "Batch name substring match"},
                    "batch_id": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_batches",
            "description": "List batches in this centre with optional student counts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_counts": {"type": "boolean"},
                },
            },
        },
    },
]


def tools_for_prompt() -> str:
    return json.dumps(TOOL_SPECS, indent=2)


def parse_tool_calls(text: str) -> List[Dict[str, Any]]:
    if not text:
        return []
    candidates: List[str] = [text]
    for m in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", text):
        candidates.append(m.group(1))
    for m in re.finditer(r"\{[\s\S]*\"tool_calls\"[\s\S]*\}", text):
        candidates.append(m.group(0))
    for c in candidates:
        c = c.strip()
        try:
            data = json.loads(c)
        except Exception:
            continue
        if isinstance(data, dict) and isinstance(data.get("tool_calls"), list):
            return list(data["tool_calls"])
        if isinstance(data, list) and data and isinstance(data[0], dict):
            if data[0].get("type") == "function" or "function" in data[0]:
                return list(data)
    return []


def intent_to_tool_calls(question: str) -> List[Dict[str, Any]]:
    q = (question or "").lower()
    # write: create automation
    if any(
        k in q
        for k in (
            "create automation",
            "add automation",
            "new automation",
            "make a rule",
            "create a rule",
            "automation rule",
            "fee reminder rule",
        )
    ):
        name = "Fee overdue reminder"
        m = re.search(r"named?\s+[\"']([^\"']+)[\"']", question or "", re.I)
        if m:
            name = m.group(1).strip()
        action = "fee_reminder" if "fee" in q else "log_only"
        return [
            {
                "type": "function",
                "function": {
                    "name": "create_automation_rule",
                    "arguments": {
                        "name": name,
                        "trigger_type": "manual",
                        "action_type": action,
                        "enabled": True,
                    },
                },
            }
        ]
    # write: enable/disable
    if "disable automation" in q or "enable automation" in q:
        enabled = "disable" not in q
        m = re.search(r"(?:automation|rule)\s+[\"']([^\"']+)[\"']", question or "", re.I)
        return [
            {
                "type": "function",
                "function": {
                    "name": "set_automation_enabled",
                    "arguments": {
                        "rule_name": m.group(1) if m else "",
                        "enabled": enabled,
                    },
                },
            }
        ]
    # read: student count in batch
    if re.search(r"how many students.*(batch|class|section)", q) or (
        "students" in q and ("batch" in q or "class" in q)
    ):
        m = re.search(r"batch\s+[\"']?([A-Za-z0-9_\- ]+)", question or "", re.I)
        return [
            {
                "type": "function",
                "function": {
                    "name": "count_students_in_batch",
                    "arguments": {"batch_name": (m.group(1).strip() if m else "")},
                },
            }
        ]
    # read: list batches
    if "list batches" in q or "which batches" in q or "what batches" in q:
        return [
            {
                "type": "function",
                "function": {
                    "name": "list_batches",
                    "arguments": {"include_counts": True},
                },
            }
        ]
    return []


def _parse_args(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return {"_raw": raw}
    return {}


def execute_tool_calls(
    tool_calls: List[Dict[str, Any]],
    *,
    automation_service=None,
    admission_service=None,
    batch_service=None,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for tc in tool_calls or []:
        fn = tc.get("function") if isinstance(tc, dict) else None
        if not isinstance(fn, dict):
            results.append({"ok": False, "error": "invalid_tool_call_shape"})
            continue
        name = str(fn.get("name") or "")
        args = _parse_args(fn.get("arguments"))
        try:
            if name == "create_automation_rule":
                if automation_service is None:
                    results.append({"name": name, "ok": False, "error": "automation_service_unavailable"})
                    continue
                body = {
                    "name": str(args.get("name") or "Copilot rule").strip(),
                    "enabled": bool(args.get("enabled", True)),
                    "trigger": {"type": str(args.get("trigger_type") or "manual")},
                    "conditions": [],
                    "actions": [{"type": str(args.get("action_type") or "log_only"), "params": {}}],
                }
                rule = automation_service.upsert_rule(body)
                results.append({"name": name, "ok": True, "result": {"rule": rule}})
            elif name == "set_automation_enabled":
                if automation_service is None:
                    results.append({"name": name, "ok": False, "error": "automation_service_unavailable"})
                    continue
                rid = str(args.get("rule_id") or "")
                rname = str(args.get("rule_name") or "").strip().lower()
                enabled = bool(args.get("enabled", True))
                if not rid and rname and hasattr(automation_service, "list_rules"):
                    for r in automation_service.list_rules() or []:
                        if rname in str(r.get("name") or "").lower():
                            rid = str(r.get("id") or "")
                            break
                if not rid:
                    results.append({"name": name, "ok": False, "error": "rule_not_found"})
                    continue
                r = automation_service.set_enabled(rid, enabled)
                results.append({"name": name, "ok": True, "result": {"rule": r}})
            elif name == "count_students_in_batch":
                batches = []
                if batch_service and hasattr(batch_service, "list_batches"):
                    batches = list(batch_service.list_batches() or [])
                bid = str(args.get("batch_id") or "")
                bname = str(args.get("batch_name") or "").strip().lower()
                matched = None
                for b in batches:
                    if bid and str(b.get("id")) == bid:
                        matched = b
                        break
                    if bname and bname in str(b.get("name") or "").lower():
                        matched = b
                        break
                if not matched and batches and not bname and not bid:
                    matched = batches[0]
                if not matched:
                    results.append({"name": name, "ok": True, "result": {"count": 0, "batch": None}})
                    continue
                mbid = str(matched.get("id") or "")
                count = 0
                if admission_service and hasattr(admission_service, "list_students"):
                    students = list(admission_service.list_students(active_only=False) or [])
                    for s in students:
                        sb = str(s.get("batch_id") or s.get("batch") or "")
                        if sb == mbid or (bname and bname in str(s.get("batch_name") or "").lower()):
                            count += 1
                results.append(
                    {
                        "name": name,
                        "ok": True,
                        "result": {
                            "count": count,
                            "batch_id": mbid,
                            "batch_name": matched.get("name"),
                        },
                    }
                )
            elif name == "list_batches":
                batches = []
                if batch_service and hasattr(batch_service, "list_batches"):
                    batches = list(batch_service.list_batches() or [])
                out = [{"id": b.get("id"), "name": b.get("name")} for b in batches]
                results.append({"name": name, "ok": True, "result": {"batches": out}})
            else:
                results.append({"name": name, "ok": False, "error": f"unknown_tool:{name}"})
        except Exception as e:
            results.append({"name": name, "ok": False, "error": str(e)})
    return results


def _local_tool_dispatch(question: str) -> List[Dict[str, Any]]:
    """Use local GGUF to emit tool_calls when intent is ambiguous."""
    try:
        from services.local_model import local_available, local_complete
        if not local_available():
            return []
        system = (
            "You are a tool router. Reply ONLY with JSON of the form "
            '{"tool_calls":[{"type":"function","function":{"name":"...","arguments":{...}}}]} '
            "using one of these tools:\n" + tools_for_prompt() + "\n"
            "If no tool applies, reply {\"tool_calls\":[]}."
        )
        text = local_complete(question, system=system, max_tokens=256, temperature=0.0)
        return parse_tool_calls(text)
    except Exception:
        return []


def run_copilot_tools(
    question: str,
    *,
    automation_service=None,
    admission_service=None,
    batch_service=None,
    llm_tool_text: Optional[str] = None,
    use_local_for_ambiguous: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    calls = parse_tool_calls(llm_tool_text or "")
    if not calls:
        calls = intent_to_tool_calls(question)
    if not calls and use_local_for_ambiguous:
        calls = _local_tool_dispatch(question)
    if not calls:
        return [], []
    results = execute_tool_calls(
        calls,
        automation_service=automation_service,
        admission_service=admission_service,
        batch_service=batch_service,
    )
    return calls, results
