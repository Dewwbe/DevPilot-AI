"""Offline evaluation harness for the diagnoser.

Usage (from backend/):  python ../evals/run_evals.py
Without DEVPILOT_ANTHROPIC_API_KEY it evaluates the heuristic fallback only.
Metrics: category accuracy, keyword recall, evidence validity, tokens, latency.
Grow this set with real failures you collect - it is your regression suite for prompts.
"""
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.services.diagnoser import diagnose  # noqa: E402

cases = [json.loads(p.read_text()) for p in sorted((Path(__file__).parent / "cases").glob("*.json"))]
rows = []
for c in cases:
    r = diagnose(c["log"], {})
    text = (r.root_cause + " " + r.fix_summary + " " + " ".join(r.evidence)).lower()
    rows.append({
        "case": c["name"],
        "category_ok": r.category == c["expected_category"],
        "mentions_ok": all(k.lower() in text for k in c.get("must_mention", [])),
        "model": r.model, "tokens": r.input_tokens + r.output_tokens, "latency_ms": r.latency_ms,
    })

for row in rows:
    print(f"{row['case']:<28} category={'PASS' if row['category_ok'] else 'FAIL'}  "
          f"mentions={'PASS' if row['mentions_ok'] else 'FAIL'}  model={row['model']}")
acc = statistics.mean(r["category_ok"] for r in rows)
print(f"\nCategory accuracy: {acc:.0%} over {len(rows)} cases")
sys.exit(0 if acc >= 0.8 else 1)
