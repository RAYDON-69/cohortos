"""
Copilot function-calling layer (Hermes-style structured JSON tool calls).

Format (OpenAI/Hermes compatible):
  tools: [{ "type": "function", "function": { "name", "description", "parameters" } }]
  tool_calls: [{ "type": "function", "function": { "name", "arguments": "<json string or object>" } }]

Proof tool: create_automation_rule → AutomationService.upsert_rule
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional, Tuple


TOOL_SPECS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "create_automation_rule",
            "description": (
                "Create or update a centre automation rule (trigger/condition/action) "
                "via the existing automations rules engine."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Human-readable rule name",
                    },
                    "trigger_type": {
                        "type": "string",
                        "enum": [
                            "manual",
                            "schedule.daily",
                            "schedule.weekly",
                            "event.fee_overdue",
                            "event.attendance_marked",
                        ],
                        "description": "When the rule fires",
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
                        "description": "Action to run",
                    },
                    "enabled": {
                        "type": "boolean",
                        "description": "Whether the rule is enabled after create",
                    },
                },
                "required": ["name"],
            },
        },
    }
]


def tools_for_prompt() -> str:
    return json.dumps(TOOL_SPECS, indent=2)


def parse_tool_calls(text: str) -> List[Dict[str, Any]]:
    """
    Extract Hermes/OpenAI-style tool_calls from model output.
    Accepts: full JSON object, fenced ```json blocks, or a bare tool_calls array.
    """
    if not text:
        return []
    candidates: List[str] = [text]
    for m in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", text):
        candidates.append(m.group(1))
    # Find {...} containing tool_calls
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
    """
    Deterministic tool selection when no LLM is configured.
    Maps natural language to structured tool_calls (not free text).
    """
    q = (question or "").lower()
    wants_auto = any(
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
    )
    if not wants_auto:
        return []
    name = "Fee overdue reminder"
    m = re.search(r"named?\s+[\"']([^\"']+)[\"']", question or "", re.I)
    if m:
        name = m.group(1).strip()
    elif "fee" in q:
        name = "Fee overdue reminder"
    action = "fee_reminder" if "fee" in q else "log_only"
    args = {
        "name": name,
        "trigger_type": "manual",
        "action_type": action,
        "enabled": True,
    }
    return [
        {
            "type": "function",
            "function": {
                "name": "create_automation_rule",
                "arguments": args,
            },
        }
    ]


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
) -> List[Dict[str, Any]]:
    """Execute structured tool_calls; returns list of {name, ok, result/error}."""
    results: List[Dict[str, Any]] = []
    for tc in tool_calls or []:
        fn = tc.get("function") if isinstance(tc, dict) else None
        if not isinstance(fn, dict):
            results.append({"ok": False, "error": "invalid_tool_call_shape"})
            continue
        name = str(fn.get("name") or "")
        args = _parse_args(fn.get("arguments"))
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
            try:
                rule = automation_service.upsert_rule(body)
                results.append({"name": name, "ok": True, "result": {"rule": rule}})
            except Exception as e:
                results.append({"name": name, "ok": False, "error": str(e)})
        else:
            results.append({"name": name, "ok": False, "error": f"unknown_tool:{name}"})
    return results


def run_copilot_tools(
    question: str,
    *,
    automation_service=None,
    llm_tool_text: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Returns (tool_calls, execution_results).
    Prefer LLM-emitted tool_calls when parseable; else intent_to_tool_calls.
    """
    calls = parse_tool_calls(llm_tool_text or "")
    if not calls:
        calls = intent_to_tool_calls(question)
    if not calls:
        return [], []
    results = execute_tool_calls(calls, automation_service=automation_service)
    return calls, results
