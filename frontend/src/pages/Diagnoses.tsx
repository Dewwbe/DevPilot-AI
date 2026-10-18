import { useEffect, useState } from "react";
import { api, type StoredDiagnosis } from "../api/client";

// Diagnoses created automatically (GitHub webhook) or from queued runs. Refreshes every 10s.
export function DiagnosesPage() {
  const [rows, setRows] = useState<StoredDiagnosis[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = () => api.diagnoses().then((r) => { setRows(r); setError(""); })
      .catch((e: Error) => setError(e.message));
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, []);

  return (
    <div>
      <h2>Diagnoses</h2>
      {error && <p role="alert">{error}</p>}
      {!error && rows.length === 0 && <p>No diagnoses yet. A failed workflow run will appear here.</p>}
      {rows.map((d) => (
        <article key={d.id} className="card">
          <h3>{d.repository} · run {d.provider_run_id}</h3>
          <p><strong>{d.category}</strong> · confidence {(d.confidence * 100).toFixed(0)}% · {d.model}</p>
          <p>{d.root_cause}</p>
          {d.evidence.length > 0 && <pre>{d.evidence.join("\n")}</pre>}
          {d.fix && (
            <p>Proposed fix: {d.fix.summary} <span className={`risk-${d.fix.risk}`}>{d.fix.risk}</span>
              {" "}({d.fix.status})</p>
          )}
          <small>{new Date(d.created_at).toLocaleString()}</small>
        </article>
      ))}
    </div>
  );
}
