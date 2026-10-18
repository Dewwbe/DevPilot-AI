import { useState } from "react";
import { api, type Repository } from "../api/client";
import { Empty, ErrorBox, Spinner } from "../components/ui";
import { githubUrl, go, link, timeAgo, useLoad } from "../lib";

const ANALYSIS_LABEL: Record<string, string> = {
  queued: "Analysis queued", running: "Analysing…", completed: "Analysed", failed: "Analysis failed",
};

function RepoCard({ repo, onAnalyse }: { repo: Repository; onAnalyse: () => void }) {
  return (
    <li className="card repo-card">
      <div className="repo-main">
        <a className="repo-name" href={link(`/repos/${repo.id}`)}>{repo.full_name}</a>
        <div className="muted small">
          branch <code>{repo.default_branch}</code> · connected {timeAgo(repo.created_at)} ·{" "}
          <a href={githubUrl(repo.full_name)} target="_blank" rel="noreferrer">GitHub ↗</a>
        </div>
      </div>
      <div className="repo-meta">
        <span className="badge badge-muted">{repo.diagnosis_count} diagnos{repo.diagnosis_count === 1 ? "is" : "es"}</span>
        {repo.analysis_status && <span className={`badge st-${repo.analysis_status}`}>{ANALYSIS_LABEL[repo.analysis_status] ?? repo.analysis_status}</span>}
      </div>
      <div className="repo-actions">
        <button className="btn btn-ghost btn-sm" onClick={onAnalyse}>Analyse</button>
        <a className="btn btn-primary btn-sm" href={link(`/repos/${repo.id}`)}>View failed runs</a>
      </div>
    </li>
  );
}

export function RepositoriesPage() {
  const repos = useLoad(api.repos, [], (r) => r.some((x) => x.analysis_status === "queued" || x.analysis_status === "running"));
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function connect(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      const repo = await api.connect(url);
      setUrl("");
      go(`/repos/${repo.id}`);
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  return (
    <div className="page">
      <header className="page-head">
        <div><h1>Repositories</h1><p className="muted">Connect a GitHub repository by its link.</p></div>
      </header>

      <form className="card connect" onSubmit={connect}>
        <input value={url} onChange={(e) => setUrl(e.target.value)} aria-label="GitHub repository link"
               placeholder="https://github.com/owner/repo  or  owner/repo" />
        <button className="btn btn-primary" disabled={!url.trim() || busy}>{busy ? <Spinner label="Connecting…" /> : "Connect"}</button>
        {error && <div className="notice notice-error full" role="alert">{error}</div>}
      </form>

      <ErrorBox message={repos.error} onRetry={repos.reload} />
      {repos.loading && !repos.data && <Spinner label="Loading repositories…" />}
      {repos.data && repos.data.length === 0 && (
        <Empty title="No repositories yet">Paste a link above, for example https://github.com/octocat/Hello-World.</Empty>
      )}
      {repos.data && repos.data.length > 0 && (
        <ul className="repo-list">
          {repos.data.map((r) => (
            <RepoCard key={r.id} repo={r}
              onAnalyse={() => api.analyze(r.id).then(repos.reload).catch((e: Error) => setError(e.message))} />
          ))}
        </ul>
      )}
    </div>
  );
}
