# SPEC.md — CohortOS: AI-Powered Coaching Operating System (v2.2)
> **This file is the single source of truth.** The agent must re-read this file at the start of
each session. Nothing here should be re-explained by the user; if something is genuinely
missing, the agent must ask, then append the answer back under the relevant section.
>
> **Upgrade markers:** Lines tagged `[FLEX]` are now more flexible than v1; `[BULLET]` are
more bulletproof; `[NEW]` are net-new capabilities; `[LOCKED]` marks a decision finalized
after discussion (v2.1). Offline-first remains the default; cloud/hybrid is an optional
per-centre mode.

## 0. Project Facts
- **Product:** CohortOS — productizable, multi-tenant SaaS for coaching centres
(200–6000 students) in Bangladesh, India, and globally.
- **Origin client:** Swapan Kumar Saha, physics coaching teacher, Barishal (teaching since
2008), author of "Swapan's Physics." ~400 students, ~10 batches. Remains the design
anchor.
- **Platform:** Desktop app **and** responsive web/mobile/desktop for student/parent faces.
`[FLEX]` The desktop app is the offline-first front desk with fully switchable cloud first option ;
the web app is the cloud-first option for centres that prefer it.
- **Mode toggle `[FLEX]`:** Each centre chooses at onboarding:
- **Offline-first (default):** local SQLite, syncs to cloud when online.
- **Cloud-first:** hosted DB, local cache for offline resilience.
- **Hybrid:** desktop for desk staff + web/mobile/desktop for teachers/students/parents.
- **Environment constraints:** Internet is available but unreliable (frequent power cuts). **All
core features (attendance, payment, exams, records, content access) must work with zero
internet.(default)** Only messaging, AI, and cloud sync require internet and must
queue/degrade gracefully.
- **Users `[FLEX]`:** Multi-staff with RBAC (owner, desk, teacher, assistant)with owner being
admin — replaces v1's single-teacher login. Students and parents have optional accounts
(see Module 8). A centre may still run in single-user mode.
- **Pricing `[NEW]`:** Tiered monthly SaaS by student count — Starter ৳5k (≤500), Growth
৳10–15k (≤1500), Scale custom (≤6000), with per-student overage. Annual discount
available.
- **AI default `[NEW]`:** Free-tier Google Gemini (Google AI Studio key the centre already
owns) is the default. Paid keys / Cloud projects are optional upgrades. See Module 9.

## 1. Module: Admission
**Form fields:** Name, Batch (select from configured slots), Roll (auto-generated, editable),
student phone, parent phone(s), WhatsApp number, cohortos id (optional). **No Facebook
ID or college name field.** `[FLEX]` Centres may add custom fields (e.g., school, college,
guardian occupation, custom field named by user) or delete any fielid via Settings.

**Batch configuration `[FLEX]`:**
- Days: any combination of Sat–Fri.
- Time: 24-hour format (bulletproof against am/pm ambiguity).
- Batch display name: auto-generated (e.g. "Sat,Mon,Wed 14:00") or manual override.
- **Batch templates `[NEW]`:** Per coaching type (medical prep, HSC, English, skill) —
pre-set days, times, exam structures, messaging templates, and AI system prompts (for
editing system prompts they will first request the cohortos team (cause the system
prompts are not be seen to be seen and leaked without request)). Templates are editable
and exportable.

**Roll number encoding `[FLEX]` `[LOCKED]`:**
- Default scheme: `[DaySet][TimeCode][Serial]`. DaySet is a **3-digit bitmask** (Sat=1,
Sun=2, Mon=4, Tue=8, Wed=16, Thu=32, Fri=64 — sum the selected days, zero-padded
001–127), fixed-width regardless of how many days are selected. TimeCode is a 2-digit
24-hour hour. Serial is 3 digits. Example: Sat+Mon+Wed = 1+4+16 = `021`, 14:00 = `14`,
serial 33 = `033` → roll = **`02114033`**.
- **Centres may switch to a plain serial scheme** or define their own encoding in Settings.
The default scheme remains available for backward compatibility with the origin client.

