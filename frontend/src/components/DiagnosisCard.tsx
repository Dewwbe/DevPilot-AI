import type { Diagnosis } from "../api/client";

export function DiagnosisCard({ d }: { d: Diagnosis }) {
  return (
    <section className="card">
      <header className="row">
        <span className="tag">{d.category}</span>
        <span className={`risk risk-${d.risk}`}>risk: {d.risk}</span>
        <span className="muted">confidence {(d.confidence * 100).toFixed(0)}% · {d.model}</span>
      </header>
      <h3>Root cause</h3>
      <p>{d.root_cause}</p>
      {d.evidence.length > 0 && (<><h3>Evidence from log</h3><pre>{d.evidence.join("\n")}</pre></>)}
      {d.fix_summary && (<><h3>Proposed fix</h3><p>{d.fix_summary}</p></>)}
      {d.patch && <pre className="diff">{d.patch}</pre>}
      {d.warnings.map((w) => <p key={w} className="warn">⚠ {w}</p>)}
      {d.fix_summary && <p className="muted">Fixes are applied only after human approval.</p>}
    </section>
  );
}
