# SPEC.md — CoachMate: AI-Powered Coaching Operating System (v3.0 — Stress-Tested & Hardened)

> **This file is the single source of truth.** The agent must re-read this file at the start of
> each session. Nothing here should be re-explained by the user; if something is genuinely
> missing, the agent must ask, then append the answer back under the relevant section.
>
> **Marker legend:** `[FLEX]` flexible/configurable · `[BULLET]` bulletproof/hardened behavior ·
> `[NEW]` net-new capability · `[LOCKED]` decision finalized, do not silently change ·
> **`[HARDENED v3]`** issue found and fixed in this stress-test pass · **`[ASSUMED v3]`**
> reasonable default filled in for a genuine spec gap — override any of these explicitly if wrong,
> otherwise treat as locked. See **Appendix A** for the full list of what changed and why, and
> **Section 14** for the MVP phasing this spec now assumes.

## 0. Project Facts
- **Product:** CoachMate — productizable, multi-tenant SaaS for coaching centres
(200–6000 students) in Bangladesh, India, and globally.
- **Origin client:** Swapan Kumar Saha, physics coaching teacher, Barishal (teaching since
2008), author of "Swapan's Physics." ~400 students, ~10 batches. Remains the design
anchor and the Phase‑1 pilot centre (see §14).
- **Platform:** Desktop app **and** responsive web/mobile/desktop for student/parent faces.
`[FLEX]` The desktop app is the offline-first front desk, switchable to cloud-first per centre;
the web app is the cloud-first option for centres that prefer never installing anything.
- **Mode toggle `[FLEX]`:** Each centre chooses one mode at onboarding (changeable later,
with a guided one-time migration, not a silent flag flip):
  - **Offline-first (default):** local SQLite, syncs to cloud when online.
  - **Cloud-first:** hosted DB, local cache for offline resilience.
  - **Hybrid:** desktop for desk staff + web/mobile/desktop for teachers/students/parents.
- **Environment constraints:** Internet is available but unreliable (frequent power cuts). **All
core features (attendance, payment, exams, records, content access) must work with zero
internet (default).** Only messaging, AI, and cloud sync require internet and must
queue/degrade gracefully.
- **Users `[FLEX]`:** Multi-staff with RBAC (owner, desk, teacher, assistant) with owner being
admin — replaces v1's single-teacher login. Students and parents have optional accounts
(see Module 8). A centre may still run in single-user mode.
- **Pricing `[NEW]` `[HARDENED v3]`:** Tiered monthly SaaS by student count. The v2.2 range
"Growth ৳10–15k" had no rule for which price a centre actually pays — fixed with sub-bands:
  - **Starter:** ৳5,000/mo, ≤500 students.
  - **Growth‑A:** ৳10,000/mo, 501–1000 students.
  - **Growth‑B:** ৳15,000/mo, 1001–1500 students.
  - **Scale:** custom quote, 1501–6000 students.
  - **`[ASSUMED v3]` Beyond 6000 students:** treated as a new Scale negotiation, not an
    automatic overage extrapolation — the model hasn't been validated at that size yet.
  - **Per-student overage:** flat per-student rate above a tier's ceiling until the centre
    upgrades tiers (grace period: 1 billing cycle before forced upgrade prompt).
  - **Annual discount:** available (rate `[ASSUMED v3]` — insert once finance confirms; do not
    ship a hardcoded number without sign-off).
  - **`[ASSUMED v3]` Currency/region:** BDT (৳) is the launch currency for Bangladesh; India
    and other markets need a currency field per tenant and local-currency price parity, not
    a hard BDT conversion at checkout. Flagged as a Phase‑2 item (§14) — don't block Phase‑1
    launch on multi-currency billing.
  - **`[HARDENED v3]` License enforcement gap (this was previously undefined and is a real
    revenue-leak risk):** Because offline-first mode runs entirely on local SQLite, a centre
    that stops paying can keep using the desktop app indefinitely with zero technical
    enforcement. Fix: the desktop app performs a lightweight online license check on a
    rolling basis (e.g., once per 14 days when internet is available) against the tenant's
    billing status. If billing is delinquent past a grace window (`[ASSUMED v3]`: 30 days), the
    app moves to a **read-only lockout** — all existing data remains visible and exportable
    (never deleted, never held hostage), but new attendance/payment/exam entries are
    blocked until payment resumes. If the centre never reconnects to the internet at all, no
    enforcement is possible — this is a known, accepted trade-off of true offline-first design
    and should be priced in as a small % of unavoidable churn leakage rather than "solved."

## 1. Module: Admission
**Form fields:** Name, Batch (select from configured slots), Roll (auto-generated, editable),
student phone, parent phone(s), WhatsApp number, coachmate id (optional). **No Facebook
ID or college name field.** `[FLEX]` Centres may add custom fields (e.g., school, college,
guardian occupation, custom field named by user) or archive any field via Settings.
`[HARDENED v3]` **Field removal is a soft-delete/archive, never a hard delete** — historical
records keep the data they already captured even after a field is archived from the active
form; archiving only stops the field appearing for *new* admissions. This matters because
Module 4/7 promise history is "never lost," and a hard field delete would silently violate that.