**Roll/batch changes `[BULLET]`:** If a student's batch or roll changes, generate the new roll
and **migrate full history** (attendance, payments, results, threads) to the new roll/account
— never lose history. Migration is atomic (transactional) and logged.

**Duplicate detection `[BULLET]`:** Before saving, check for likely duplicates (same name +
same phone, or same phone across records). If a match is found, **show the error and the
specific reason first** (e.g. "Phone number already registered to student X, roll Y") before
allowing the teacher to proceed or cancel. Duplicate resolution is idempotent.

**Editing `[BULLET]`:** Only authorised staff can edit student records. Every other field is
editable. All edits are audit-logged.

## 2. Module: Attendance / Irregularity
**Hardware `[BULLET]`:** ZKTeco K60 and ZKTeco series as default option (or compatible
to any biometric device) over local network (static IP). Use `pyzk` to pull punches — avoids
proprietary `zkemkeeper.dll`. Falls back to manual entry if the device is offline. Device linking
is manual (teacher enters the device's internal user ID per student). for flexiblity , also add a
bulletproof manual attendance taking system like the google sheets.

**Late rule `[FLEX]`:** Configurable threshold, default **12 minutes** after batch start.
**Per-batch override** allowed (not only global). Past threshold → "Late" (not absent).

**Absent rule `[BULLET]`:** If a student does not punch in on any batch day within their
assigned batch, mark absent (visually distinct, e.g. red dot). Anti-proxy: if the same device
logs two punches within an implausible window, flag for review.

**Cross-batch attendance `[BULLET]`:** If a student attends a *different* batch time slot **on
their own batch's day**, count it as present for that day (not absent). Cross-batch validation
is explicit and logged.

**Biometric/manual precedence `[BULLET]` `[LOCKED]`:** Biometric punches are
authoritative when present. Manual entry only fills gaps (device offline, or no device at all)
— it never silently overwrites an existing biometric record. Evaluation order: collect all
punches (biometric + manual) for the student that day → run the anti-proxy plausibility
check across all of them → determine own-batch/cross-batch credit from whichever punches
survive that check. Cross-batch credit is not an exemption from anti-proxy — it's simply a
different valid session a punch can originate from. If biometric and manual entries disagree
on a student's final status for the day, don't auto-resolve either way — route it to the same
review queue anti-proxy flags already use.

**Extra classes `[FLEX]`:** In batch settings, the teacher can add an extra day/time with an
expiry date — active as a genuine class session until that date, then automatically stops
applying.

**Teacher's daily view `[BULLET]`:** Attendance tab → select batch → see prior day's
absentees list (expandable to more days back) so the teacher can rebuke them directly,
independent of automated messaging.

**Automated messaging for absentees `[FLEX]`:**
- Sent automatically at **one global fixed time** (default), **or per-batch time** if the centre
chooses.
- **Channel `[FLEX]`:** WhatsApp Business API, SMS gateway, in-app push, or mix —
per-centre choice with monthly cost caps. Swappable `NotificationService` (Module 6) so
switching providers never touches business logic.
- **Special exclusion rule `[FLEX]` `[LOCKED]`:** Uses the single **irregularity threshold**
(default: fewer than 3 days attended that month, per-batch editable — see Module 3, same
setting drives both modules). Below it, **stop sending automated absence messages** to
that student and **stop the automated payment nag** (Module 3) — both fold into one
consolidated **"notify the teacher directly"** alert covering attendance + payment status, so
the family isn't double-messaged and nothing is silently dropped.
- **Extra template:** distinct message for "late 3 days in a row", separate from
single-day-late and absence templates.
- All templates are teacher-editable text, stored persistently, reused until changed.

## 3. Module: Payment
**Tracking granularity `[FLEX]`:** Default = Paid / Unpaid status **per month only** (no
amount). **Optional amount + receipt mode** for centres that want it; the simple mode
remains default for the origin client.

**Locking mechanic `[BULLET]`:** Student → Payment section → row of months (filled dot =
paid, hollow = unpaid). Tapping a month then "Lock" marks it paid and **locks** that record
(prevents accidental edits). Manual teacher action — no auto-marking. Locked records are
immutable except by an explicit owner unlock with audit log.

**Delayed-payment messaging `[FLEX]`:**
- Trigger date configurable (day of month, previous vs. current month target).
- **Green/white box logic `[BULLET]`:** every unpaid student defaults to green (will receive
message); teacher can toggle to white (will NOT receive). White stays white — **no
auto-reset to green** — until the teacher manually flips it back.
- **Exclusion rule `[FLEX]` `[LOCKED]`:** Uses the same **irregularity threshold** as Module
2 (default: fewer than 3 days attended that month, per-batch editable) — one setting drives
both exclusions, not two independent numbers. Excluded students are covered by the
consolidated teacher alert defined in Module 2, not a separate automated payment message.
- **bKash/nagad deep-link `[NEW]`:** Payment reminders can include a deep-link or
copy-paste payment target.
- Optional: teacher can receive a summary message of all delayed-payment students each
cycle (Send / Don't Send choice).

## 4. Module: Exams / Results
**Per-chapter exam structure (the "main exam") `[FLEX]`:**
1. 15 MCQs (Medical/Varsity style) in 9 minutes — result given immediately, hand to hand.
2. 6 physics maths questions (BUET style), 60 marks, 18 minutes.
3. 1 CQ (HSC-style), 10 marks.
- Written-portion (2 & 3) results entered by the teacher within the next 2–3 classes.
- A separate "open book" exam also occurs per chapter but is marked low-priority/optional in
the record.
- **This structure is a template `[FLEX]`:** centres can define their own exam templates
(different MCQ counts, type of exam, durations, marks) per batch/subject.

**Input method `[BULLET]`:** Manual typing (no voice input required — confirmed by origin
client).

**Extra/custom exams `[FLEX]`:** Support ad hoc exams outside the standard structure
(custom name, date, score fields).

**History `[BULLET]`:** All exam results persist permanently, viewable over time, to reveal
patterns/weaknesses per topic. Never lost on roll/batch changes.

**Batch-level analytics `[NEW]`:** Per-topic weakness heatmaps, MCQ-vs-written gaps,
cohort comparison, and "students likely to struggle next exam" predictions from
attendance+result trends. Analytics are read-only views over the same data.

## 5. Module: Content (CohortOS Vault) `[NEW]`
- **Resource types:** PDFs, sheets, videos (YouTube links + timestamps + uploaded mp4),
images, live class recordings.
- **Per-topic library:** link a resource to a specific topic/chapter. Manual entry is the priority
workflow.
- **Access rules engine `[BULLET]`:** Per-resource conditions:
- "only students with ≥X% attendance this month"
- "only students who sat the last exam"
- "only paid-up students"
- "expires on date Y"
- Rules are composable (AND/OR) and per-batch.
- **Anti-leak `[BULLET]` `[LOCKED]`:** In-app viewer with watermarking, no-download flag,
per-user session tokens. Screen-share discouraged via session watermark. **Centre-wide
default policy is owner-only.** Any teacher or assistant can relax protection on a per-resource
basis (any resource, not just their own) — always audit-logged and the resource is visibly
labeled "protection relaxed" wherever it appears. Desk role has no access to anti-leak
controls.
- **Big-file support:** No Telegram-Premium-style limits; chunked upload + resumable
download.
- **Online coaching mode `[NEW]`:** Live class integration, chat, hand-raise, polls — for
centres that run online batches.
- **Offline cache `[BULLET]`:** Students can pre-download allowed resources for offline
study; access rules re-evaluate on reconnect.
- **Optional AI video-suggest `[FLEX]`:** Low-priority helper tab to suggest candidate
YouTube videos for a topic — explicitly optional, must not consume significant build time.

## 6. Module: Messaging Architecture (cross-cutting)
- **`NotificationService` abstraction `[BULLET]`:** Single internal service used by attendance
(Module 2), payment (Module 3), in-app threads (Module 8), and account login/recovery
(Module 8). Underlying provider (WhatsApp Business API, SMS gateway, in-app push, or a
low-volume transactional email sender) is swappable without touching business logic.
- **Channel choice `[FLEX]`:** Per-centre, per-message-type channel selection with monthly
cost caps.
- **Templates:** All editable in a Settings panel; persisted until changed.
- **Queue `[BULLET]`:** Outgoing messages **queue locally** and flush automatically when
connectivity returns — never silently drop a message. Queue is durable (survives restart).
- **Bangla/UTF-8 `[BULLET]`:** UTF-8 throughout, no encoding bugs. Bangla-friendly text
fields and templates.

## 7. Module: Cross-cutting / Non-functional
- **Bulletproof / offline-first `[BULLET]`:** Every core action (data entry, attendance capture,
payment locking, exam entry, content access) works without internet.
- **Mode toggle `[FLEX]`:** Offline-first default; cloud-first or hybrid optional per centre.
- **Sync engine `[BULLET]`:** Encrypted, last-write-wins per field, conflict log the owner can
review. Sync is idempotent and resumable.
- **Multi-staff RBAC `[FLEX]`:** Owner, desk, teacher, assistant roles with per-centre
permissions.
- **Data integrity `[BULLET]`:** History never lost on roll/batch changes; locked payment
records not silently editable; all mutations audit-logged.
- **Expandability `[BULLET]`:** Data model anticipates student/parent logins (Module 8) and
multi-tenancy (Module 10) without rebuild.
- **UI `[FLEX]`:** Simple for using but highly attractive design and flexible, low-friction for
non-technical desk staff; Bangla + English toggle; mobile as well as desktop responsive for
student/parent app as well as the owner.

## 8. Module: Student & Parent Accounts `[NEW]` `[LOCKED v2.1]`

**Join mechanism `[BULLET]` `[LOCKED]`:** Two entry points, one underlying operation —
`link(admission_id, cohortos_account_id)`, always staff-auditable, never silent.
- **Per-admission join code (primary):** generated automatically at admission (Module 1),
tied to that exact admission_id — not a centre-wide PIN. Delivered as a QR code (printed
on ID card/receipt, or shown on desk screen) plus a short alphanumeric fallback for manual
typing. Single-use, long expiry (default 90 days); staff can regenerate on demand, which
auto-invalidates the prior code. Scanning/entering the code *is* claiming that specific
admission record — no name/phone matching required, no ambiguity possible.
- **Manual staff-linking (fallback):** the student states their CohortOS ID to a staff
member, who enters it against the admission record via Settings. This fills the existing
"cohortos id (optional)" field from Module 1's admission form — the two features were
always meant to connect. Staff sees a confirm screen ("linking to: [name, roll]") before
committing. Owner can unlink/reassign later; every linking action is audit-logged.
- **Lost access:** since all data is anchored to admission_id (not account_id), a student who
loses account access can create a new account and re-link via a fresh join code or
staff-manual linking — no separate recovery flow needed for this case, no data loss.

**Account identifier `[FLEX]` `[LOCKED]`:** Centre's choice — phone number, email, or both,
configurable per centre at onboarding (or left open for the student to pick at signup).
Whichever identifier(s) are enabled, a dedup check runs against them to prevent duplicate
accounts.

**Verification `[BULLET]` `[LOCKED]`:** No upfront email/SMS verification step at account
creation. An unlinked account has zero access — no Vault, no AI Tutor, no records, nothing
— so it carries no abuse value on its own (this also closes the Module 9.3 quota-farming
risk). Possession of a valid join code, or staff-mediated linking, *is* the identity proof; this
achieves "bulletproof" without any CohortOS-side verification infrastructure or ongoing
server cost.

**Login/recovery `[BULLET]` `[LOCKED]`:** Passwordless. Login is a one-time code sent via
whichever channel matches the stored identifier, dispatched through the same
`NotificationService` abstraction (Module 6) already built for attendance/payment
messaging — WhatsApp/SMS for phone, a low-volume free-tier transactional email sender
for email. No separate auth server, no new recurring cost: email OTP volume is login-only
(low), and phone OTP rides on whatever messaging channel/cost the centre already budgets
for.

- **Privacy `[BULLET]`:** A coaching cannot see another coaching's data about the same
student. Tenant isolation is strict.
- **Student view:** Read-only attendance, payment status, results, and access to the AI
Tutor (Module 9) + Vault (Module 5) + in-app threads (Module 8.4).
- **Parent link `[NEW]`:** Parents with their id can be linked to the student's account with
read-only view across all their coachings, plus AI-generated progress summaries.
- **In-app conversation threads (8.4) `[NEW]`:** Every student AI query is saved in a thread
the teacher can open. The teacher can take over the thread and reply directly, or annotate
the AI answer. The teacher can also start a thread ("explain today's class to absentees").
Threads are searchable per student/batch/topic. AI can assist teacher replies (draft,
translate Bangla↔English). **Priority queue `[LOCKED]`:** reuses the confidence/cohort-
severity scoring engine defined in Module 9.2 — no separate system is built. A thread is
flagged "not confident — ask teacher" when the 9.1 self-verification pass detects a
mismatch, retrieval found no grounded source chunks, or the student explicitly pushes back.
Flagged threads are ranked by confidence (lowest first) × cohort size sharing the same
misconception × proximity to a relevant exam — identical ranking logic to the 9.2 analytics
suggestions, so one engine serves both surfaces.

## 9. Module: AI — CohortOS Solve (Student Tutor) & CohortOS Teach (Teacher
Co-Pilot) `[NEW]`
### 9.1 CohortOS Solve (student-facing AI tutor)
**Pipeline (stress-tested, bulletproof):**
1. **Intake & classification:** detect subject, topic, board (HSC/Medical/BUET), question type
(MCQ/written/CQ).
2. **Retrieval (NotebookLM-style):** grounded retrieval over the *student's enrolled
coaching's resource set* (teacher's notes, textbook chapters, past papers) plus vetted
primary sources pre-loaded per subject. The model is constrained to cite retrieved chunks.
3. **Structured system prompt:** break the question → identify concept → solve
step-by-step → cross-check units/signs/edge cases → output in three blocks: **Answer**,
**How**, **Why**.
4. **Self-verification pass:** a second model call re-derives the answer and flags mismatch;
if mismatch persists, it says rather than hallucinate.
5. **Teacher alignment:** the teacher can edit the additional system prompt per subject (e.g.,
"always use my sign-convention", "never skip the free-body diagram") and can
review/annotate any student query.
6. **Conversation thread:** the student can ask follow-ups; the teacher can step into the
same thread (Module 8).
7. **Cost control:** route easy queries to a cheap model tier and hard written problems to a
higher tier; cache common questions; enforce per-student daily query caps set by the
coaching.

