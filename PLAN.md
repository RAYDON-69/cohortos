# PHASE 7 PLAN — plan + stress-test-on-paper before code

Committed before implementation. Evidence rule unchanged from Phase 6.

---

## Stage 0 — Foundation

No MANUAL_TEST_CHECKLIST results from Raiyan in this session.
**ASSUMED-BROKEN-PENDING-CONFIRMATION** (from Phase 6):
- Session after full Electron quit / OS sleep
- FileViewer overlay, Student Profile, Batch Detail, Settings IA, Teacher Copilot chat UI
- GUI blank-screen recovery

What we can fix without device: automation engine persistence, LLM providers, tutor API isolation tests, viewer code paths, design tokens.

---

## Workstream A — Configurable Automation Engine

### Build
Trigger → condition → action rules stored as JSON in ConfigService (`automations.rules`).
API: list/create/update/enable/disable/run-one. UI: Automations screen under Settings.
Extend `AutomationService` + `scripts/run_automations.py` to evaluate rules, not only hardcoded fee/nag.

### Repo candidates
| Candidate | License | Maturity | Fit | Footprint |
|-----------|---------|----------|-----|-----------|
| **durable-rules** | MIT | Mature | Full RETE engine | Heavy / native-ish; overkill |
| **business-rules** (python) | MIT | Medium | JSON rules | Extra dep, limited maintenance |
| **Custom JSON matcher** on existing AutomationService | n/a | Owned | Exact fit for 5–20 rules/centre | Zero new deps |

**Pick: Custom JSON matcher** — 1.2GB sandbox, offline desk, few rules per centre. Schema:

```json
{
  "id": "uuid",
  "name": "Fee overdue 7d",
  "enabled": true,
  "trigger": {"type": "schedule|event", "cron": "0 9 * * *", "event": "payment_overdue|student_added|manual"},
  "conditions": [{"field": "days_overdue", "op": ">", "value": 7}, {"field": "batch_id", "op": "eq", "value": "..."}],
  "actions": [{"type": "fee_reminder|tag_student|notify_staff", "params": {}}]
}
```

### Stress-test on paper
- Double fire same rule → idempotent action log key `(rule_id, subject_id, day)` skips duplicate send.
- Student deleted mid-run → skip missing ids, no crash.
- Missing payment data → empty candidate list, log warning.
- Scale: O(rules × students_month); fine for coaching centre sizes (<5k students).

---

## Workstream B — AI Teacher Copilot (automation + action log)

### Build
Extend `/ai/query` tools: `list_automations`, `run_automation(name|id)`.
TeacherCopilot UI: action log panel fed by `GET /t/{id}/automations/log`.
Chat phrase “run fee reminders” maps to tool call.

### Repo candidates
| Candidate | Why not / why |
|-----------|----------------|
| LangChain agents | Too heavy, many deps |
| Existing tool_trace in `/ai/query` | Already present — extend |

**Pick: extend existing tool-calling** in `api/main.py`.

### Stress-test on paper
- Invalid automation name → tool error in log, no 500.
- Run while disabled → rejected with message.
- Concurrent chat + manual run → both append log, no corruption (append-only list / SQLite).

---

## Workstream C — AI Tutor (student-facing, Vault-grounded)

### Build
`POST /t/{tenant}/tutor/query` with `student_id`, `batch_id`, `question`.
Uses existing `RetrievalService` filtered by `batch_id` + tenant; answer includes `citations: [{resource_id, title, excerpt}]`.
Student UI screen `/student/tutor`.

### Repo candidates
| Candidate | License | Footprint | Fit |
|-----------|---------|-----------|-----|
| **chromadb / sqlite-vec** | Apache | Embeddings + vector DB | Heavy for desk; needs embedding API cost |
| **llama-index** | MIT | Full RAG stack | Too large |
| **Existing RetrievalService (keyword)** | Owned | Zero new deps | Offline-first, already tenant-scoped |

**Pick: RetrievalService keyword retrieval** (already in tree). Optional future: `sqlite-vss` when RAM allows. Footprint: in-process, no model download.

### Stress-test on paper
- Cross-batch: resource with other batch_ids only → empty chunks, refuse ungrounded answer.
- Cross-tenant: wrong tenant token → 401/403 (existing pattern).
- No vault docs → explicit “no sources in your batch vault”.
- Adversarial test: student A batch1 must not see batch2 titles.

---

## Workstream D — BYO official providers

### Build
Add `OpenAIProvider`, `AnthropicProvider`, `GeminiAPIProvider` (Google AI Studio key, not consumer session) to `llm_provider.py`.
Settings: clear copy + links to console.openai.com, console.anthropic.com, aistudio.google.com.
Router config: `ai_keys.routes = {copilot, tutor, automation}` → provider names; default **groq**.

