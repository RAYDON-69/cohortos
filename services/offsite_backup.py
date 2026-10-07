"""Schedule encrypted backups to a user-chosen folder/USB with retention (P36 C5)."""
from __future__ import annotations
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from services.tenant_backup import TenantBackupService

def write_backup_to_folder(svc: TenantBackupService, tenant_id: str, folder: Path, *, retain: int = 7) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    pkg = svc.create_backup(tenant_id)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = folder / f"cohortos-{tenant_id[:8]}-{ts}.json"
    path.write_text(json.dumps(pkg), encoding="utf-8")
    # retention
    files = sorted(folder.glob(f"cohortos-{tenant_id[:8]}-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[retain:]:
        try:
            old.unlink()
        except OSError:
            pass
    return path

def restore_drill(svc: TenantBackupService, path: Path) -> Dict[str, Any]:
    pkg = json.loads(Path(path).read_text(encoding="utf-8"))
    return svc.restore_backup(pkg, into_empty=True)
