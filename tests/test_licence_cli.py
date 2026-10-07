import subprocess, sys
from pathlib import Path
import pytest
from services.licence_service import HAS_CRYPTO

pytestmark = pytest.mark.skipif(not HAS_CRYPTO, reason="cryptography required")
CLI = str(Path(__file__).resolve().parents[1] / "tools" / "licence_cli.py")

def test_keygen_refuses_repo_dir(tmp_path):
    # out-dir inside repo should be refused
    repo_tools = Path(__file__).resolve().parents[1] / "tools" / "keys-should-not"
    rc = subprocess.run([sys.executable, CLI, "keygen", "--out-dir", str(repo_tools)], capture_output=True, text=True)
    assert rc.returncode != 0

def test_keygen_and_issue_outside_repo(tmp_path):
    out = tmp_path / "keys"
    rc = subprocess.run([sys.executable, CLI, "keygen", "--out-dir", str(out)], capture_output=True, text=True)
    assert rc.returncode == 0, rc.stderr
    priv = out / "licence_private.key"
    assert priv.exists()
    rc2 = subprocess.run([
        sys.executable, CLI, "issue-licence",
        "--private-key", str(priv),
        "--tenant-id", "t-cli",
        "--plan", "growth",
        "--seats", "100",
        "--days", "30",
    ], capture_output=True, text=True)
    assert rc2.returncode == 0 and "." in rc2.stdout.strip()

def test_sign_revocation_and_update(tmp_path):
    out = tmp_path / "keys2"
    subprocess.check_call([sys.executable, CLI, "keygen", "--out-dir", str(out)])
    priv = str(out / "licence_private.key")
    rc = subprocess.run([sys.executable, CLI, "sign-revocation", "--private-key", priv, "--tenants", "a,b"], capture_output=True, text=True)
    assert rc.returncode == 0 and "." in rc.stdout
    rc2 = subprocess.run([
        sys.executable, CLI, "sign-update-manifest",
        "--private-key", priv, "--version", "2.0.0",
        "--url", "https://example.com/x", "--sha256", "abc",
    ], capture_output=True, text=True)
    assert rc2.returncode == 0 and "." in rc2.stdout
