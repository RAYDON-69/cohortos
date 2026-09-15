# CohortOS v1.2 — Frontend ↔ Backend Audit

## TL;DR
The frontend was **not talking to the backend correctly**, and in fact could not
even build. Root cause: `frontend/src/api/client.ts` and `api/main.py` were
written against two different, drifted versions of the API contract (the
frontend targets a much larger surface — "Portions 12–23" per its comments —
than `api/main.py`, which is a slimmer v1.2 route layer). Most of the missing
logic already exists in `services/*.py`; it just was never wired into a route.

## Fixed in this pass (verified: `tsc --noEmit` clean, `python -m py_compile` clean)

1. **Build-breaking syntax error in `client.ts`** — `loadTokens()` contained a
   leftover dead code fragment from an older version (duplicate `return`
   after the function's closing `}`, referencing `STORAGE_KEYS.access` /
   `.refresh`, which don't even exist in the current `STORAGE_KEYS` object).
   This is a hard `TS1128` syntax error — **the entire frontend failed to
   compile**, so nothing else in this audit mattered until it was removed.
2. **Founder-admin calls hit the wrong origin.** `founderRequest()` read its
   base URL from `localStorage.getItem("cohortos_api_base")`, a key nothing
   in the app ever sets. Every founder dashboard/provisioning call was
   silently going to a relative path on the frontend's own origin instead of
   the API server. Now uses `getApiBaseUrl()`, the same base every other
   call uses.
3. **`/accounts/link-join` couldn't be used the way the frontend calls it.**
   Backend required `admission_id` + `cohortos_account_id` up front; the
   frontend's `linkByJoinCode()` only ever sends `account_id` + `join_code`
   (the whole point of a join code is the student *doesn't* know their
   internal admission id). Route now resolves `admission_id` by looking up
   the join code server-side, matching the SPEC's Module 8 join-code flow,
   and returns student name/roll for the confirmation screen.
4. **Founder dashboard returned the wrong shape entirely.** The route
   hand-rolled `{tenants, summary:{total}}`; `FounderAdminService.dashboard()`
   already builds the exact `{tenant_count, active, suspended, trial, tenants}`
   shape the frontend types expect — the route just wasn't calling it.
5. **Founder tenant lifecycle actions were 404s.** `founderGetTenant`,
   `founderSuspend`, `founderExtend`, `founderActivate`,
   `founderUpdateStudentCount`, `founderAudit`, and the `status` filter on
   `founderListTenants` all had no matching route, despite the service
   methods (`suspend_tenant`, `extend_tenant`, `activate_tenant`,
   `update_student_count`, `list_audit`) already existing and tested.
6. **Attendance review resolution was a 404.** `resolveAttendanceReview()`
   called `POST /attendance/reviews/{flagId}/resolve`, which didn't exist;
   `AttendanceService.resolve_review()` already implements it. Also wired the
   `limit` query param on `GET /attendance/reviews`.
7. **Path aliases for the two `[BULLET]` (non-negotiable, must-work-offline)
   flows** — attendance and payments — added so the frontend's actual URLs
   resolve: `GET /attendance/batch/{batch_id}?on_date=`,
   `GET /payments/batch/{batch_id}?year=&month=`,
   `GET /payments/delayed/{batch_id}?year=&month=`. All three are thin
   wrappers over existing, already-tested service methods.

## Still broken — needs backend routes (not fixed in this pass)

These are frontend calls with **no matching backend route at all**. Grouped
by whether the underlying service logic already exists (cheap to wire up) or
genuinely needs new backend work.

**Service logic already exists — just needs a route** (check the named
service method before writing new logic):
- `POST /students/{id}/migrate` → `AdmissionService.migrate_student_roll_batch`
- `GET/PATCH /batches/{id}`, `POST /batches/{id}/extra-sessions` → `AdmissionService.update_batch`, `.add_extra_session`, `.get_batch`
- `POST /exams`, `POST /exams/{id}/results`, `GET /exams/{id}/results`,
  `GET /students/{id}/results`, `POST /exams/{id}/complete`,
  `GET /analytics/heatmap`, `GET /analytics/struggle` → all present on `ExamService` (`create_exam`, `enter_result`, `get_exam_results`, `get_student_results`, `complete_exam`, `topic_heatmap`, `students_likely_to_struggle`)
- `POST /vault`, `PUT /vault/{id}/access-rules`, `POST /vault/{id}/relax`,
  `POST /vault/{id}/restore`, `GET /vault/student`, `GET /vault/{id}/access`
  → `ContentService.create_resource`, `.set_access_rules`, `.relax_protection`,
  `.restore_protection`, `.evaluate_access`
- `POST /accounts`, `GET /accounts/{id}/home` → `AccountService.create_account`, `.student_view`
- `GET/PUT /ai/style-profiles/{subject}` → `AITeachService.get_style_profile`, `.upsert_style_profile`
- `GET /ai/review-queue`, `.../approve`, `.../reject` → `AITeachService.list_review_queue`, `.approve_item`, `.reject_item`
- `GET /ai/item-bank`, `.../history`, `.../push-bank` → present on `AITeachService` (`student_visible_items`, `push_to_exam_bank`) — history endpoint needs checking against item versioning
- `GET/POST /solve/threads*` → `AISolveService.list_threads`, `.list_messages`, `AccountService.teacher_reply_on_thread`
- `GET/PUT /parents/{id}*` (portal, summary, notifications, preferences) →
  `AccountService.parent_view` covers part of this; notification
  preferences live in `NotificationService.set_user_preference` /
  `.get_user_preference` — needs a small aggregation route
- `POST /ai/threads/{id}/take-over`, `GET /ai/threads/{id}/messages` → `AccountService.teacher_reply_on_thread`, `AISolveService.list_messages`

**Needs a decision before implementing** (schema/design ambiguity, not just
wiring):
- `api/main.py`'s `staff` route currently stores a flat ad-hoc row
  (`{id, name, role, phone, email}`), while the frontend expects a proper
  `role_id`/`role_name` RBAC model backed by `DataService.create_role` /
  `create_permission`. These are two different staff models — reconcile
  before wiring `assignStaffRole` (`POST /staff/{id}/role`).
- Vault `access_rules` shape (`{operator, rules: [{kind, value}]}`) needs to
  be checked against `ContentService.set_access_rules`'s actual rule schema
  before exposing it directly to the client.

## Recommendation
Fix the "already exists — just needs a route" group next; it's the bulk of
the remaining gap and low-risk since the business logic is already tested
(239/239 per README). The two "needs a decision" items should get a quick
spec note in `SPEC.md` first, per `CLAUDE.md`'s source-of-truth rule, before
wiring — guessing the contract for RBAC/staff or Vault access rules risks
building the wrong shape twice.
