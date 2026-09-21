# Run CohortOS locally (first-time, zero guessing)

For Linux desktop (e.g. Linux Mint XFCE). Two terminals required.

---

## 0. Prerequisites

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
node -v    # need v18+ or v20+
python3 -V # need 3.11+
```

If Node is missing, install from [nodejs.org](https://nodejs.org/) (LTS 20).

---

## 1. Get the code

```bash
git clone https://github.com/RAYDON-69/cohortos.git
cd cohortos
git pull origin main
```

You should see folders: `api/`, `frontend/`, `services/`.

---

## 2. Terminal A — API (port 8741)

```bash
cd ~/cohortos          # or wherever you cloned
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export COHORTOS_JWT_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
export COHORTOS_FOUNDER_TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
export COHORTOS_TEST_EXPOSE_OTP=1

mkdir -p data
python3 -c "
import os
from api.main import create_api_app
import uvicorn
app = create_api_app(
    jwt_secret=os.environ['COHORTOS_JWT_SECRET'],
    cloud_db='./data/cloud.db',
    auth_db='./data/auth.db',
    founder_token=os.environ['COHORTOS_FOUNDER_TOKEN'],
)
uvicorn.run(app, host='127.0.0.1', port=8741)
"
```

**Success:** log shows `Uvicorn running on http://127.0.0.1:8741`.  
Browser check: open http://127.0.0.1:8741/docs — Swagger UI loads.

Leave this terminal running.

---

## 3. Terminal B — Frontend (port 5173)

```bash
cd ~/cohortos/frontend
npm config set registry https://registry.npmjs.org/
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

**Success:** log shows `Local: http://127.0.0.1:5173/`.  
Open that URL — you should see the sign-in screen.

---

## 4. First sign-in

1. Use **Start a free centre trial** (or equivalent) with your phone number.
2. With `COHORTOS_TEST_EXPOSE_OTP=1`, a **6-digit test code** appears (API/UI) — enter it.
3. You should land on **Attendance** with the desk sidebar.

---

## 5. Optional: AI developer keys

Settings → **AI API keys** → choose provider → paste a **developer console** API key (not ChatGPT Plus / Claude Pro login) → Save.

| Provider | Get key from |
|----------|----------------|
| Groq | console.groq.com |
| OpenAI | platform.openai.com |
| Anthropic | console.anthropic.com |
| Gemini | aistudio.google.com |
| NVIDIA NIM | build.nvidia.com |

---

## Likely failures

| Symptom | Fix |
|--------|-----|
| `npm install` hangs / 502 | `npm config set registry https://registry.npmjs.org/` then retry |
| Login fails / network errors | Terminal A still running on **8741**? |
| `ModuleNotFoundError: fastapi` | `source .venv/bin/activate` and `pip install -r requirements.txt` again |
| Blank white page | Hard refresh; confirm Vite is on **5173** and API on **8741** |
| Port already in use | `fuser -k 8741/tcp` or `5173/tcp` then restart that terminal |

---

## Manual QA after local start

See **MANUAL_TEST_CHECKLIST.md** (about 15 minutes). Session after full app quit + OS sleep still needs your real device (not browser-only).

---

## Optional: packaged AppImage

From GitHub Actions **Desktop release** artifacts:

```bash
sudo apt install -y libfuse2t64 || sudo apt install -y libfuse2
chmod +x CohortOS-*.AppImage
./CohortOS-*.AppImage
```
