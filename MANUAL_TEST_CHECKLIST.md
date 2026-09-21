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

## Phase 7 — automations, tutor, providers

11. **Automations screen**  
    - Settings → Automations → save “Fee overdue reminder” → Run now.  
    - **Pass:** Action log shows a run; second Run does not crash.

12. **AI Copilot runs automation**  
    - AI Copilot: ask “run fee reminders”.  
    - **Pass:** Answer or action log reflects a run (not a blank error).

13. **AI Tutor isolation**  
    - Open `/student/tutor`, ask a question with an empty batch.  
    - **Pass:** Message that no vault sources found (not another batch’s content).

14. **BYO keys copy**  
    - Settings → AI API keys.  
    - **Pass:** Text says developer console keys, not ChatGPT Plus login; providers include Groq, NIM, OpenAI, Anthropic, Gemini.

15. **View file size guard**  
    - Vault open on a normal small PDF/image still works.  
    - **Pass:** Viewer opens or clear error (no app crash).

---

## Phase 8 — design, viewers, RAG

16. **Login feel**  
    - Open sign-in cold.  
    - **Pass:** Clear hierarchy, smooth enter animation, error banner animates in/out; not a flat clinical form.

17. **PDF viewer**  
    - Vault → open a PDF → Prev/Next, zoom, search a word that exists.  
    - **Pass:** Page changes; zoom works; find jumps page.

18. **Image / media**  
    - Open an image (zoom) and a short audio/video if available.  
    - **Pass:** Zoom buttons work; media has seek/speed (Plyr) or clear native controls.

19. **Tutor multi-doc**  
    - Upload several notes to one batch, ask a question only one note answers.  
    - **Pass:** Answer cites that note’s title, not a random other batch file.

---

If anything fails, note the step number and a screenshot in your reply to the builder.


