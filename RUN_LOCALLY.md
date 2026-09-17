# Run CohortOS locally (Linux desktop)

Assumes Ubuntu/Debian-style Linux with a desktop session (e.g. Linux Mint XFCE).

## 0. Prerequisites

- Git, Python 3.11+, Node.js 20+, npm
- Internet for first install

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
# Node 20 if missing: https://nodejs.org/ or your distro’s nodejs package
node -v
python3 -v
```

Success: `node -v` shows v20.x or similar; `python3 -v` shows 3.11+.

## 1. Clone / update

```bash
git clone https://github.com/RAYDON-69/cohortos.git
cd cohortos
git pull origin main
```

Success: folder contains `api/`, `frontend/`, `services/`.

## 2. Backend (API)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export COHORTOS_JWT_SECRET="$(python3 -c 'import secrets;print(secrets.token_hex(32))')"
export COHORTOS_FOUNDER_TOKEN="$(python3 -c 'import secrets;print(secrets.token_hex(16))')"
export COHORTOS_TEST_EXPOSE_OTP=1
python3 -c "from api.main import create_api_app; import uvicorn, os; app=create_api_app(jwt_secret=os.environ['COHORTOS_JWT_SECRET'], cloud_db='./data/cloud.db', auth_db='./data/auth.db', founder_token=os.environ['COHORTOS_FOUNDER_TOKEN']); uvicorn.run(app, host='127.0.0.1', port=8741)"
```

Success: terminal shows `Uvicorn running on http://127.0.0.1:8741`. Open http://127.0.0.1:8741/docs in a browser — Swagger UI loads.

Keep this terminal open.

## 3. Frontend (web desk)

New terminal:

```bash
cd cohortos/frontend
# Use official npm registry (avoid broken corporate proxies)
npm config set registry https://registry.npmjs.org/
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Success: `Local: http://127.0.0.1:5173/`. Open that URL — login screen appears.

## 4. First sign-in (pilot OTP)

1. On the login screen choose **Start a free centre trial** (or request OTP if already created).
2. Use your phone number.
3. With `COHORTOS_TEST_EXPOSE_OTP=1`, the API response / UI shows a **6-digit test code** — enter it.
4. You should land on **Attendance**.

Success: desk sidebar visible (Attendance, Admissions, Fees, …).

## 5. Optional: AI keys (Groq / NVIDIA NIM)

Settings → **AI API keys** → pick **Groq** or **NVIDIA NIM** → paste your key → Save.  
Then use “Ask about this centre” on that screen.

## Likely failures

| Symptom | Fix |
|--------|-----|
| `npm install` hangs or 502 errors | `npm config set registry https://registry.npmjs.org/` then retry. Avoid internal proxies. |
| Frontend loads but API errors / login fails | Confirm API terminal still running on port **8741**. CORS is set for `127.0.0.1:5173`. |
| `ModuleNotFoundError: fastapi` | Activate venv: `source .venv/bin/activate` and `pip install -r requirements.txt` again. |

## Optional: packaged desktop app

Use GitHub Actions **Desktop release** artifacts (AppImage). On Mint you may need:

```bash
sudo apt install -y libfuse2t64 || sudo apt install -y libfuse2
chmod +x CohortOS-*.AppImage
./CohortOS-*.AppImage
```

