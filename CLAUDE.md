# CohortOS

Multi-tenant coaching OS (attendance, payments, exams, Vault, AI tutor/co-pilot)
for centres in Bangladesh, India, and globally. Design anchor: physics coaching
in Barishal (~400 students). Global ~/.claude/CLAUDE.md already covers workflow,
git, and safety — this file only adds project-specific rules.

## Source of truth
`SPEC.md` at repo root is the single source of truth. **Do not rely on memory
of it from a previous session.** If something is genuinely missing or ambiguous,
ask, then append the answer under the relevant module in SPEC.md.

Markers: `[FLEX]` = configurable per centre · `[BULLET]` = non-negotiable ·
`[NEW]` = net-new · `[LOCKED]` = decision finalized (do not re-litigate).

## Locked decisions (v2.2) — treat as final
- **Module 1 roll encoding:** 3-digit day bitmask + 2-digit hour + 3-digit serial
  (e.g. Sat+Mon+Wed 14:00 serial 33 → `02114033`). Plain serial still available.
- **Module 2/3 irregularity threshold:** one shared setting (default <3 days
  attended that month). Below it → stop automated absence *and* payment nags;
  one consolidated teacher alert instead.
- **Module 2 biometric/manual:** biometric is authoritative; manual only fills
  gaps and never silently overwrites a biometric punch. Disagreements → review
  queue (same as anti-proxy).
- **Module 5 anti-leak:** centre-wide default is owner-only protection. Teacher/
  assistant may relax per-resource (audit-logged, visibly labeled). Desk has no
  anti-leak controls.
- **Module 8 join:** per-admission join code (QR + short alphanumeric, single-use,
  long expiry) is primary; staff-manual linking is the fallback. Both call the
  same `link(admission_id, cohortos_account_id)`. No upfront email/SMS verify
  at signup — an unlinked account has zero access. Passwordless OTP via existing
  NotificationService.
- **Module 8.4 thread priority:** reuses the Module 9.2 confidence × cohort-
  severity ranking engine. No separate triage system.
- **Module 10 founder dashboard:** no Gemini-spend visibility (tenants bring
  their own keys). Track query volume, 429 rate, cache hit rate, MCQ-vs-written
  split instead.

## Domain skills (preloaded into agents — do not invoke standalone)
- offline-sync-conflict-resolution
- multi-tenant-rbac
- ai-grounding-pipeline
- financial-audit-integrity
- cohortos-invariants (ultra-short bulletproof checklist)

architect-planner, security-auditor, and code-reviewer already carry the ones
they need. See `.claude/agents/`.

## Stack (fill as decided — do not assume)
- Desktop app framework:
- Web/mobile framework:
- Local DB (offline-first): SQLite
- Hosted DB (cloud-first mode):
- Biometric: `pyzk` → ZKTeco K60 / compatible
- AI: Google Gemini free-tier (Google AI Studio key) default; BYOK optional
- Test / lint / build: `<fill once stack chosen>`

## Conventions
- Never print or log a centre’s AI system-prompt content. Changes go through
  the CohortOS team (Module 1).
- Core actions (attendance, payment lock, exam entry, content access) must
  work with zero internet. Making any of them network-dependent is a `[BULLET]`
  regression — flag loudly.
- Payment amounts are optional (default = paid/unpaid per month only).

## Do not touch
- Locked payment records except via explicit owner-unlock (itself audit-logged).
- Default roll-encoding scheme (kept for origin-client backward compatibility).

## Token discipline
- Prefer `/spec-sync` (lightweight) over pasting or re-reading the full SPEC.
- Delegate broad search/research to subagents so the main thread stays lean.
- When a task is done, prefer a short verified summary over a long narrative.
