# CohortOS licence model (P36)

## Goals
Stop casual multi-centre misuse of a single paid licence. Not DRM against a determined attacker on an offline desktop.

## Token
- Ed25519 signed payload: `tenant_id`, `plan`, `exp`, `seats`, `issued_at`
- Public key embedded in the app; **private key stays on the licence server / founder tooling only**
- Offline grace: 7 days after `exp` still writable; then **read-only** (view, export, backup). Data is never deleted on lapse.
- Tamper: bad signature → reject
- Clock rollback: high-water mark file; >24h backward → re-verify required

## Revocation
Revocation requires online check-in (optional future). Until then, short `exp` + renewal is the control.

## Key management
- Generate with `services.licence_service.generate_keypair`
- Store private key in founder HSM/password manager — never in git
- Rotate by issuing new tokens; old tokens valid until exp

## Limits (honest)
Electron/Python desktop can be patched to skip checks. Mitigation: server-side feature flags for cloud features; licence mainly gates local commercial conscience + support eligibility.
