import { api } from "../api/client";
import { Empty, ErrorBox, Spinner } from "../components/ui";
import { timeAgo, useLoad } from "../lib";

const LABELS: Record<string, string> = {
  "repository.connected": "Connected a repository",
  "analysis.completed": "Analysed a repository", "analysis.failed": "Repository analysis failed",
  "diagnosis.pasted": "Diagnosed a pasted log", "diagnosis.created": "Diagnosis created",
  "diagnosis.failed": "Diagnosis failed", "diagnosis.budget_exceeded": "Daily token budget reached",
  "run.diagnose_requested": "Requested a run diagnosis", "webhook.workflow_run_failed": "Webhook: workflow failed",
  "fix.approved": "Approved a fix", "fix.rejected": "Rejected a fix",
  "fix.pr_requested": "Requested a pull request", "fix.pr_opened": "Opened a pull request",
  "fix.pr_failed": "Pull request failed",
  "checks.completed": "Checks finished", "checks.failed": "Checks failed",
  "deployment.generated": "Generated deployment files",
};
const tone = (a: string) => /failed|exceeded|rejected/.test(a) ? "tone-bad" : /approved|opened|completed/.test(a) ? "tone-good" : "";

export function AuditPage() {
  const rows = useLoad(api.audit);
  return (
    <div className="page">
      <header className="page-head">
        <div><h1>Audit trail</h1><p className="muted">An append-only record of who did what.</p></div>
        <button className="btn btn-ghost" onClick={rows.reload}>↻ Refresh</button>
      </header>
      <ErrorBox message={rows.error} onRetry={rows.reload} />
      {rows.loading && !rows.data && <Spinner />}
      {rows.data && rows.data.length === 0 && <Empty title="No activity yet" />}
      {rows.data && rows.data.length > 0 && (
        <div className="card table-wrap">
          <table className="table">
            <thead><tr><th>When</th><th>Who</th><th>What</th><th>Target</th></tr></thead>
            <tbody>
              {rows.data.map((r, i) => (
                <tr key={i}>
                  <td className="nowrap muted small" title={new Date(r.at).toLocaleString()}>{timeAgo(r.at)}</td>
                  <td>{r.actor}</td>
                  <td className={tone(r.action)}>{LABELS[r.action] ?? r.action}</td>
                  <td className="muted small mono">{r.target.length > 38 ? r.target.slice(0, 36) + "…" : r.target}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
