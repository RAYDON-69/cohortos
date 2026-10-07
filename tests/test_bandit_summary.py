from pathlib import Path
from scripts.ci_bandit_summary import summarize
import json

def test_summary_with_findings(tmp_path):
    data = {
        "results": [
            {
                "filename": "services/x.py",
                "line_number": 10,
                "test_id": "B108",
                "issue_severity": "MEDIUM",
                "issue_text": "temp file",
            }
        ]
    }
    p = tmp_path / "b.json"
    p.write_text(json.dumps(data))
    out = tmp_path / "sum.txt"
    rc = summarize(str(p), str(out))
    assert rc == 0
    assert "services/x.py:10" in out.read_text()

def test_summary_empty(tmp_path):
    p = tmp_path / "b.json"
    p.write_text(json.dumps({"results": []}))
    out = tmp_path / "sum.txt"
    assert summarize(str(p), str(out)) == 0
    assert out.read_text() == ""
