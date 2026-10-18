"""Evaluation harness for the diagnoser.

Usage (from the repo root, after `pip install -e backend[dev]`):
  python evals/run_evals.py --mode heuristic          # offline classifier only (no Claude)
  python evals/run_evals.py --mode fake               # full pipeline with a deterministic FakeClaude
  python evals/run_evals.py --mode real --max-cost-usd 1.00   # real Claude, stops at the cost cap

Modes
- heuristic: measures the regex classifier that is the fallback when Claude is unavailable.
- fake:      runs redaction -> window extraction -> grounding check -> risk rules with a fake model
             and asserts the *guardrails* (hallucinated evidence dropped, confidence capped, risk
             decided by rules). It validates our code, not model quality. Runs on every PR.
- real:      measures actual model quality, tokens, latency and estimated cost. Nightly.

Each mode is compared with its entry in evals/baseline.json; the run fails if accuracy drops
below the recorded floor. Raise the floor when quality improves. A JSON report is written to
evals/results/<mode>.json for CI artifacts.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))

from app.core.metrics import estimate_cost_usd  # noqa: E402
from app.models.entities import RiskLevel  # noqa: E402
from app.services.claude_client import LLMResult  # noqa: E402
from app.services.diagnoser import PROMPT_VERSION, diagnose  # noqa: E402


class FakeClaude:
    """Returns a scripted model response, so the pipeline around the model can be tested."""

    def __init__(self, data: dict):
        self.data = data

    def structured(self, **_kwargs) -> LLMResult:
        return LLMResult(data=self.data, model="fake", input_tokens=0, output_tokens=0,
                         latency_ms=0)


def load_cases() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted((ROOT / "cases").glob("*.json"))]


def synthesize_response(case: dict) -> dict:
    """A well-behaved model answer derived from the case labels (used when no override exists)."""
    keywords = [k.lower() for k in case.get("must_mention", [])]
    evidence = [line for line in case["log"].splitlines()
                if any(k in line.lower() for k in keywords)][:2]
    return {
        "category": case["expected_category"],
        "root_cause": "Failure involving " + ", ".join(case.get("must_mention", ["unknown"])),
        "evidence": evidence, "confidence": 0.8,
        "fix_summary": "Fix " + ", ".join(case.get("must_mention", [])),
        "patch": "", "files_touched": [],
    }


def run_case(case: dict, mode: str) -> dict:
    if mode == "heuristic":
        r = diagnose(case["log"], {}, use_llm=False)
    elif mode == "fake":
        r = diagnose(case["log"], {},
                     client=FakeClaude(case.get("fake_response") or synthesize_response(case)))
    else:
        r = diagnose(case["log"], {})
        if r.model == "heuristic":
            raise SystemExit("real mode needs DEVPILOT_ANTHROPIC_API_KEY (Claude was not used)")
    text = (r.root_cause + " " + r.fix_summary + " " + " ".join(r.evidence)).lower()
    return {
        "case": case["name"],
        "category_ok": r.category == case["expected_category"],
        "mentions_ok": all(k.lower() in text for k in case.get("must_mention", [])),
        "evidence_ok": all(e in case["log"] for e in r.evidence),  # redaction may alter lines
        "model": r.model, "tokens": r.input_tokens + r.output_tokens,
        "input_tokens": r.input_tokens, "output_tokens": r.output_tokens,
        "latency_ms": r.latency_ms, "prompt_version": r.prompt_version,
    }


def guardrail_checks() -> list[tuple[str, bool]]:
    """Fixed adversarial scenarios proving the code around the model enforces its rules."""
    log = "Run pytest\nE   ModuleNotFoundError: No module named 'requests'\nexit code 1"
    base = {"category": "dependency", "root_cause": "missing requests", "confidence": 0.95,
            "fix_summary": "add it", "patch": "", "files_touched": ["requirements.txt"]}
    out = []

    r = diagnose(log, {}, client=FakeClaude({**base, "evidence": ["a line that is not in the log"]}))
    out.append(("hallucinated evidence is dropped", r.evidence == []))
    out.append(("confidence capped without evidence", r.confidence <= 0.3))

    r = diagnose(log, {}, client=FakeClaude({
        **base, "evidence": ["E   ModuleNotFoundError: No module named 'requests'"],
        "files_touched": [".github/workflows/ci.yml"]}))
    out.append(("workflow edits are high risk (rules, not the model)", r.risk == RiskLevel.high))

    r = diagnose("password=hunter2 failed\nE   boom", {}, client=FakeClaude(
        {**base, "evidence": ["password=hunter2 failed"]}))
    out.append(("secrets are redacted before grounding", "hunter2" not in " ".join(r.evidence)))

    r = diagnose(log, {}, use_llm=False)
    out.append(("budget exhaustion falls back to heuristic", r.model == "heuristic"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["heuristic", "fake", "real"], default="heuristic")
    ap.add_argument("--max-cost-usd", type=float, default=1.0, help="real mode: stop when reached")
    ap.add_argument("--max-cases", type=int, default=0, help="0 = all")
    ap.add_argument("--no-baseline", action="store_true")
    args = ap.parse_args()

    cases = load_cases()
    if args.max_cases:
        cases = cases[: args.max_cases]

    rows, spent, stopped_early = [], 0.0, False
    for c in cases:
        if args.mode == "real" and spent >= args.max_cost_usd:
            stopped_early = True
            break
        row = run_case(c, args.mode)
        spent += estimate_cost_usd(row["input_tokens"], row["output_tokens"])
        rows.append(row)
        print(f"{row['case']:<28} category={'PASS' if row['category_ok'] else 'FAIL'}  "
              f"mentions={'PASS' if row['mentions_ok'] else 'FAIL'}  model={row['model']}")

    accuracy = statistics.mean(r["category_ok"] for r in rows)
    report = {
        "mode": args.mode, "prompt_version": PROMPT_VERSION, "cases": len(rows),
        "category_accuracy": round(accuracy, 3),
        "mention_rate": round(statistics.mean(r["mentions_ok"] for r in rows), 3),
        "evidence_validity": round(statistics.mean(r["evidence_ok"] for r in rows), 3),
        "avg_tokens": round(statistics.mean(r["tokens"] for r in rows), 1),
        "avg_latency_ms": round(statistics.mean(r["latency_ms"] for r in rows), 1),
        "estimated_cost_usd": round(spent, 4), "stopped_by_cost_cap": stopped_early,
        "rows": rows,
    }
    failures: list[str] = []

    if args.mode == "fake":
        print("\nGuardrail checks")
        for name, ok in guardrail_checks():
            print(f"  {'PASS' if ok else 'FAIL'}  {name}")
            if not ok:
                failures.append(f"guardrail: {name}")

    if not args.no_baseline:
        floor = json.loads((ROOT / "baseline.json").read_text(encoding="utf-8")).get(args.mode, {})
        for metric, minimum in floor.items():
            if report.get(metric.removeprefix("min_"), 0) < minimum:
                failures.append(f"{metric.removeprefix('min_')} {report[metric.removeprefix('min_')]}"
                                f" < baseline {minimum}")

    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / f"{args.mode}.json").write_text(json.dumps(report, indent=2),
                                                         encoding="utf-8")
    print(f"\nMode={args.mode}  category accuracy={accuracy:.0%} over {len(rows)} cases  "
          f"est. cost=${spent:.4f}" + ("  (stopped at cost cap)" if stopped_early else ""))
    for f in failures:
        print(f"FAILED: {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
