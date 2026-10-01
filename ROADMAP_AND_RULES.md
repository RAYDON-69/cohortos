# CohortOS — Standing Rules + Roadmap
Owner: Claude (planning/verification). Read this file in full at the start of EVERY round, before SPEC_v3.md and BUILD_LOG.md.

## 0. Standing rules (non-negotiable)
1. **Plan first.** Quote real constraints/logs, state decisions and rejected alternatives, THEN code.
2. **Test-first.** Write each item's acceptance test before the implementation. The test must be able to fail — say how you know.
3. **Evidence standard.** PROVEN = a CI run on main passing an assertion that covers the item. Otherwise UNVERIFIED (exact blocker) or NOT-DONE (reason). A stub is never a feature.
4. **Remix, don't reinvent.** Prefer maintained open-source libraries. For each new dependency record name, version, license in `docs/LICENSES.md`. Only MIT/Apache-2.0/BSD/ISC unless flagged. Custom code needs a stated reason.
5. **Independent verification.** Claude merges, dispatches E2E Smoke twice, and reports. Never self-merge. Never claim "green" for a run you did not see.
6. **One branch per round**, pushed before you stop. If the session ends early, push partial work and list exactly what remains.
7. Never weaken or skip a test to get green. Never commit secrets.
8. **Finish with a punch-list:** PROVEN / UNVERIFIED / NOT-DONE + recommendation for next round.
9. **Self-audit before finishing:** list 10 ways this round could still fail on a 4GB Windows laptop with power cuts and Bangla input; test the top 5.
10. **Use the whole session — enforced, not a suggestion.** Attempt every workstream listed in the prompt; a workstream with zero commits and zero tests is a failure for that workstream, not an acceptable scope cut. If you find yourself wanting to stop, that is the signal to pick the next UNVERIFIED or NOT-DONE item and keep going. Only stop when every workstream has at least one real commit and one real test, or you've hit a genuine technical wall — and if so, name that wall precisely in the punch-list, don't just go quiet.

## 1. Product constraints
- Offline-first. Must run on low-end PCs (4GB RAM target). Heavy features (local LLM) are OFF by default on low-RAM machines.
- BD phone format 01XXXXXXXXX; BDT default currency.
- Student data is children's data: least privilege, consent, no ads, no data sales, delete on request.
- Agentic writes are never silent: confirm, log, role-check.

## 2. Roadmap (sequence)
**Phase gate (confirmed by Raiyan, 2026-09-29): nothing past P25 starts until the coaching-centre desktop app — including the voice agent and class workspace — is fully done.** Do not open work on P26+ items early even if a round finishes ahead of schedule; use spare time to close out UNVERIFIED items in P23–P25 instead.
- **P23** [done, E2E-verified] Local-LLM safety + proof; agent safety; automation depth; CSV/Excel student importer; security CI; threat model + legal drafts.
- **P24** Voice agent for the centre's own call staff (outbound reminder/follow-up calls to students/parents — this is currently done by a dedicated human caller). Remix a real open-source voice-agent stack: a telephony provider's streaming call API + an STT/TTS pipeline, routed through the existing local/cloud LLM abstraction from §3 — don't hand-roll audio/signal handling. **Hard gate: assisted mode only (agent drafts a script / summarizes the call for a human to place) until BTRC's automated-call and DND rules are confirmed (§5); no auto-dial capability ships before that.**
- **P25** Online class workspace, replacing the centre's current Zoom+Telegram setup. Integrate one existing self-hostable video/conferencing project — Jitsi Meet, LiveKit, or BigBlueButton — with a stated reason for the pick, plus a lightweight class chat/notice layer. Do not build a WebRTC stack from scratch.
- **P26** Public website (static; Bangla+English; Home, Features, Pricing, About, Support, Legal) from an existing open-source landing template; in-app onboarding tour + Help; demo-video script.
- **P27** Student/parent surface: PWA first (installable on Android, no store), Capacitor APK only if needed. Attendance, dues + pay, results, notices, AI Tutor (backend exists), notification centre.
- **P28** Messaging: real SMS via a BTRC-licensed BD aggregator (sender-ID/masking registration), Bangla templates, delivery reports, cost meter. WhatsApp Business later.
- **P29** Live payments: bKash + Nagad + international rail (see Legal) after merchant onboarding. Webhook signature verification, idempotent confirm, reconciliation report, refunds, PDF invoices, VAT lines.
- **P30** Founder panel: tenant list, plan/license control, usage + cost caps, support inbox, feature flags / regional packs, release channel + signed auto-update, opt-in crash reporting.
- **P31** Hardening: OWASP ASVS L1/L2 pass, backup/restore drill, multi-desk sync-conflict UX, SQLite→Postgres path for large centres, low-end-PC performance budget (startup, RSS), accessibility.
- **Later:** regional packs beyond Bangladesh.

