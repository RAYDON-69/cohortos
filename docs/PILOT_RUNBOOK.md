# CohortOS Pilot Runbook

## Teacher quickstart (English)

1. Install / open CohortOS desk app.
2. Sign in with phone OTP.
3. **Load demo** (Settings → Demo) for a 5-minute walkthrough, or start empty.
4. Create a batch → add students → mark today’s attendance.
5. Record a fee payment or due.
6. Classes: prefer **Broadcast** (paste YouTube/FB Live link) for large batches; use Interactive Jitsi only for small doubt sessions.
7. After class: attach recording link (HTTPS YouTube/Drive) → notify absentees.
8. Call Desk: work the queue with **human-placed** calls only (tel:/WhatsApp); log outcome.
9. Backup: one-click encrypted backup before large imports.
10. Remove demo data before using a real centre.

## শিক্ষক দ্রুত শুরু (বাংলা)

1. অ্যাপ খুলে ফোন OTP দিয়ে লগইন করুন।
2. ডেমো লোড করে দেখুন, অথবা খালি কেন্দ্রে শুরু করুন।
3. ব্যাচ তৈরি → শিক্ষার্থী যোগ → উপস্থিতি দিন।
4. ফি আদায়/বকেয়া এন্ট্রি করুন।
5. ক্লাস: বড় ব্যাচে **Broadcast** লিংক; ছোট সেশনে Interactive।
6. ক্লাস শেষে রেকর্ডিং লিংক দিন, অনুপস্থিতদের নোটিশ পাঠান।
7. Call Desk থেকে নিজে কল করুন — অটোডায়াল নেই।
8. ব্যাকআপ নিন। ডেমো ডেটা মুছে ফেলুন।

## 10-step on-device test

Devices: (A) ~4GB laptop LITE, (B) Android phone, (C) ≥16GB laptop FULL.

1. Cold start app on A — note time to login screen.  
2. Login OTP on A.  
3. Load demo; confirm Bangla names visible.  
4. Attendance mark present/absent.  
5. Create broadcast class with YouTube link; open student join on B.  
6. On C: interactive/Jitsi join if configured; else skip and note.  
7. Whiteboard: visible on C FULL, hidden reason on A LITE.  
8. Call Desk: script + log “no answer”.  
9. Backup → remove demo → confirm demo gone.  
10. Airplane mode: offline banner, no crash.

**Live media quality = UNVERIFIED in CI.**

## When it breaks

| Symptom | Try |
|---------|-----|
| Blank page / Session required | Sign out, clear site data, login again |
| Missing bearer token | Re-login; check system clock |
| Class join 404 | Recreate session; update app (id fix) |
| meet.jit.si blocked | Set self-host URL + fallback |
| App freeze on 4GB | Stay on LITE; disable local model |

## Feedback (CSV template)

```csv
date,device_ram_gb,os,feature,what_happened,severity_1_to_5,contact
2026-10-01,4,Windows11,attendance,"example",3,teacher@example.com
```

## Self-host Jitsi (one command)

```bash
# After cloning upstream docker-jitsi-meet and copying deploy/jitsi/.env.example:
./deploy/jitsi/verify.sh https://meet.yourcentre.example
```

Checks: HTTP reachability. JWT rejection and TLS must be validated manually on the VPS (document results in pilot notes). Live-media quality remains **UNVERIFIED**.
