import { useState } from "react";
import { api, type Diagnosis } from "../api/client";
import { DiagnosisCard } from "../components/DiagnosisCard";

export function DiagnosePage() {
  const [log, setLog] = useState("");
  const [result, setResult] = useState<Diagnosis | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true); setError("");
    try { setResult(await api.diagnoseLog(log)); }
    catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }

  return (
    <div>
      <h2>Diagnose a failed CI job</h2>
      <textarea rows={12} value={log} onChange={(e) => setLog(e.target.value)}
        placeholder="Paste a failed GitHub Actions log…" />
      <button disabled={!log || busy} onClick={run}>{busy ? "Analysing…" : "Diagnose"}</button>
      {error && <p className="warn">{error}</p>}
      {result && <DiagnosisCard d={result} />}
    </div>
  );
}
