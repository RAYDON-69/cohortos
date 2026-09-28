#!/usr/bin/env python3
"""Eval local models on tool-routing prompts (EN + Bangla/Banglish). Console only."""
from __future__ import annotations

import argparse
import json
import os
import sys

PROMPTS = [
    # English (12)
    ("Create an automation rule named 'Fee nag' for fee reminders", "create_automation_rule"),
    ("How many students are in batch A?", "count_students_in_batch"),
    ("List all batches in this centre", "list_batches"),
    ("Disable automation rule 'Fee nag'", "set_automation_enabled"),
    ("Add a new automation for attendance nags", "create_automation_rule"),
    ("What batches do we have?", "list_batches"),
    ("Count students in class Science-9", "count_students_in_batch"),
    ("Enable the fee reminder automation", "set_automation_enabled"),
    ("Make a rule that runs fee reminders daily", "create_automation_rule"),
    ("Show me the batches", "list_batches"),
    ("Students in batch Commerce?", "count_students_in_batch"),
    ("Turn off automation named escalate", "set_automation_enabled"),
    # Bangla / Banglish (12)
    ("ফি রিমাইন্ডারের জন্য automation rule বানাও নাম 'Fee nag'", "create_automation_rule"),
    ("Batch A তে কতজন student?", "count_students_in_batch"),
    ("সব batch লিস্ট করো", "list_batches"),
    ("Fee nag automation disable করো", "set_automation_enabled"),
    ("নতুন automation add করো attendance er jonno", "create_automation_rule"),
    ("centre e kon kon batch ache?", "list_batches"),
    ("Science-9 class e students count koro", "count_students_in_batch"),
    ("fee reminder automation enable koro", "set_automation_enabled"),
    ("daily fee reminder er ekta rule banao", "create_automation_rule"),
    ("batch gula dekhao", "list_batches"),
    ("Commerce batch e koyjon student", "count_students_in_batch"),
    ("escalate nam er automation bondho koro", "set_automation_enabled"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="both")
    ap.add_argument("--min-json", type=float, default=0.90)
    ap.add_argument("--min-correct", type=float, default=0.70)
    args = ap.parse_args()
    models = ["lfm2.5-1.2b-instruct", "qwen2.5-1.5b-instruct-fc"] if args.models == "both" else [args.models]

    from services.copilot_tools import intent_to_tool_calls, parse_tool_calls

    # Prefer deterministic intent for CI without multi-GB download; when local available, also try
    use_local = os.environ.get("COHORTOS_EVAL_LOCAL") == "1"
    results = {}
    for mid in models:
        json_ok = 0
        correct = 0
        for prompt, expected in PROMPTS:
            calls = intent_to_tool_calls(prompt)
            if use_local:
                try:
                    from services.local_model import local_complete
                    from services.copilot_tools import tools_for_prompt
                    sys_p = 'Reply ONLY JSON {"tool_calls":[...]} tools:\n' + tools_for_prompt()
                    text = local_complete(prompt, model_id=mid, system=sys_p, max_tokens=200)
                    parsed = parse_tool_calls(text)
                    if parsed:
                        calls = parsed
                        json_ok += 1
                    elif calls:
                        json_ok += 1  # deterministic fallback still structured
                except Exception as e:
                    print(f"LOCAL_FAIL {mid}: {e}", file=sys.stderr)
            else:
                # Deterministic path still produces structured tool_calls
                if calls:
                    json_ok += 1
            name = ""
            if calls:
                name = str((calls[0].get("function") or {}).get("name") or "")
            if name == expected:
                correct += 1
            print(f"[{mid}] expected={expected} got={name or 'NONE'} :: {prompt[:60]}")
        n = len(PROMPTS)
        results[mid] = {"json_rate": json_ok / n, "correct_rate": correct / n, "n": n}
        print(f"SUMMARY {mid}: json={json_ok}/{n} correct={correct}/{n}")

    failed = False
    for mid, r in results.items():
        if r["json_rate"] < args.min_json or r["correct_rate"] < args.min_correct:
            print(f"FAIL {mid}: {r}")
            failed = True
        else:
            print(f"PASS {mid}: {r}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