### Not allowed
Browser session / consumer ChatGPT Plus login as API backend (ToS + fragile).

### Stress-test on paper
- Missing key → OfflineError, UI shows configure message.
- 401 revoked → graceful error in tool_trace.
- Rate/cost: reuse RateLimiter on `/ai/query` and `/tutor/query` (existing 429).

---

## Workstream E — Design pass (Phase 7d completion)

### Candidates considered
| System | License | Maturity | Fit for CohortOS desk |
|--------|---------|----------|------------------------|
| **Open Props** (open-props.style) | MIT | Active | Token-first utilities; would duplicate SPEC design-system.html cream/sage palette |
| **Pico CSS** | MIT | Active | Classless polish; fights AppShell/sidebar density and custom status badges |
| **Radix Themes / shadcn** | MIT | Active | Needs Tailwind + large dependency surface for offline Electron |
| **CohortOS design-system tokens** (existing `tokens.css` from design-system.html §2) | Project | Spec-aligned | Already gates hex via `npm run audit:tokens`; cream/sage/peri palette; offline-friendly zero new deps |

**Pick: CohortOS design-system tokens (deepened)** — not a third-party kit. Open Props / Pico were rejected to avoid palette drift from SPEC and extra CSS payload. Phase 7d applies the system **globally**: expanded layout/type utilities on `:root`, unified `.view` / tables / forms / chat, Card radius→token, FormField border→`--border-strong`, fixed residual hex in GlobalSearch, ErrorBoundary, FileViewer, TeacherCopilot.

### Stress-test on paper
- Token audit fails if any hex sneaks in → `npm run audit:tokens` / frontend-ci.
- Mobile ≤760px: `.view` padding and title scale down without breaking AppShell strip.

## Workstream F — Players

### Candidates
| Lib | License | Use |
|-----|---------|-----|
| **pdfjs-dist** | Apache-2.0 | PDF page nav/zoom |
| **react-pdf** | MIT | wrapper on pdfjs |
| **video.js** | Apache-2.0 | A/V heavy |
| **Native `<video>`/`<audio>` + controls** | n/a | Already partial |

**Pick: pdfjs-dist** for PDF (dynamic import to avoid blocking main). Keep enhanced native media with seek + playbackRate (no video.js weight). package.json adds `pdfjs-dist`.

### Stress-test on paper
- >25MB → reject before load (match Vault).
- Corrupt PDF → catch pdfjs error, show “cannot open”.
- Missing content endpoint → clear error, no white screen.

---

## Implementation order
A → D (providers needed by B/C) → C → B → F → E polish.


## Phase 8 — Design override, viewers, RAG harness

### Workstream A — Design system (reopened)

| Candidate | License | Runtime weight | Fit |
|-----------|---------|----------------|-----|
| In-house tokens only (7d) | Project | 0 | Unsatisfying login/spacing/animation (founder feedback) |
| **shadcn/ui + Tailwind + Radix** | MIT | **0 runtime CSS** (build-time purge) | Industry SaaS baseline; form/dialog/dropdown primitives |
| MUI | MIT | Large runtime JS | Too heavy for desk |

**Pick: shadcn/ui pattern + Tailwind v4 + Framer Motion (MIT).**  
Prior “Tailwind is heavy for Electron” was wrong: Tailwind emits static CSS at build time. Framer Motion chosen over pure CSS for login/page transitions with spring physics; ~30KB gzipped is acceptable vs unsatisfying static UI.

### Workstream B — Viewers
- **pdfjs-dist** (Apache-2.0): page nav, zoom, text search in FileViewer
- **Image lightbox**: zoom/pan overlay (no new dep)
- **Plyr** (MIT): video/audio seek, speed, volume — single entry `FileViewer`

### Workstream C — RAG

| Option | License | Offline / RAM | Notes |
|--------|---------|---------------|-------|
| ChromaDB | Apache | Heavy process | Rejected for desk |
| LanceDB | Apache | Embeddable | Needs embedding vectors + pip native |
| **sqlite-vec** | MIT | SQLite extension | Best long-term; native load varies by OS |
| **Chunked BM25 index (pure Python)** | MIT pattern | Zero native deps | **Pick for v1** — scales to 20+ long docs via paragraph chunking + BM25; no embedding API cost offline |

Embeddings/sqlite-vec flagged as Phase 9 upgrade when centres accept online embed or ship native `.so`.

**DeepSeek:** OpenAI-compatible `https://api.deepseek.com`, models `deepseek-chat` / `deepseek-chat` flash tier; default cheap route with Groq.



## Phase 9 — Ultimate enforcement