### 9.2 CohortOS Teach (teacher AI co-pilot) — bulletproof requirements
- **Never invent unapproved syllabus content `[BULLET]`:** The Co-Pilot may only generate
content grounded in (a) the teacher's own approved notes/past papers and (b) the centre's
vetted primary resources. Any item that cannot be traced to a source is flagged "ungrounded
— needs teacher review" before creating the things and is never auto-published.
- **Few-shot style locking `[BULLET]`:** The teacher uploads past papers/notes; the Co-Pilot
builds a few-shot prompt profile (style, terminology, difficulty, sign-conventions) and locks
generation to that profile. The profile is editable and versioned.
- **Teacher review gate `[BULLET]`:** No AI-generated item (MCQ, written question,
solution, analytics suggestion) reaches students until the teacher explicitly approves. Drafts
live in a "Review Queue."
- **Versioning + audit trail `[BULLET]`:** Every AI-generated item has a version history
(accept/edit/reject) with timestamps, staff ID, and the source chunks used. Rejects are
retained for learning.
- **High-signal analytics `[BULLET]`:** When the teacher asks for suggestions, the Co-Pilot
returns *less content but hitting the patterns that matter* — e.g., "3 students share the same
rotational-dynamics misconception; here is one targeted 15-min recap + 15 MCQs," not a
generic dump but bulletproof. Suggestions are ranked by expected impact (cohort size ×
weakness severity).
- **Bangla + English output `[FLEX]`:** Output in the teacher's preferred language and
terminology (set in profile). Mixed Bangla-English (Banglish) supported.
- **Low-confidence detection `[BULLET]`:** A confidence score is computed for every output;
below threshold → "needs teacher review" flag, no silent hallucination.
- **Exam integration `[BULLET]`:** Generates items compatible with Module 4 templates
(MCQ / written / CQ) and can push approved items into the exam bank or the Vault (Module
5) with access rules. **Optional OCR assist `[NEW]`:** teacher can upload a student's
handwritten answer image; the Teacher Co-Pilot (Module 9) transcribes and grades against
a rubric, flagging conceptual errors. OCR is optional and never auto-publishes.

