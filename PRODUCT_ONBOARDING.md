# CohortOS — How users get in (no terminal, no tenant ID)

## Centre owner (new)

1. Open the web app or desktop app.
2. Choose **Start free trial**.
3. Enter centre name + phone (name/email optional).
4. Receive a 6-digit code → enter it → desk opens.
5. Trial lasts **14 days**. Founder sees the centre in Control.

You never type a Tenant ID.

## Staff (returning)

1. **Sign in** with phone only.
2. If the phone is on one centre → code is sent.
3. If the phone is on several centres → pick the centre → code is sent.
4. Enter the 6-digit code.

## Students

Added **manually** by the centre (Admissions). Parent/student app join via QR/code is Phase 2.

## Founder (you only)

- Set `COHORTOS_FOUNDER_TOKEN` on the server.
- Use founder API/UI with that token.
- Clients never receive this token or the source zip.

## What clients receive later

- Web URL and/or Windows / Linux installers — **not** this development zip.
