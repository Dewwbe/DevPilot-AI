import { useState } from "react";
import { api } from "../api/client";
import { ErrorBox, Spinner } from "../components/ui";
import { go } from "../lib";

const SAMPLES: { label: string; log: string }[] = [
  { label: "Missing dependency", log: "Run pip install -r requirements.txt\nERROR: Could not find a version that satisfies the requirement foobarlib==9.9\nERROR: No matching distribution found for foobarlib==9.9\nError: Process completed with exit code 1." },
  { label: "Failing test", log: "Run pytest -q\n=================== FAILURES ===================\n___ test_total ___\n    def test_total():\n>       assert total([1, 2]) == 4\nE       assert 3 == 4\nFAILED tests/test_cart.py::test_total - assert 3 == 4\nError: Process completed with exit code 1." },
  { label: "Docker COPY error", log: "Step 4/8 : COPY requirements.txt .\nCOPY failed: file not found in build context or excluded by .dockerignore: stat requirements.txt: file does not exist\nError: buildx failed with: ERROR: failed to solve" },
];

export function DiagnosePage() {
  const [log, setLog] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function run() {
    setBusy(true); setError("");
    try {
      const d = await api.diagnoseLog(log);
      go(`/diagnoses/${d.id}`);  // the result is saved to history and reviewed there
    } catch (e) { setError((e as Error).message); setBusy(false); }
  }

  return (
    <div className="page narrow">
      <header className="page-head">
        <div><h1>Diagnose a log</h1><p className="muted">Paste the output of a failed CI job. Secrets are redacted before anything is analysed.</p></div>
      </header>
      <div className="card">
        <div className="row gap wrap">
          <span className="muted small">Try an example:</span>
          {SAMPLES.map((s) => <button key={s.label} className="chip" onClick={() => setLog(s.log)}>{s.label}</button>)}
        </div>
        <textarea rows={14} value={log} onChange={(e) => setLog(e.target.value)} spellCheck={false}
                  placeholder="Paste a failed GitHub Actions log here…" aria-label="CI log" />
        <ErrorBox message={error} />
        <div className="row gap">
          <button className="btn btn-primary" disabled={!log.trim() || busy} onClick={run}>
            {busy ? <Spinner label="Analysing…" /> : "Diagnose"}
          </button>
          {log && !busy && <button className="btn btn-ghost" onClick={() => setLog("")}>Clear</button>}
          <span className="muted small">{log.length.toLocaleString()} characters</span>
        </div>
      </div>
      <p className="muted small">Have a repository instead? <a href="#/repos">Connect it</a> and diagnose its failed runs without copying logs.</p>
    </div>
  );
}
