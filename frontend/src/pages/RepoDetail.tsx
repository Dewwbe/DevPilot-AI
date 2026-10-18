import { useState } from "react";
import { api, type Run } from "../api/client";
import { CategoryBadge, Confidence, Empty, ErrorBox, ModelTag, Notice, Spinner, StatusBadge } from "../components/ui";
import { githubUrl, link, summarize, timeAgo, useLoad } from "../lib";

function RunRow({ run, busy, onDiagnose }: { run: Run; busy: boolean; onDiagnose: () => void }) {
  return (
    <tr>
      <td>
        <a href={run.url} target="_blank" rel="noreferrer" className="run-title">{run.title || run.name}</a>
        <div className="muted small">{run.name} · {run.branch ? <code>{run.branch}</code> : "–"} · <code>{run.sha}</code></div>
      </td>
      <td className="nowrap muted small">{run.created_at ? timeAgo(run.created_at) : "–"}</td>
      <td className="run-diag">
        {run.diagnosis_id ? (
          <a className="btn btn-ghost btn-sm" href={link(`/diagnoses/${run.diagnosis_id}`)}>View diagnosis</a>
        ) : run.diagnosing ? (
          <Spinner label="Diagnosing…" />
        ) : (
          <>
            <button className="btn btn-primary btn-sm" disabled={busy} onClick={onDiagnose}>
              {run.error ? "Retry" : "Diagnose"}
            </button>
            {run.error && <div className="small tone-warn run-error" title={run.error}>⚠ {run.error}</div>}
          </>
        )}
      </td>
    </tr>
  );
}

export function RepoDetailPage({ id }: { id: string }) {
  const repos = useLoad(api.repos, [id]);
  const repo = repos.data?.find((r) => r.id === id);
  const runs = useLoad(() => api.runs(id), [id], (r) => r.some((x) => x.diagnosing), 3000);
  const analyses = useLoad(() => api.analyses(id), [id], (a) => a[0]?.status === "queued" || a[0]?.status === "running");
  const diagnoses = useLoad(() => api.diagnoses({ repository: repo?.full_name, limit: 10 }), [repo?.full_name],
    () => !!runs.data?.some((x) => x.diagnosing), 3000);
  const [busyId, setBusyId] = useState("");
  const [actionError, setActionError] = useState("");

  async function diagnose(run: Run) {
    setBusyId(run.id); setActionError("");
    try {
      await api.diagnoseRun(id, run.id);
      runs.reload();
    } catch (e) { setActionError((e as Error).message); }
    finally { setBusyId(""); }
  }

  if (repos.data && !repo) {
    return <div className="page"><Empty title="Repository not found" action={<a className="btn btn-ghost" href={link("/repos")}>Back to repositories</a>} /></div>;
  }

  const profile = analyses.data?.[0]?.profile;
  return (
    <div className="page">
      <a className="back" href={link("/repos")}>← Repositories</a>
      <header className="page-head">
        <div>
          <h1>{repo?.full_name ?? "Repository"}</h1>
          {repo && <p className="muted">
            Default branch <code>{repo.default_branch}</code> ·{" "}
            <a href={githubUrl(repo.full_name)} target="_blank" rel="noreferrer">Open on GitHub ↗</a>
          </p>}
        </div>
        <button className="btn btn-ghost" onClick={() => { runs.reload(); diagnoses.reload(); }}>↻ Refresh</button>
      </header>

      <section className="card">
        <div className="section-head">
          <h2>Failed workflow runs</h2>
          <span className="muted small">Most recent first</span>
        </div>
        <ErrorBox message={actionError} />
        {runs.error ? (
          <Notice kind="warn">
            <strong>Couldn't load failed runs.</strong> {runs.error}
            <div><button className="btn btn-ghost btn-sm" onClick={runs.reload}>Try again</button></div>
          </Notice>
        ) : runs.loading && !runs.data ? <Spinner label="Asking GitHub for failed runs…" />
        : runs.data && runs.data.length === 0 ? (
          <Empty title="No failed runs 🎉">This repository has no recent failed GitHub Actions runs. Push a commit that breaks CI and press Refresh.</Empty>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Run</th><th>When</th><th>Diagnosis</th></tr></thead>
              <tbody>
                {runs.data?.map((r) => <RunRow key={r.id} run={r} busy={busyId === r.id} onDiagnose={() => diagnose(r)} />)}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="grid two">
        <div className="card">
          <div className="section-head"><h2>Diagnoses</h2><a href={link(`/diagnoses?repository=${encodeURIComponent(repo?.full_name ?? "")}`)}>All →</a></div>
          {diagnoses.data && diagnoses.data.length === 0 && <p className="muted">None yet. Diagnose a failed run above.</p>}
          <ul className="list">
            {diagnoses.data?.map((d) => (
              <li key={d.id}>
                <a className="list-row" href={link(`/diagnoses/${d.id}`)}>
                  <div className="list-main">
                    <div className="row gap"><CategoryBadge category={d.category} /><span className="muted small">{timeAgo(d.created_at)}</span></div>
                    <div className="clamp">{summarize(d)}</div>
                  </div>
                  <div className="list-side"><Confidence value={d.confidence} /><ModelTag model={d.model} /><StatusBadge status={d.fix?.status} /></div>
                </a>
              </li>
            ))}
          </ul>
        </div>

        <div className="card">
          <div className="section-head">
            <h2>Repository profile</h2>
            <button className="btn btn-ghost btn-sm" onClick={() => api.analyze(id).then(analyses.reload).catch((e: Error) => setActionError(e.message))}>Analyse</button>
          </div>
          {!analyses.data || analyses.data.length === 0 ? (
            <p className="muted">Not analysed yet. Analysis detects languages, frameworks, Docker and CI setup so diagnoses have context.</p>
          ) : analyses.data[0].status !== "completed" ? (
            <Spinner label={analyses.data[0].status === "failed" ? "Analysis failed. Press Analyse to retry." : "Analysing repository…"} />
          ) : (
            <dl className="kv">
              <dt>Primary language</dt><dd>{profile?.primary_language ?? "–"}</dd>
              <dt>Frameworks</dt><dd>{profile?.frameworks?.length ? profile.frameworks.join(", ") : "–"}</dd>
              <dt>Dockerfile</dt><dd>{profile?.has_dockerfile ? "Yes" : "No"}</dd>
              <dt>CI workflows</dt><dd>{profile?.ci_workflows?.length ?? 0}</dd>
              {profile?.findings && profile.findings.length > 0 && (<><dt>Findings</dt><dd><ul className="plain">{profile.findings.map((f) => <li key={f}>{f}</li>)}</ul></dd></>)}
            </dl>
          )}
        </div>
      </section>
    </div>
  );
}
