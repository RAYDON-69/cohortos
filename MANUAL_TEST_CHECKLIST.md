# Manual test checklist (≤15 minutes)

Do this on **your** Linux machine after `git pull` and following `RUN_LOCALLY.md`.  
Check each box only if you saw the result yourself.

## Batch A — trust

1. **Session after full quit**  
   - Sign in with OTP.  
   - Fully quit the app (or stop both terminals if using browser mode).  
   - Start API + frontend again.  
   - Open the desk URL.  
   - **Pass:** You are still signed in (Attendance loads) without a new OTP.  
   - **Fail:** Login screen forces a new OTP.

2. **Session after sleep (optional)**  
   - Sign in, put the laptop to sleep for 2+ minutes, wake, reopen app.  
   - **Pass:** Still signed in.

3. **Blank screens**  
   - From the sidebar open: Attendance, History, Admissions, Fees, Exams, Vault, Settings, AI Copilot.  
   - **Pass:** Every screen shows title + content or a clear empty state (not a pure white page).  
   - If an error panel appears, click **Try again** and **Go home** — both must do something visible.

4. **Exam “KINETICS”**  
   - Open Exams → create an exam named exactly `KINETICS` with today’s date and a batch.  
   - Confirm it appears in the list and you can open/select it.  
   - Enter marks for one student if roster exists.  
   - **Pass:** No “Internal Server Error”; exam stays openable after create.

## Batch B — core

5. **View file (Vault)**  
   - Upload a small PDF or image in Vault.  
   - Click **Open / view file**.  
   - **Pass:** Overlay opens with PDF/image (or a clear download link), not a dead button.

6. **Student profile**  
   - Open Admissions, note a student id, or go to `/students/<id>`.  
   - **Pass:** Profile page with name/overview (not only the flat table).

7. **Batch detail**  
   - Open `/batches/<batch-id>` for a real batch.  
   - **Pass:** Schedule + roster links to students.

## Batch C — polish

8. **Settings groups**  
   - Open Settings.  
   - **Pass:** Sections Account / Centre / Billing / Integrations / Notifications / Support (not one undifferentiated pile only).

9. **Teacher Copilot**  
   - Open **AI Copilot** in the sidebar.  
   - Ask: “How many students?”  
   - **Pass:** Answer appears in the chat. Optional: set Groq key and ask again.

10. **Automations control**  
    - On AI Copilot, click **Run fee reminders now**.  
    - **Pass:** Status line updates without crashing.

---

If anything fails, note the step number and a screenshot in your reply to the builder.
