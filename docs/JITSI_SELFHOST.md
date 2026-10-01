# Jitsi self-host for CohortOS (recommended production)

**Public `meet.jit.si` ignores CohortOS JWTs** — rooms are effectively open if a link leaks.
Label in UI: **OPEN-ROOM, not access-controlled**. For production, self-host.

## Cheap VPS (approx.)
- 2 vCPU / 4GB RAM minimum for small batches; 8GB better
- Ubuntu 22.04+, ports 80/443/10000/UDP open

## Steps
1. `git clone https://github.com/jitsi/docker-jitsi-meet` and follow upstream README.
2. Copy `deploy/jitsi/.env.example` values into that project's `.env` (`ENABLE_AUTH=1`, `AUTH_TYPE=jwt`, shared `JWT_APP_SECRET`).
3. Set CohortOS env:
   - `COHORTOS_JITSI_BASE_URL=https://meet.yourcentre.example`
   - `COHORTOS_JITSI_JWT_SECRET=<same as JWT_APP_SECRET>`
   - Optional `COHORTOS_JITSI_FALLBACK_URL` if primary blocked by school networks.
4. TLS via Caddy or Let's Encrypt (sample `deploy/jitsi/Caddyfile`).
5. Run `deploy/jitsi/verify.sh https://meet.yourcentre.example`.

## Health / fallback
API join responses include `access_mode` (`JWT` vs `OPEN-ROOM`) and may use fallback base URL when configured.

## Recording (honest status)

**Automated Jibri recording is NOT-DONE.** CohortOS supports the manual path only:
1. Teacher ends class
2. Pastes HTTPS YouTube-unlisted / Drive / Vimeo link
3. App validates host allow-list and stores `recording_url`
4. Absentees can be notified via existing notify-absentees API

To add Jibri later: run jibri alongside docker-jitsi-meet, configure XMPP, and wire a webhook into `set_recording_url`. Treat as a separate ops project.