### 9.3 Gemini cost model (non-negotiable)
- **Default `[BULLET]`:** Free-tier Google Gemini (Google AI Studio key the centre already
owns). No paid key required on day one.
- **Rate-limit handling `[BULLET]`:** The system detects free-tier rate limits (429/quota
errors) and automatically falls back to local/cached behaviour or queues the request with a
user-visible "will answer when quota resets" notice.
- **Optional upgrade `[FLEX]`:** Centres can paste their own paid Gemini key or any api key
or connect a Cloud project later for higher limits.
- **Per-student daily query caps `[FLEX]`:** Configurable by the centre owner so free-tier
quotas are never exhausted by a single student. Caps are per-tier (MCQ vs written) and
reset daily.
- **Caching `[BULLET]`:** Common questions are cached (semantic match) to reduce API
calls.
- **Model routing `[BULLET]`:** Easy problems → cheap model tier; hard written problems
→ premium tier

## 10. Module: Multi-Tenancy & Founder Super-Admin `[NEW]`
- **Tenant isolation `[BULLET]`:** Each coaching centre is a tenant with isolated data, config,
and AI keys. Cross-tenant access is impossible by design.
- **Per-centre config `[FLEX]`:** Mode (offline/cloud/hybrid), thresholds, templates, channels,
AI keys, pricing tier — all per-tenant.
- **Founder super-admin `[NEW]` `[LOCKED]`:** A panel for you (the founder) to see all
tenants, usage, billing status, and suspend/extend tenants. Since every tenant supplies its
own Gemini key (free-tier by default, or their own paid key), CohortOS has no billing
visibility into any tenant's spend — that line is dropped. In its place: query volume,
429/rate-limit hit frequency, cache hit rate, and MCQ-vs-written usage split per tenant, so
you can spot centres about to get quota-starved and proactively nudge them toward a paid
key.
- **Pricing engine `[NEW]`:** Tiered monthly SaaS by student count (Starter ৳5k ≤500,
Growth ৳10–15k ≤1500, Scale custom ≤6000) with per-student overage and annual
discount.
- **Bring-your-own-key `[FLEX]`:** A centre can supply its own Gemini key for unlimited AI
use, decoupled from CohortOS billing.

## 11. Module: Parent Portal (optional) `[NEW]`
- **Read-only view `[FLEX]`:** Attendance, fees, results, and AI-generated progress
summary across all the parent's linked students.
- **Notifications `[FLEX]`:** Targeted, rule-based, per-student updates (not spammy group
messages).
- **Privacy `[BULLET]`:** A parent sees only their own linked students.

---
*End of SPEC.md v2.2. Module 8's join/verification/thread-priority mechanics were locked in
v2.1. v2.2 locks: roll-number bitmask encoding (Module 1), a single irregularity threshold
shared by Modules 2 & 3, anti-leak override scope (Module 5), biometric/manual attendance
precedence (Module 2), and the founder dashboard's AI-usage metrics (Module 10). All
`[FLEX]` / `[BULLET]` / `[NEW]` / `[LOCKED]` markers indicate upgrades over the original
SPEC.*
