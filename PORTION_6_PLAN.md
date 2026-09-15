# Portion 6 — Content (CohortOS Vault) — SPEC Module 5

## Acceptance criteria

1. **Resource types [FLEX]**  
   PDF, sheet, video (youtube / mp4), image, live_recording, link.  
   Manual entry is the primary workflow. Per-topic/chapter linkage.

2. **Access rules engine [BULLET]**  
   Per-resource conditions, composable AND/OR, optionally per-batch:  
   - min_attendance_pct (this month)  
   - sat_last_exam  
   - paid_up (current month)  
   - expires_on (date)  
   - always_allow / always_deny  
   Evaluation uses AttendanceService / PaymentService / ExamService when injected.

3. **Anti-leak [BULLET] [LOCKED]**  
   - Centre default: owner_only protection.  
   - Fields: watermark, no_download, session_token_required.  
   - Teacher/assistant may relax protection on any resource → audit-logged,  
     resource labeled `protection_relaxed`.  
   - Desk role cannot change anti-leak settings (enforced at service layer via role check).

4. **Big-file support**  
   Chunk metadata + resumable download state (chunk index, total chunks, checksum).  
   No hard size limit in model.

5. **Offline cache [BULLET]**  
   Students can mark resources for offline; access rules re-evaluated on reconnect  
   via `evaluate_access(..., force_recheck=True)`.

6. **Online coaching mode [NEW]** — minimal viable  
   LiveSession model: batch, start/end, status, hand_raise list, poll payloads.  
   Chat messages stored as resource-linked notes (full realtime is out of scope for this portion).

7. **AI video-suggest [FLEX]**  
   Stub only — `suggest_videos(topic)` returns empty list; documented as optional/low-priority.

8. **Cross-cutting**  
   Offline-first core writes, tenant-scoped, audit-logged, sync-ready, timezone-aware.

## Files
- models/content.py
- services/content_service.py
- migrations/009_content.sql
- tests/test_content.py
- PORTION_6_PLAN.md / PORTION_6_SUMMARY.md

## Verify
```bash
python -m pytest tests/test_content.py -v
python -m pytest tests/ -q
```
