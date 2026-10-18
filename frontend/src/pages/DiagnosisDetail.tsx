import { useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth";
import { CategoryBadge, Confidence, DiffView, Empty, ErrorBox, ModelTag, Notice, RiskBadge, Spinner, StatusBadge } from "../components/ui";
import { githubUrl, link, summarize, timeAgo, useLoad } from "../lib";

export function DiagnosisDetailPage({ id }: { id: string }) {
  const { me } = useAuth();
  const d = useLoad(() => api.diagnosis(id), [id]);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");

  const data = d.data;
  if (d.loading && !data) return <div className="page"><Spinner label="Loading diagnosis…" /></div>;
  if (!data) {
    return <div className="page"><a className="back" href={link("/diagnoses")}>← History</a>
      {d.error ? <ErrorBox message={d.error} onRetry={d.reload} /> : <Empty title="Diagnosis not found" />}</div>;
  }

  const fix = data.fix;
  const reviewer = me?.user?.login ?? "you";
  const highRisk = fix?.risk === "high";

  async function decide(decision: "approved" | "rejected") {
    if (!fix) return;
    setBusy(decision); setError(""); setInfo("");
    try { await api.decide(fix.id, decision, comment); setComment(""); d.reload(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(""); }
  }

  async function openPr() {
    if (!fix) return;
    setBusy("pr"); setError(""); setInfo("");
    try {
      await api.openPr(fix.id);
      setInfo("Pull request requested. It usually appears within a few seconds: refresh to see the link.");
      setTimeout(d.reload, 4000);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(""); }
  }

  return (
    <div className="page">
      <a className="back" href={link("/diagnoses")}>← History</a>
      <header className="page-head">
        <div>
          <div className="row gap wrap">
            <CategoryBadge category={data.category} />
            {fix && <RiskBadge risk={fix.risk} />}
            <StatusBadge status={fix?.status} />
          </div>
          <h1 className="detail-title">{summarize(data)}</h1>
          <p className="muted">
            {data.repository
              ? <>From <a href={githubUrl(data.repository)} target="_blank" rel="noreferrer">{data.repository}</a>{data.provider_run_id && <> · run {data.provider_run_id}</>}</>
              : <>Pasted log{data.created_by ? ` by ${data.created_by}` : ""}</>}
            {" "}· {timeAgo(data.created_at)}
          </p>
          <div className="row gap wrap detail-meta">
            <span className="muted small">Confidence</span><Confidence value={data.confidence} />
            <ModelTag model={data.model} />
            {data.prompt_version && <span className="muted small">prompt {data.prompt_version}</span>}
          </div>
        </div>
      </header>

      {data.model === "heuristic" && (
        <Notice kind="warn">This used the offline heuristic classifier, not Claude, so there is no proposed fix.
          Set <code>DEVPILOT_ANTHROPIC_API_KEY</code> to enable full diagnoses.</Notice>
      )}

      <section className="card">
        <h2>Evidence from the log</h2>
        {data.evidence.length ? <pre className="code">{data.evidence.join("\n")}</pre>
          : <p className="muted">No verifiable evidence lines. Each line the model cites must appear verbatim in the log, otherwise it is dropped.</p>}
        {data.log_excerpt && (
          <details><summary>Show the redacted log excerpt that was analysed</summary><pre className="code">{data.log_excerpt}</pre></details>
        )}
      </section>

      {fix && (
        <section className="card">
          <h2>Proposed fix</h2>
          <p>{fix.summary}</p>
          {fix.patch ? <DiffView patch={fix.patch} /> : <p className="muted">No patch was generated for this fix; it is advice only.</p>}
        </section>
      )}

      {fix && (
        <section className="card review">
          <h2>Review</h2>
          <ErrorBox message={error} />
          {info && <Notice kind="ok">{info}</Notice>}
          {fix.status === "pending" ? (
            <>
              <p className="muted">Nothing changes until you approve. You are reviewing as <strong>{reviewer}</strong>.
                {highRisk && " High-risk changes need a written justification (at least 10 characters)."}</p>
              <textarea rows={3} value={comment} onChange={(e) => setComment(e.target.value)}
                        placeholder={highRisk ? "Why is this change safe? (required)" : "Optional note for the audit trail"} />
              <div className="row gap">
                <button className="btn btn-primary" disabled={!!busy || (highRisk && comment.trim().length < 10)} onClick={() => decide("approved")}>
                  {busy === "approved" ? "Approving…" : "Approve"}</button>
                <button className="btn btn-danger" disabled={!!busy} onClick={() => decide("rejected")}>
                  {busy === "rejected" ? "Rejecting…" : "Reject"}</button>
              </div>
            </>
          ) : (
            <>
              <p><StatusBadge status={fix.status} /> by <strong>{fix.decided_by ?? "unknown"}</strong></p>
              {fix.status === "approved" && fix.pr_url && (
                <Notice kind="ok">Pull request opened: <a href={fix.pr_url} target="_blank" rel="noreferrer">{fix.pr_url}</a></Notice>
              )}
              {fix.status === "approved" && !fix.pr_url && fix.patch && data.repository && (
                <div>
                  <button className="btn btn-primary" disabled={!!busy} onClick={openPr}>{busy === "pr" ? "Requesting…" : "Open pull request"}</button>
                  <p className="muted small">Creates a new <code>devpilot/fix-…</code> branch and a PR for you to review. It never pushes to the default branch and never merges.</p>
                </div>
              )}
              {fix.status === "approved" && !data.repository && <p className="muted small">Fixes for pasted logs have no repository, so no pull request can be opened. Copy the patch above.</p>}
            </>
          )}
        </section>
      )}

      {data.warnings.length > 0 && data.warnings.map((w) => <Notice key={w} kind="warn">{w}</Notice>)}
    </div>
  );
}
