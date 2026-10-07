from datetime import date
from pathlib import Path

def test_exceptions_not_expired():
    p = Path("docs/PIP_AUDIT_EXCEPTIONS.txt")
    if not p.exists():
        return
    today = date.today()
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|")
        if len(parts) < 3:
            continue
        exp = date.fromisoformat(parts[2].strip())
        assert exp >= today, f"exception expired: {line}"

def test_nltk_vulnerable_apis_not_imported():
    import ast
    from pathlib import Path
    banned = {"TransitionParser", "AveragedPerceptron"}
    for path in Path("services").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("nltk"):
                for alias in node.names:
                    assert alias.name not in banned
            if isinstance(node, ast.Attribute) and getattr(node, "attr", "") in banned:
                raise AssertionError(f"{path} references {node.attr}")