**Batch configuration `[FLEX]`:**
- Days: any combination of Sat–Fri.
- Time: 24-hour format (bulletproof against am/pm ambiguity).
- Batch display name: auto-generated (e.g. "Sat,Mon,Wed 14:00") or manual override.
- **Batch templates `[NEW]`:** Per coaching type (medical prep, HSC, English, skill) —
pre-set days, times, exam structures, messaging templates, and AI system prompts (for
editing system prompts they will first request the coachmate team, since the system
prompts are not to be exposed or leaked without request). Templates are editable
and exportable.

**Roll number encoding `[FLEX]` `[LOCKED]`:**
- Default scheme: `[DaySet][TimeCode][Serial]`. DaySet is a **3-digit bitmask** (Sat=1,
Sun=2, Mon=4, Tue=8, Wed=16, Thu=32, Fri=64 — sum the selected days, zero-padded
001–127), fixed-width regardless of how many days are selected. TimeCode is a 2-digit
24-hour hour. Serial is 3 digits. Example: Sat+Mon+Wed = 1+4+16 = `021`, 14:00 = `14`,
serial 33 = `033` → roll = **`02114033`**.
- `[HARDENED v3]` **Serial scope, made explicit (previously implied, not stated):** Serial
  increments **per unique (DaySet, TimeCode) pair**, not globally. `02114033` and
  `02115033` are independent counters even though they share a DaySet.
- `[HARDENED v3]` **Same-slot, different-batch collision (real bug in v2.2):** Two genuinely
  different batches (e.g., separate Physics and Chemistry sections) can legitimately share
  the exact same days *and* start time. Under the old scheme their rolls would be visually
  indistinguishable, which is confusing for desk staff reading a roll off an ID card. Fix: the
  roll number is a **display/lookup convenience, not the sole batch identifier** — every
  student is internally keyed by a canonical `batch_id` + `admission_id`, so no data ever
  actually collides — but at the UI level, when a centre creates a second batch with an
  identical DaySet+TimeCode, the system prompts for a one-letter disambiguator suffix
  (e.g., `02114033-A` / `02114033-B`), auto-applied to all rolls in that slot going forward.
- Centres may switch to a plain serial scheme or define their own encoding in Settings. The
  default scheme remains available for backward compatibility with the origin client.

**Roll/batch changes `[BULLET]`:** If a student's batch or roll changes, generate the new roll
and **migrate full history** (attendance, payments, results, threads) to the new roll/account
— never lose history. Migration is atomic (transactional) and logged.

