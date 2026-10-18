from app.services.log_processing import classify_heuristic, extract_failure, redact


def test_redacts_secrets():
    text = "token=ghp_abcdefghijklmnopqrstuvwxyz123456 and API_KEY: sk-ant-abc123xyz789"
    out = redact(text)
    assert "ghp_" not in out
    assert "sk-ant-abc" not in out


def test_extract_failure_keeps_error_window():
    log = "\n".join([f"step {i}" for i in range(500)] + ["ERROR: boom"] + ["tail"] * 10)
    out = extract_failure(log, context=2)
    assert "ERROR: boom" in out
    assert "step 0" not in out


def test_heuristic_dependency():
    r = classify_heuristic("ModuleNotFoundError: No module named 'requests'")
    assert r.category == "dependency"
    assert r.evidence


def test_heuristic_test_failure():
    r = classify_heuristic("FAILED tests/test_api.py::test_login - AssertionError")
    assert r.category == "test_failure"
