# CohortOS Threat Model (draft)

## Assets
- Student PII (names, phones, guardians) — children's data
- Attendance, payments, exam scores — integrity + confidentiality
- Staff auth tokens / OTP — session security
- AI keys and local model files — credential + disk confidentiality

## Trust boundaries
1. Browser/Electron renderer ↔ local FastAPI (localhost)
2. Centre tenant A ↔ tenant B (must not leak)
3. Local desk ↔ cloud LLM providers (opt-in only)
4. Local desk ↔ SMS / payment providers

## Threats & mitigations
| Threat | Mitigation |
|--------|------------|
| Stolen laptop / shared PC | Future: DB encryption-at-rest; session expiry; delete-local-model |
| Prompt injection via vault text | Tools only from user question; writes need confirm + role; tests |
| Cloud LLM data exfil | `cloud_llm_enabled` default OFF; PII redaction when ON |
| SMS pumping | OTP rate limits |
| Dependency compromise | pip-audit, npm audit, Dependabot, CodeQL, gitleaks |
| Electron XSS → RCE | contextIsolation, no nodeIntegration, sandbox, CSP |

## Residual risks (accepted for P23)
- Local GGUF download integrity depends on pinned SHA when configured
- Unsigned installers until code-signing certs acquired
