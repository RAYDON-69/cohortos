"""Standalone CohortOS API entry."""
from __future__ import annotations
import os, secrets, sys
from pathlib import Path

def _data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path.home() / ".cohortos"
    d = base / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _ensure_secret(sec: Path, name: str, env_key: str) -> str:
    if os.environ.get(env_key):
        return os.environ[env_key]
    sec.mkdir(parents=True, exist_ok=True)
    f = sec / name
    if f.exists():
        return f.read_text().strip()
    val = secrets.token_hex(32)
    f.write_text(val)
    try: f.chmod(0o600)
    except Exception: pass
    return val

def main() -> None:
    data = _data_dir()
    sec = data / "secrets"
    os.environ.setdefault("COHORTOS_JWT_SECRET", _ensure_secret(sec, "jwt_secret.txt", "COHORTOS_JWT_SECRET"))
    os.environ.setdefault("COHORTOS_FOUNDER_TOKEN", _ensure_secret(sec, "founder_token.txt", "COHORTOS_FOUNDER_TOKEN"))
    os.environ.setdefault("COHORTOS_AUTH_DB", str(data / "auth.db"))
    os.environ.setdefault("COHORTOS_CLOUD_DB", str(data / "cloud.db"))
    os.environ.setdefault("COHORTOS_TEST_EXPOSE_OTP", "1")
    os.environ.setdefault("COHORTOS_CORS_ORIGINS", "http://127.0.0.1:8741,http://localhost:8741,file://")
    host = os.environ.get("COHORTOS_HOST", "127.0.0.1")
    port = int(os.environ.get("COHORTOS_PORT", "8741"))
    import uvicorn
    from api.main import create_api_app_or_raise
    print(f"CohortOS API -> http://{host}:{port}")
    uvicorn.run(create_api_app_or_raise(), host=host, port=port, log_level="warning")

if __name__ == "__main__":
    main()
