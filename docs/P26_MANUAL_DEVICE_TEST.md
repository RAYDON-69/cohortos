# P26 Manual media test (10 steps) — run on 3 devices

Devices: (A) ~4GB laptop, (B) Android phone, (C) ≥16GB laptop.

1. Deploy/start CohortOS desk API + frontend; set `COHORTOS_JITSI_BASE_URL` (self-host preferred).
2. Create a batch and a class session from `/classes`.
3. On device C (FULL): Teacher join — confirm camera/mic permission prompt and grid.
4. On device B: open student join link (`/join/...&token=`) — one-tap Bangla button opens room.
5. On device A (LITE): confirm UI shows lite reason (360p / audio-first); whiteboard disabled if tier API applied.
6. Raise hand + post a poll from teacher; student votes (if UI wired) or via API.
7. Paste a YouTube-unlisted recording URL on the session; end session.
8. Notify absentees; confirm Call Desk shows a card; place a **manual** tel: call; log outcome with human_action_id.
9. Kill network mid-session (airplane mode) — app should not crash; offline banner acceptable.
10. Confirm public meet.jit.si mode shows OPEN-ROOM warning; self-host JWT mode does not.

Live A/V quality and Jibri recording = **UNVERIFIED** in CI.
