from app.models.entities import RiskLevel
from app.services.diagnoser import assess_risk, diagnose
from tests.conftest import FakeClaude

LOG = """Run pytest
ImportError while importing test module
E   ModuleNotFoundError: No module named 'requests'
Error: Process completed with exit code 1."""


def test_falls_back_to_heuristic_without_key():
    r = diagnose(LOG, {})
    assert r.category == "dependency"
    assert r.model == "heuristic"
    assert r.warnings


def test_rejects_hallucinated_evidence():
    fake = FakeClaude({
        "category": "dependency", "root_cause": "requests missing from requirements",
        "evidence": ["E   ModuleNotFoundError: No module named 'requests'",
                     "this line does not exist in the log"],
        "confidence": 0.9, "fix_summary": "Add requests", "patch": "",
        "files_touched": ["requirements.txt"],
    })
    r = diagnose(LOG, {}, client=fake)
    assert len(r.evidence) == 1
    assert any("not found in log" in w for w in r.warnings)
    assert r.risk == RiskLevel.medium


def test_caps_confidence_without_evidence():
    fake = FakeClaude({"category": "unknown", "root_cause": "?", "evidence": [],
                       "confidence": 0.95, "fix_summary": "", "files_touched": []})
    assert diagnose(LOG, {}, client=fake).confidence <= 0.3


def test_risk_rules():
    assert assess_risk(["README.md"]) == RiskLevel.low
    assert assess_risk(["tests/test_x.py"]) == RiskLevel.low
    assert assess_risk(["app/service.py"]) == RiskLevel.medium
    assert assess_risk([".github/workflows/ci.yml"]) == RiskLevel.high
    assert assess_risk(["Dockerfile"]) == RiskLevel.high