## 3. Local model policy (decided)
- Detect total AND free RAM (psutil). Total <5GB (a "4GB device"): OFF, hidden under Advanced, red caution ("may freeze this computer; use a cloud key instead"). 5–<8GB: OFF by default, opt-in with caution. ≥8GB: offer enable.
- Never download silently: show size (~1GB), require explicit consent, warn about mobile data, check disk space, resumable, cancelable, pinned model revision + SHA-256, delete-model button.
- Refuse to load if free RAM < model + context + 1GB. Run inference isolated (subprocess/sidecar) with timeout and kill switch so the app never freezes.
- Model choice is provisional until (a) license review and (b) Bangla eval. LFM2.5 ships under the "lfm1.0" license (not Apache) — read commercial/revenue terms; Qwen2.5-1.5B(-FC) is Apache-2.0 and cleaner for acquirer due diligence.

## 4. Security (before the first paying centre)
- CI: gitleaks (secrets), pip-audit + npm audit (fail on high), CodeQL, Dependabot. Prefer console output over artifacts (Actions artifact quota).
- Electron hardening: contextIsolation, sandbox, no nodeIntegration, strict CSP, validated IPC, block unexpected navigation, signed updates.
- Installers: code-signing (Windows cert, Apple notarization) — unsigned installers trigger SmartScreen/Gatekeeper warnings and kill trust.
- Data: decide encryption-at-rest for the local DB (student PII on shared PCs); encrypted backups; immutable audit log for payments/attendance/grades.
- Auth: OTP rate limits + lockout; guard against SMS-pumping fraud; tenant-isolation tests stay in CI.
- LLM-specific: prompt-injection tests (vault text must never trigger tools); per-tenant toggle for sending data to cloud LLMs, default OFF, PII redaction when ON; API keys encrypted at rest.
- Housekeeping: rotate any key/token that appeared in chat logs; use fine-grained, repo-scoped, expiring GitHub tokens.

## 5. Legal (Bangladesh — NOT legal advice; verify with a Bangladeshi lawyer and accountant)
- **Data protection:** the Personal Data Protection Act, 2026 (Law 63 of 2026) replaced the 2025 ordinance in April 2026 and applies to entities serving people in Bangladesh. The Feb-2026 amendment added in-country copy rules for restricted data / critical infrastructure — confirm it does not touch you. Students are mostly minors: confirm parental-consent and children's-data rules.
- **Roles:** each centre is the data controller, CohortOS the processor → Data Processing Agreement per centre. Also: Privacy Policy, Terms of Service, breach-response procedure, retention/deletion policy (export/delete tools already exist).
- **Cyber law:** the Cyber Security Act 2023 was repealed by the Cyber Security Ordinance 2025 (May 2025); re-check current status before finalizing ToS liability/moderation clauses.
- **Company & tax:** register the entity (RJSC / trade licence), TIN, VAT/BIN as applicable, business bank account, invoices with VAT lines.
- **IP hygiene (matters for exit):** written IP-assignment from every contributor; open-source license inventory (docs/LICENSES.md); model licenses (see §3). Acquirers audit all of this.
- **Payments:** bKash/Nagad merchant onboarding needs trade licence, NID, TIN, BD bank. Stripe does not (to my knowledge) support Bangladesh-registered businesses directly — verify the current supported-countries list; options are a foreign entity (e.g. Stripe Atlas) or a merchant-of-record (Paddle / Lemon Squeezy).
- **Messaging/voice:** BTRC rules on bulk SMS, masking sender IDs, and automated calls/DND — verify before P26 and before any AI voice outreach.

## 6. Go-to-market (Raiyan's weak spot — be direct)
- **Wedge:** fee collection + attendance→parent SMS. "Works during power cuts, in Bangla." Sell the outcome (dues collected, hours saved), not features.
- **ICP:** district-town coaching centres with 100–500 students and 2–10 teachers — less contested than Dhaka.
- **Pilots:** 4 known teachers → 3 PAID pilots (even a token fee; free pilots validate nothing), 30-day success metrics (collection rate, hours saved, SMS delivered), written testimonial + short Bangla video case study.
- **Friction to remove:** migration. Excel/CSV importer + "we import your student list" as a paid setup service.
- **Channels:** in-person demos in district towns, coaching-owner Facebook/WhatsApp groups, Bangla YouTube/Facebook shorts, local coaching associations, 5% affiliate (in writing).
- **Sanity-check pricing:** $100K ARR from 50 centres implies ~$167/centre/month (~20,000 BDT) — far above typical district-centre software spend. Either justify ARPA (SMS credits, AI, onboarding, multi-campus) or target 100–300 centres. Model this before quoting valuations.
- **International outreach:** treat as a separate later product bet; don't let it dilute the Bangladesh wedge. "$300K ARR from 3–5 teachers" is not a realistic model — needs schools/platform partnerships.
- **Metrics that build an exit story:** paid centres, weekly active centres, fee volume processed through the app, retention, support load.


## E2E gate policy (P26c)
- **CORE** (`frontend/e2e/smoke.spec.ts`): required. Must stay green on every main push.
- **EXTENDED** (`frontend/e2e/smoke-extended.spec.ts`): **required** (continue-on-error removed after 3 green runs on main). Every run publishes `ci-reports/e2e-<run_id>-<attempt>.json` with `core_outcome`, `extended_outcome`, and `main_sha`.
- Every run publishes `ci-reports/e2e-<run_id>-<attempt>.json` with `core_outcome` and `extended_outcome` from `steps.<id>.outcome` (definitive JSON signal).
