# CohortOS cost model (honest, short)

Servers hold **data and relay only** — no GPU, no media SFU bill at the CohortOS layer when centres use **BROADCAST** mode.

| Line item | Who pays | PROVEN / ASSUMED |
|-----------|----------|------------------|
| Desk SQLite + API on centre PC | Centre (electricity) | PROVEN path (offline-first) |
| Optional cloud API host (small VPS) | Operator | ASSUMED ~$5–12/mo shared |
| **BROADCAST** class (YouTube/FB/Zoom link) | Teacher’s free tier / existing sub | PROVEN architecture (no our media) |
| **INTERACTIVE** self-hosted Jitsi | Centre/operator VPS 4–8GB | ASSUMED ~$8–20/mo if dedicated |
| meet.jit.si public | Free, OPEN-ROOM | PROVEN link path; not access-controlled |
| SMS (BTRC aggregator) | Centre prepaid | ASSUMED; not live in P26 |
| Cloud LLM keys | Centre BYO | PROVEN opt-in; default OFF |
| Local GGUF model | Centre disk/RAM | PROVEN optional download |
| Vault files | Local disk / user Drive | PROVEN local storage |

## Estimate per centre / month

| Mode | Infra (operator) | Media | Notes |
|------|------------------|-------|-------|
| BROADCAST-only | ~$0–5 (shared API) | $0 to us | Scales to hundreds of viewers on weak networks |
| INTERACTIVE self-host Jitsi | ~$10–20 VPS | $0 SFU SaaS | Small batches / doubt-clearing |
| INTERACTIVE public meet.jit.si | ~$0 | $0 | OK for pilots only (OPEN-ROOM) |

**Founder rule:** default new sessions to **BROADCAST**; use INTERACTIVE only when the teacher needs two-way AV for a small group.