**Duplicate detection `[BULLET]` `[HARDENED v3]`:** Before saving, check for likely
duplicates using the **student's own phone number** (same name + same student phone, or
the same student phone reused across records). **Parent/WhatsApp phone numbers are
explicitly excluded from this check** — siblings routinely share a parent's phone number,
and flagging that as a duplicate would block completely legitimate admissions. If a match is
found, **show the error and the specific reason first** (e.g. "Phone number already
registered to student X, roll Y") before allowing the teacher to proceed or cancel. Duplicate
resolution is idempotent.

**Editing `[BULLET]`:** Only authorised staff can edit student records. Every other field is
editable. All edits are audit-logged.

## 2. Module: Attendance / Irregularity
**Hardware `[BULLET]`:** ZKTeco K60 and ZKTeco series as default option (or compatible
to any biometric device) over local network (static IP). Use `pyzk` to pull punches — avoids
proprietary `zkemkeeper.dll`. Falls back to manual entry if the device is offline. Device linking
is manual (teacher enters the device's internal user ID per student).
`[HARDENED v3]` **Device clock drift:** the sync job checks the device's onboard clock
against server/system time on every pull and auto-corrects drift under 2 minutes silently;
drift over 2 minutes is flagged to the owner (don't silently trust an unreliable clock to decide
who's "late").
`[HARDENED v3]` **Bulletproof manual attendance sheet, spec'd concretely** (v2.2 only
said "like Google Sheets," which isn't a spec): a per-batch, per-day grid — rows = enrolled
students, columns = P / L / A / cross-batch — tap-to-cycle status per cell, fully usable
offline, multiple desk staff can edit different cells concurrently (per-field last-write-wins per
§7's sync rule, with the same student+day+field conflict surfaced in the owner's conflict log
if two staff genuinely disagree on one cell).

**Late rule `[FLEX]`:** Configurable threshold, default **12 minutes** after batch start.
**Per-batch override** allowed (not only global). Past threshold → "Late" (not absent).
`[HARDENED v3]` **Unbounded "late" window (gap in v2.2):** a punch nominally counts as
"Late" no matter how far past the threshold it is, which would let a student punch in 5
minutes before class *ends* and still be marked Late instead of Absent. Fix: a second,
configurable cutoff — **`[ASSUMED v3]` default = batch duration, or 90 minutes, whichever is
shorter** — beyond which a punch no longer counts as attendance for that session at all
(logged as a raw punch, but the day's status stays Absent unless cross-batch credit applies).

**Absent rule `[BULLET]`:** If a student does not punch in on any batch day within their
assigned batch, mark absent (visually distinct, e.g. red dot). Anti-proxy: if the same device
logs two punches within an implausible window, flag for review.

**Cross-batch attendance `[BULLET]` `[HARDENED v3]`:** If a student attends a *different*
batch time slot **on their own batch's day**, count it as present for that day — **restricted to
batch slots the student is actually enrolled in** (v2.2 didn't scope this, which would have let
any student punch into any unrelated batch's device and get free credit — a proxy loophole
big enough to defeat the whole anti-proxy system). A student enrolled only in one batch has
no cross-batch credit available by definition. Cross-batch validation is explicit and logged.

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
- **Extra template:** distinct message for "late 3 days in a row," separate from
single-day-late and absence templates.
- All templates are teacher-editable text, stored persistently, reused until changed.

## 3. Module: Payment
**Tracking granularity `[FLEX]`:** Default = Paid / Unpaid status **per month only** (no
amount). **Optional amount + receipt mode** for centres that want it; the simple mode
remains default for the origin client.
`[HARDENED v3]` **Missing third state:** many centres give scholarships, sibling discounts,
or fee waivers for a given month — v2.2 only had Paid/Unpaid, which forces those students
into an incorrect "Unpaid" state that then triggers nag messages to a family that owes
nothing. Fix: add a third per-month status, **Waived**, settable only by the owner
(audit-logged, requires a one-line reason), which is excluded from both the automated
payment nag and the payment-status irregularity feed.

**Locking mechanic `[BULLET]`:** Student → Payment section → row of months (filled dot =
paid, hollow = unpaid). Tapping a month then "Lock" marks it paid and **locks** that record
(prevents accidental edits). Manual teacher action — no auto-marking. Locked records are
immutable except by an explicit owner unlock with audit log.
`[HARDENED v3]` **Locked records vs. the sync engine's last-write-wins rule (§7):** a locked
payment record is explicitly **excluded** from ordinary field-level last-write-wins conflict
resolution. Any conflicting sync write against a locked record is rejected outright and routed
to the owner's conflict log rather than silently applied — this closes a real hole where a
device syncing stale data could otherwise "win" and quietly un-flip a locked payment.

**Delayed-payment messaging `[FLEX]`:**
- Trigger date configurable (day of month, previous vs. current month target).
- **Green/white box logic `[BULLET]`:** every unpaid student defaults to green (will receive
message); teacher can toggle to white (will NOT receive). White stays white — **no
auto-reset to green** — until the teacher manually flips it back, **scoped to that specific
month's box only** `[HARDENED v3]` — a new month's box always starts green by default
regardless of a prior month being flipped white, so the exclusion doesn't silently carry
forward forever.
- **Exclusion rule `[FLEX]` `[LOCKED]`:** Uses the same **irregularity threshold** as Module
2 (default: fewer than 3 days attended that month, per-batch editable) — one setting drives
both exclusions, not two independent numbers. Excluded students are covered by the
consolidated teacher alert defined in Module 2, not a separate automated payment message.
- **bKash/Nagad deep-link `[NEW]`:** Payment reminders can include a deep-link or
copy-paste payment target. `[HARDENED v3]` **Scope boundary, made explicit:** this is a
*convenience link only* — CoachMate does not integrate a payment gateway or auto-
reconcile transactions in v3.0. Marking a month "Paid" remains a manual teacher action after
they've verified receipt of funds by whatever means. Automatic reconciliation via bKash/
Nagad webhooks is a distinct, larger scope item explicitly deferred (see §14).
- Optional: teacher can receive a summary message of all delayed-payment students each
cycle (Send / Don't Send choice).

## 4. Module: Exams / Results
**Per-chapter exam structure (the "main exam") `[FLEX]`:**
1. 15 MCQs (Medical/Varsity style) in 9 minutes — result given immediately, hand to hand.
2. 6 physics maths questions (BUET style), 60 marks, 18 minutes.
3. 1 CQ (HSC-style), 10 marks.
- Written-portion (2 & 3) results entered by the teacher within the next 2–3 classes.
  `[HARDENED v3]` This window is a soft target, not a block: if results aren't entered within it,
  the exam surfaces on the teacher's dashboard as "overdue entry" — a nudge, never a lock,
  since blocking would punish a busy teacher for the student's benefit.
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

**Batch-level analytics `[NEW]` `[HARDENED v3]`:** Per-topic weakness heatmaps,
MCQ-vs-written gaps, and cohort comparison are read-only views over existing exam data and
are Phase‑1 scope. The "students likely to struggle next exam" **prediction** is a distinct,
higher-risk promise (v2.2 didn't specify a method, which risks turning into an open-ended ML
project before launch). Scoped down for v3.0: MVP uses a **transparent heuristic**, not a
model — e.g., attendance below the irregularity threshold combined with a declining trend
across the last 3 exam scores in a topic — shown to the teacher with the specific numbers
that triggered it, never as an unexplained black-box score. A learned model is an explicit
Phase‑3 upgrade (§14), not a v3.0 commitment.

## 5. Module: Content (CoachMate Vault)
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
- **Anti-leak `[BULLET]` `[LOCKED]` `[HARDENED v3]`:** In-app viewer with **dynamic
  watermarking** (a faint, moving overlay showing the viewing student's name/roll +
  timestamp, so a screenshot or phone photo is traceable to who took it), a no-download flag,
  and per-user session tokens. **Centre-wide default policy is owner-only.** Any teacher or
  assistant can relax protection on a per-resource basis (any resource, not just their own) —
  always audit-logged and the resource is visibly labeled "protection relaxed" wherever it
  appears. Desk role has no access to anti-leak controls.
- **Big-file support:** No Telegram-Premium-style limits; chunked upload + resumable
  transfer. `[HARDENED v3]` **Contradiction fixed:** "no-download" and "resumable download"
  looked like they conflicted. Resolved — the chunked/resumable mechanism applies to (a)
  the teacher's original upload, and (b) the encrypted local cache the in-app viewer
  maintains for offline viewing (§ below); it never exposes a raw, portable file to a student on
  a protected resource. Resources a teacher explicitly marks downloadable (e.g., a syllabus
  PDF with no anti-leak need) are a separate, simpler path with no watermarking overhead.
- **Online coaching mode `[NEW]`:** Live class integration, chat, hand-raise, polls — for
  centres that run online batches.
- **Offline cache `[BULLET]` `[HARDENED v3]`:** Students can pre-download allowed
  resources for offline study; access rules re-evaluate on reconnect. **TTL added:** a cached
  protected resource auto-expires and deletes itself from local storage after
  **`[ASSUMED v3]` 14 days** without a successful reconnect-and-revalidate — otherwise a
  student whose access is revoked (e.g., unenrolled) could sit on a fully offline device
  indefinitely and the revocation would never take effect.
- **Optional AI video-suggest `[FLEX]`:** Low-priority helper tab to suggest candidate
  YouTube videos for a topic — explicitly optional, must not consume significant build time.

## 6. Module: Messaging Architecture (cross-cutting)
- **`NotificationService` abstraction `[BULLET]`:** Single internal service used by attendance
(Module 2), payment (Module 3), in-app threads (Module 8), and account login/recovery
(Module 8). Underlying provider (WhatsApp Business API, SMS gateway, in-app push, or a
low-volume transactional email sender) is swappable without touching business logic.
- **Channel choice `[FLEX]`:** Per-centre, per-message-type channel selection with monthly
cost caps.
- **`[HARDENED v3]` Cost-cap exhaustion policy (undefined in v2.2):** when a centre's
monthly cost cap is reached mid-cycle, bulk/automated notifications (absence pings, payment
nags, summaries) queue and resume next cycle rather than sending. **Login OTPs and the
consolidated teacher alert (Modules 2/3/8) are exempt from the cap** — they're core-
functionality messages, not bulk marketing-style sends, and blocking them would break the
product, not just delay a nag.
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
review — **except locked payment records, which are excluded from LWW per §3's
hardening** and always route conflicts to manual owner review. Sync is idempotent and
resumable.
- **Multi-staff RBAC `[FLEX]`:** Owner, desk, teacher, assistant roles with per-centre
permissions.
- **Data integrity `[BULLET]`:** History never lost on roll/batch changes; locked payment
records not silently editable; all mutations audit-logged.
- **`[HARDENED v3]` Backup & disaster recovery (missing entirely in v2.2 — a serious gap for
  an offline-first app on unreliable power):**
  - Local SQLite runs in **WAL mode** so an unclean shutdown from a power cut doesn't
    corrupt the database.
  - The desktop app takes an **automatic local snapshot** on a schedule (`[ASSUMED v3]`:
    daily, keeping 7 rolling copies) to a separate file, independent of the live DB.
  - When online, the same snapshot is pushed to encrypted cloud storage as an
    off-site backup, on top of the normal sync stream.
  - **Data export/portability:** the owner can export the centre's full dataset (students,
    attendance, payments, exams — CSV or a single portable archive) at any time. This is
    both a disaster-recovery safety net and a trust signal: a centre's data is never locked
    into CoachMate.
- **`[HARDENED v3]` Local data encryption:** the local SQLite file (and any offline cache from
  Module 5) is encrypted at rest, not just data in transit during sync — a stolen or lost
  desktop otherwise exposes every student's phone number and payment status in plaintext.
- **`[HARDENED v3]` Schema/version migration:** since independent centres run the desktop
  app on their own update cadence, every schema change ships with a forward migration
  that runs automatically on update and is tested to never require a manual DB touch or
  data loss on any prior supported version.
- **Expandability `[BULLET]`:** Data model anticipates student/parent logins (Module 8) and
multi-tenancy (Module 10) without rebuild.
- **UI `[FLEX]`:** Simple to use but highly attractive design and flexible, low-friction for
non-technical desk staff; Bangla + English toggle; mobile as well as desktop responsive for
student/parent app as well as the owner.

## 8. Module: Student & Parent Accounts `[LOCKED v2.1]`

**Join mechanism `[BULLET]` `[LOCKED]`:** Two entry points, one underlying operation —
`link(admission_id, coachmate_account_id)`, always staff-auditable, never silent.
- **Per-admission join code (primary):** generated automatically at admission (Module 1),
tied to that exact admission_id — not a centre-wide PIN. Delivered as a QR code (printed
on ID card/receipt, or shown on desk screen) plus a short alphanumeric fallback for manual
typing. Single-use, `[HARDENED v3]` **default expiry shortened to 30 days** (v2.2's 90-day
default left a long window where a lost or stolen physical ID card could be used by someone
else to claim the account first); staff can regenerate on demand, which auto-invalidates the
prior code, and can set a longer expiry per centre if they genuinely need it. Scanning/
entering the code *is* claiming that specific admission record — no name/phone matching
required, no ambiguity possible. `[HARDENED v3]` **Fallback code strength, specified:** the
alphanumeric fallback is minimum 8 characters, and join attempts are rate-limited (max 5
tries per admission_id per hour, then a short lockout) to prevent brute-forcing it.
- **Manual staff-linking (fallback):** the student states their CoachMate ID to a staff
member, who enters it against the admission record via Settings. This fills the existing
"coachmate id (optional)" field from Module 1's admission form — the two features were
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
— so it carries no *data* abuse value on its own (this also closes the Module 9.3 quota-
farming risk). Possession of a valid join code, or staff-mediated linking, *is* the identity
proof; this achieves "bulletproof" without any CoachMate-side identity-verification
infrastructure or ongoing server cost. `[HARDENED v3]` **One residual abuse vector remains
even with zero data value: OTP-send itself can be weaponized as an SMS/email bombing
harassment tool against a phone number that isn't even the attacker's.** Fix: signup and
login OTP requests are rate-limited per identifier *and* per source IP (`[ASSUMED v3]`: 3
requests per identifier per hour), independent of whether the resulting account ever gets
linked to anything.

**Login/recovery `[BULLET]` `[LOCKED]`:** Passwordless. Login is a one-time code sent via
whichever channel matches the stored identifier, dispatched through the same
`NotificationService` abstraction (Module 6) already built for attendance/payment
messaging — WhatsApp/SMS for phone, a low-volume free-tier transactional email sender
for email. No separate auth server, no new recurring cost: email OTP volume is login-only
(low), and phone OTP rides on whatever messaging channel/cost the centre already budgets
for. `[HARDENED v3]` **OTP parameters, specified (undefined in v2.2):** 6 digits, 10-minute
expiry, max 5 verification attempts per code before it's invalidated and a new one must be
requested (subject to the rate limit above).

- **Privacy `[BULLET]`:** A coaching cannot see another coaching's data about the same
student. Tenant isolation is strict.
- **Student view:** Read-only attendance, payment status, results, and access to the AI
Tutor (Module 9) + Vault (Module 5) + in-app threads (Module 8.4).
- **Parent link `[NEW]` `[HARDENED v3]`:** Parents can be linked to a student's account with
read-only view across all their coachings, plus AI-generated progress summaries. **Linking
mechanism, made explicit (v2.2 never actually said how a parent gets linked):** a parent
links using the **same per-admission join code** as the student, producing a distinct
parent-role account mapped to the same `admission_id` — staff or the student can share the
code with a parent, and either the QR/receipt copy already reaches the parent naturally, or
staff re-share it manually. Because the code carries no identity claim beyond "possession,"
an owner can revoke a specific parent-linked account at any time (audit-logged) if a linking
was made in error or a family situation changes (e.g., custody).
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

## 9. Module: AI — CoachMate Solve (Student Tutor) & CoachMate Teach (Teacher Co-Pilot)

### 9.1 CoachMate Solve (student-facing AI tutor)
**Pipeline (stress-tested, bulletproof):**
1. **Intake & classification:** detect subject, topic, board (HSC/Medical/BUET), question type
(MCQ/written/CQ).
2. **Retrieval (NotebookLM-style):** grounded retrieval over the *student's enrolled
coaching's resource set* (teacher's notes, textbook chapters, past papers) plus vetted
primary sources pre-loaded per subject. The model is constrained to cite retrieved chunks.
   `[HARDENED v3]` **Empty-retrieval behavior, made explicit (v2.2 flagged the thread but
   never said what the student actually sees):** when no grounded chunk is found, the
   student still gets an answer attempt, but it's visibly labeled "general knowledge — not
   verified against your coaching's material" rather than silently presented with the same
   confidence as a grounded answer, alongside the existing teacher-review flag.
3. **Structured system prompt:** break the question → identify concept → solve
step-by-step → cross-check units/signs/edge cases → output in three blocks: **Answer**,
**How**, **Why**.
4. **Self-verification pass:** a second model call re-derives the answer and flags mismatch;
if mismatch persists, it says rather than hallucinate. `[HARDENED v3]` **Cost conflict fixed:**
doubling every single query's model cost fights directly against the free-tier sustainability
goal in §9.3. Self-verification runs on the **written/CQ tier only** (where errors are costlier
and harder for a student to self-spot); MCQ-tier answers, which are cheap to check by
elimination, skip the second pass by default. A centre can force it on for MCQs too if they
want, at their own quota cost.
5. **Teacher alignment:** the teacher can edit the additional system prompt per subject (e.g.,
"always use my sign-convention," "never skip the free-body diagram") and can
review/annotate any student query.
6. **Conversation thread:** the student can ask follow-ups; the teacher can step into the
same thread (Module 8).
7. **Cost control:** route easy queries to a cheap model tier and hard written problems to a
higher tier; cache common questions; enforce per-student daily query caps set by the
coaching. `[HARDENED v3]` **Cap override path added:** a teacher can grant a specific
student a temporary cap increase (e.g., during exam crunch), audit-logged, expiring
automatically after a set number of days rather than becoming a silent permanent
exception.

### 9.2 CoachMate Teach (teacher AI co-pilot) — bulletproof requirements
- **Never invent unapproved syllabus content `[BULLET]`:** The Co-Pilot may only generate
content grounded in (a) the teacher's own approved notes/past papers and (b) the centre's
vetted primary resources. Any item that cannot be traced to a source is flagged "ungrounded
— needs teacher review" before creating the thing and is never auto-published.
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
generic dump. Suggestions are ranked by expected impact (cohort size × weakness
severity), using the same transparent-heuristic approach as §4's exam predictions — no
unexplained black-box ranking.
- **Bangla + English output `[FLEX]`:** Output in the teacher's preferred language and
terminology (set in profile). Mixed Bangla-English (Banglish) supported.
- **Low-confidence detection `[BULLET]`:** A confidence score is computed for every output;
below threshold → "needs teacher review" flag, no silent hallucination.
- **Exam integration `[BULLET]`:** Generates items compatible with Module 4 templates
(MCQ / written / CQ) and can push approved items into the exam bank or the Vault (Module
5) with access rules. **Optional OCR assist `[NEW]`:** teacher can upload a student's
handwritten answer image; the Co-Pilot transcribes and grades against a rubric, flagging
conceptual errors. OCR is optional and never auto-publishes. `[HARDENED v3]` **Accuracy
caveat, made explicit:** handwritten Bangla OCR is meaningfully less reliable than printed
text or English handwriting; the UI marks OCR-sourced transcriptions as "auto-transcribed —
verify before grading" so a teacher never trusts a misread digit or sign at face value.

### 9.3 Gemini cost model (non-negotiable)
- **Default `[BULLET]`:** Free-tier Google Gemini (Google AI Studio key the centre already
owns). No paid key required on day one.
- **Rate-limit handling `[BULLET]` `[HARDENED v3]`:** The system detects free-tier rate limits
(429/quota errors) and automatically falls back to local/cached behaviour or queues the
request with a user-visible "will answer when quota resets" notice. **Queue priority added:**
when quota is tight, a queued **teacher** Co-Pilot request is served before a queued
**student** Solve request of the same tier — a teacher blocked on quota affects a whole
batch's prep, a single student's queued question doesn't. Queue also has a max depth and
entries older than `[ASSUMED v3]` 24 hours expire with a clear "quota didn't recover in time,
please resend" message rather than silently answering something the student has moved
past.
- **Optional upgrade `[FLEX]`:** Centres can paste their own paid Gemini key or any API key,
or connect a Cloud project later for higher limits.
- **Per-student daily query caps `[FLEX]`:** Configurable by the centre owner so free-tier
quotas are never exhausted by a single student. Caps are per-tier (MCQ vs written) and
reset daily. Overridable per-student, temporarily, per §9.1's hardening above.
- **Caching `[BULLET]`:** Common questions are cached (semantic match) to reduce API
calls.
- **Model routing `[BULLET]`:** Easy problems → cheap model tier; hard written problems →
premium tier.

## 10. Module: Multi-Tenancy & Founder Super-Admin
- **Tenant isolation `[BULLET]`:** Each coaching centre is a tenant with isolated data, config,
and AI keys. Cross-tenant access is impossible by design.
- **Per-centre config `[FLEX]`:** Mode (offline/cloud/hybrid), thresholds, templates, channels,
AI keys, pricing tier — all per-tenant.
- **Founder super-admin `[NEW]` `[LOCKED]`:** A panel for the founder to see all tenants,
usage, billing status, and suspend/extend tenants. Since every tenant supplies its own
Gemini key (free-tier by default, or their own paid key), CoachMate has no billing visibility
into any tenant's spend — that line is dropped. In its place: query volume, 429/rate-limit hit
frequency, cache hit rate, and MCQ-vs-written usage split per tenant, so the founder can
spot centres about to get quota-starved and proactively nudge them toward a paid key.
  `[HARDENED v3]` **Privacy boundary, made explicit (mirrors §8's tenant isolation, but
  v2.2 never stated it for the founder's own access):** operational metrics only. The founder
  panel has **no access to any tenant's student PII, academic content, exam data, or
  message/thread contents** by default. A support-access grant into a specific tenant's data
  requires the tenant owner's explicit, time-boxed, audit-logged consent — never a standing
  backdoor.
  `[HARDENED v3]` **Suspension scope, made explicit:** "suspend" acts on cloud/AI/sync
  features and the tenant's CoachMate billing record — it does **not**, and structurally
  cannot, reach into an offline-first centre's local desktop data, per §0's licensing hardening.
- **Pricing engine `[NEW]`:** As defined in §0 (Starter/Growth‑A/Growth‑B/Scale, per-student
overage, annual discount).
- **Bring-your-own-key `[FLEX]`:** A centre can supply its own Gemini key for unlimited AI
use, decoupled from CoachMate billing.

## 11. Module: Parent Portal (optional)
- **Read-only view `[FLEX]`:** Attendance, fees, results, and AI-generated progress
summary across all the parent's linked students.
- **Notifications `[FLEX]`:** Targeted, rule-based, per-student updates (not spammy group
messages).
- **Privacy `[BULLET]`:** A parent sees only their own linked students.
- **Linking:** see §8's hardened parent-link mechanism — a parent account attaches via the
same per-admission join code used by the student, never a separate unverified flow.

## 12. Compliance & Data Protection `[NEW v3]`
`[HARDENED v3]` Entirely missing from v2.2 — necessary before a global launch touching
minors' personal data, and a genuine competitive point (§13) since most regional coaching-
management tools don't address this at all.
- **Data minimization:** collect only what Modules 1–11 actually use; no field exists "just in
  case."
- **Retention & deletion:** a centre owner can request deletion of a specific student's
  account-linked data (not the anonymized attendance/exam aggregates needed for the
  centre's own records, unless the centre itself also deletes those) — `[ASSUMED v3]`
  retention default of 3 years post-graduation/withdrawal for financial records (typical local
  bookkeeping practice), configurable per centre's own legal obligations.
- **Minors & consent:** for students under 18 (the majority of the user base), the account is
  understood to be under the coaching centre's and parent's oversight by design — the join-
  code model (§8) already routes account creation through staff or a parent-shared code
  rather than an open public signup, which is the practical form "guardian involvement"
  takes here rather than a separate formal consent-capture flow. `[ASSUMED v3]` — flag for
  legal review against India's DPDP Act 2023 (verifiable parental consent provisions) before
  an India launch specifically.
- **Cross-border data residency:** cloud-mode data is hosted per-region (`[ASSUMED v3]`:
  Bangladesh/India data stays in-region) rather than a single global bucket, to reduce
  cross-border transfer complexity as the product expands market by market.

## 13. Competitive Positioning `[NEW v3]`
`[HARDENED v3]` The stated goal of this spec ("win over all the opponents") had no
supporting section in v2.2 — a spec this detailed on mechanics said nothing about why a
centre would pick CoachMate over an existing coaching-management tool. Added as a
reference point for product/sales, not a technical requirement:
- **True offline-first, not "offline mode bolted onto a cloud app":** attendance, payment
  locking, and exam entry are full-featured with zero internet — most regional competitors
  assume connectivity and degrade badly on the frequent power cuts this market actually has.
- **AI that's grounded and teacher-gated, not a generic chatbot wrapper:** every AI output
  a student or parent sees is either cited to the centre's own material or explicitly labeled as
  unverified, and every AI item a teacher publishes passes a review gate — competitors
  bolting on an ungated LLM risk a wrong answer reaching a student with no visible caveat.
- **Free-tier-first AI economics:** built to run meaningfully on a free Gemini key from day
  one, with graceful, transparent degradation under quota pressure — not a per-seat AI
  upcharge that prices out a 400-student centre.
- **Anti-leak content protection:** dynamic watermarking and no-download-by-default
  directly address a real, named pain point (teacher's own notes/past papers leaking) that
  generic LMS-style competitors don't design for at all.
- **Bangladesh/India-native from the ground up:** roll-number scheme built around real
  batch scheduling, bKash/Nagad payment convenience links, Bangla-first UI and templates
  — not an English-first product with translations bolted on.

## 14. Rollout Plan / MVP Phasing `[NEW v3]`
`[HARDENED v3]` An 11-module, deeply "bulletproof" spec is a real launch risk if treated as
one big-bang release — v2.2 had no phasing at all. Recommended split:
- **Phase 1 (pilot-ready, origin client first):** Modules 0–4, 6, 7 core (admission, attendance,
  payment, exams, messaging, sync/backup/RBAC). No AI, no Vault, no student/parent
  accounts yet. Goal: replace the origin client's current workflow completely and prove
  offline-first reliability in the field before adding surface area.
- **Phase 2:** Module 5 (Vault + anti-leak), Module 8 (student/parent accounts + threads).
  Goal: bring students and parents into the loop once the core desk operations are solid.
- **Phase 3:** Module 9 (AI Solve/Teach), Module 10 (multi-tenancy + founder admin),
  Module 11 (parent portal notifications), multi-currency billing (§0). Goal: the differentiated,
  harder-to-build layer, built on a foundation that's already proven itself daily with real data.
- Each phase ships with its own explicit acceptance test pass against this spec before
  moving to the next — not deferred to one "final" test at the end.

---
*End of SPEC.md v3.0. This pass stress-tested v2.2 end-to-end: every `[HARDENED v3]` marker
above is a contradiction, ambiguity, missing edge case, or unaddressed risk that was found and
fixed; every `[ASSUMED v3]` marker is a genuine gap filled with a reasonable default that should
be explicitly confirmed or overridden, not silently trusted. Full list in Appendix A. Everything
carried over unmarked from v2.2 was re-checked and left as-is. Module 8's join/verification/
thread-priority mechanics were locked in v2.1; v2.2's locks (roll bitmask, shared irregularity
threshold, anti-leak override scope, biometric/manual precedence, founder AI-usage metrics)
remain locked in v3.0 and were not reopened.*

## Appendix A — Stress-Test Changelog (v2.2 → v3.0)

| # | Module | Issue found | Fix |
|---|--------|-------------|-----|
| 1 | 0 | Pricing "Growth ৳10–15k" had no rule for which price applies | Split into Growth‑A (501–1000) / Growth‑B (1001–1500) sub-bands |
| 2 | 0 | No handling for >6000 students | Explicit: new Scale negotiation, not auto-extrapolated |
| 3 | 0 | No multi-currency plan for "globally" claim | Flagged BDT-only for Phase 1, currency-per-tenant deferred to Phase 2 |
| 4 | 0 | No enforcement mechanism for non-payment on offline-first installs | Rolling license check + read-only lockout after grace period, data never deleted |
| 5 | 1 | Field "delete" would silently break "history never lost" promise | Archive/soft-delete only |
| 6 | 1 | Roll serial scope was implied, not stated | Explicit: serial increments per (DaySet, TimeCode) pair |
| 7 | 1 | Two different batches could share an identical roll pattern | Auto-suffix disambiguator (`-A`/`-B`) on collision |
| 8 | 1 | Duplicate check risked flagging siblings sharing a parent phone | Scoped duplicate check to student's own phone only |
| 9 | 2 | Device clock drift could mis-flag "late" | Auto-correct <2min drift, flag >2min to owner |
| 10 | 2 | "Like Google Sheets" wasn't an actual spec | Concrete grid UX + concurrency rule spec'd |
| 11 | 2 | "Late" status had no upper bound | Added max-late cutoff → falls back to Absent |
| 12 | 2 | Cross-batch credit wasn't scoped to enrolled batches — proxy loophole | Restricted to batches the student is actually enrolled in |
| 13 | 3 | No status for scholarships/waived fees | Added owner-only "Waived" status, excluded from nags |
| 14 | 3 | Locked payment records were still subject to plain LWW sync | Explicit LWW carve-out, routes to owner conflict log |
| 15 | 3 | White-flag persistence scope was ambiguous across months | Explicit: scoped to that month's box only |
| 16 | 3 | bKash/Nagad link implied auto-reconciliation | Explicit: convenience link only, manual confirmation stays |
| 17 | 4 | 2–3 class result-entry window looked like a hard block | Explicit: soft nudge, "overdue" flag, never blocking |
| 18 | 4 | "Predicts struggling students" had no defined method — open-ended ML risk | Scoped to a transparent, explainable heuristic for MVP |
| 19 | 5 | "No-download" vs "resumable download" read as contradictory | Clarified scope: upload/cache transfer vs. protected-view no-export |
| 20 | 5 | Watermark spec was vague ("session watermark") | Specified dynamic name/roll/timestamp overlay |
| 21 | 5 | Revoked access could persist indefinitely in an offline cache | Added 14-day cache TTL requiring reconnect-revalidate |
| 22 | 6 | No policy for what happens when a cost cap is hit mid-cycle | Bulk sends queue; OTP + core alerts exempt from cap |
| 23 | 7 | No backup/disaster-recovery plan at all for an offline app on unreliable power | WAL mode, local snapshots, off-site backup on sync, full data export |
| 24 | 7 | No local encryption-at-rest for sensitive local data | Added explicit requirement |
| 25 | 7 | No schema-migration strategy across independently-updated installs | Added explicit forward-migration requirement |
| 26 | 8 | 90-day join-code expiry left a long lost/stolen-ID exposure window | Shortened default to 30 days, configurable |
| 27 | 8 | Fallback alphanumeric code had no length/rate-limit spec | 8+ chars, 5 attempts/hour rate limit |
| 28 | 8 | OTP itself could be weaponized as a harassment/bombing vector | Per-identifier and per-IP rate limiting on OTP sends |
| 29 | 8 | OTP length/expiry/attempt limits were unspecified | 6 digits, 10-min expiry, 5 attempts |
| 30 | 8 / 11 | Parent-linking mechanism was never actually defined | Explicit: same join code, distinct parent-role account, owner-revocable |
| 31 | 9.1 | Self-verification doubling every query's cost fought the free-tier goal | Scoped self-verification to written/CQ tier only |
| 32 | 9.1 | No behavior defined for empty-retrieval answers | Explicit "unverified — general knowledge" labeling |
| 33 | 9.1 / 9.3 | No override path for a student legitimately needing more than the daily cap | Added teacher-grantable, time-boxed, audited override |
| 34 | 9.2 | OCR assist gave no accuracy expectation for handwritten Bangla | Added explicit "verify before grading" caveat |
| 35 | 9.3 | Rate-limit queue had no priority order or expiry | Teacher-before-student priority; 24h queue TTL |
| 36 | 10 | Founder's own data-access boundary was never stated | Explicit: metrics only, no PII/content without owner-granted, audited access |
| 37 | 10 | "Suspend" scope against an offline-first tenant was undefined | Explicit: cloud/AI/billing only, cannot touch local data |
| 38 | — | No compliance/data-protection section for a product handling minors' data across two countries | Added §12 |
| 39 | — | No section addressing the spec's own stated goal of competitive differentiation | Added §13 |
| 40 | — | No phasing — 11 modules read as one big-bang release, a real delivery risk | Added §14 MVP phasing anchored on the origin client pilot |