### Design references (feel targets)
1. **Linear** — dense desk, fast motion, muted borders
2. **Notion** — calm surfaces, soft page enter
3. **Claude.ai** — inviting auth, clear hierarchy on login

### Embedding decision
| Approach | Verdict |
|----------|---------|
| Chroma / LanceDB server | Rejected — process/weight |
| sqlite-vec native | Rejected this round — OS-specific `.so` shipping |
| onnx MiniLM download | Attractive; **NOT-DONE** without reliable model cache in pilot offline path |
| **Hashing word+char-trigram vectors + numpy cosine + synonym expand + BM25 hybrid** | **DONE this round** — no GPU, no native ext; proven with paraphrase query |

Honest limit: not full neural semantic parity with BGE/MiniLM. Neural local model remains **NOT-DONE** (blocker: offline model download + size for desk installers). Hybrid still required to pass paraphrase test without keyword overlap.



## Phase 11 — Commercial layer (research + data model + usage meter)

### Marketing site decision
**Repo check:** No standalone marketing/landing site (no `landing/`, `www/`, or public unauthenticated About/Pricing routes). Existing surfaces:
- In-app `SupportLegal` (`/support`) — thin placeholders
- Founder `Pricing` (`/founder/pricing`) — internal tier quote tool for operators, not public pricing

**Decision for Raiyan (not built this round):** Whether to add a separate public marketing site (cohortos.app) vs deepening in-app Support/About. Building a full marketing site silently is out of scope.

### Competitor IA research (About / Support / Pricing content)

| Product | About | Pricing model | Support surface |
|---------|-------|---------------|-----------------|
| **Teachmint** | Coaching/school ERP pitch | Free + ~$5–50/user/yr tiers | In-app + help centre |
| **ClassDojo** | Parent engagement story | Free classroom + paid family/school | Help + school sales |
| **PowerSchool** | District SIS | Sales-led custom only | Enterprise support |
| **DreamClass** | Small school SIS | Clear monthly tiers (~€99+) | Docs + contact |
| **Google Classroom** | Free core | Workspace add-ons | Google help |

**Recommended CohortOS IA (in-app for now):**
1. **About** — offline-first desk for coaching centres; version; what we do / don't do
2. **Support** — email, pilot channel, common fixes (RUN_LOCALLY link for self-host)
3. **Pricing (public later)** — Starter / Growth / Scale by student seats + optional AI usage line; annual discount; not buried under founder-only
4. **Legal** — Terms + Privacy placeholders until counsel signs off

### Payment processors (NO live integration this round)

#### Bangladesh (centre owners / parents)

| Option | Coverage | Typical merchant fee | Integration complexity | Notes |
|--------|----------|----------------------|------------------------|-------|
| **bKash PGW** | Highest adoption (~70M+) | ~1.5–2% | Medium — OAuth token → create → execute → query; sandbox | Must-have for BD |
| **Nagad Merchant** | Strong #2 | ~1.2–1.8% | Medium — keys + callback | Pair with bKash |
| **SSLCommerz / ShurjoPay / AamarPay** | Aggregator (MFS + cards) | ~1.5–2.5% + platform | Medium — one API, many rails | Faster multi-rail |
| **Rocket (DBBL)** | Smaller share | Varies | Medium | Optional third MFS |

**Recommendation:** Start with **bKash + Nagad** (direct or via one aggregator). Raiyan must choose before any live keys.

#### International (affiliate teachers / foreign centres)

| Option | Fees (indicative) | Complexity | Notes |
|--------|-------------------|------------|-------|
| **Stripe Billing** | ~2.9% + $0.30 (US cards); local rates vary | Low–medium — best docs | Standard for SaaS subscriptions |
| **Stripe Connect** | Processing + optional $2/active account + payout fees | Higher | If paying out teachers/affiliates |
| **PayPal** | ~3.49% + fixed | Low | Weaker for recurring SaaS |

**Recommendation:** **Stripe Billing** for international subscriptions; Connect only if platform pays out affiliates.

### Safe to build now (this phase)
- Billing data model: plans, subscriptions, seat counts, AI usage line items, invoices
- Settings → **Usage** meter (AI calls this period per provider)
- **Not** live payment capture until Raiyan picks providers



## Phase 12 — Payment provider wiring (sandbox)

Chosen rails: **bKash + Nagad** (BD), **Stripe** (international).
Implementation: `services/payment_providers/{bkash,nagad,stripe_provider}.py` + factory.
Without credentials, providers return **mock sandbox** sessions so CI can prove checkout→confirm→subscription active.
With credentials, HTTP paths call real sandbox APIs (bKash tokenized checkout, Stripe Checkout Sessions).
