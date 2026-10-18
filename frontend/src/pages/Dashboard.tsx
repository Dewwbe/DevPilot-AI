import { useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth";
import { BarChart, CategoryBadge, Confidence, Empty, ErrorBox, ModelTag, Spinner, StatCard, StatusBadge } from "../components/ui";
import { categoryLabel, go, link, pct, summarize, timeAgo, useLoad } from "../lib";

function ConnectBox() {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      const repo = await api.connect(url);
      go(`/repos/${repo.id}`);
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  return (
    <form className="connect" onSubmit={submit}>
      <input value={url} onChange={(e) => setUrl(e.target.value)} aria-label="GitHub repository link"
             placeholder="Paste a GitHub repository link, e.g. https://github.com/owner/repo" />
      <button className="btn btn-primary" disabled={!url.trim() || busy}>
        {busy ? <Spinner label="Connecting…" /> : "Connect repository"}
      </button>
      {error && <div className="notice notice-error full" role="alert">{error}</div>}
    </form>
  );
}

export function DashboardPage() {
  const { me } = useAuth();
  const stats = useLoad(api.stats);
  const recent = useLoad(() => api.diagnoses({ limit: 6 }));
  const s = stats.data;
  const name = me?.authenticated ? (me.user?.name || me.user?.login) : "";

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>{name ? `Welcome back, ${name.split(" ")[0]}` : "Dashboard"}</h1>
          <p className="muted">What your repositories have been telling you lately.</p>
        </div>
      </header>

      <section className="card hero">
        <h2>Diagnose a repository</h2>
        <p className="muted">Link a GitHub repository, pick a failed workflow run, and get the root cause and a proposed fix.</p>
        <ConnectBox />
      </section>

      <ErrorBox message={stats.error} onRetry={stats.reload} />
      {stats.loading && !s && <Spinner label="Loading dashboard…" />}

      {s && (
        <>
          <section className="grid stats">
            <StatCard label="Needs your review" value={s.pending_fixes} tone={s.pending_fixes ? "warn" : undefined}
                      hint={s.pending_fixes ? "Open proposed fixes →" : "Nothing waiting"}
                      href={link("/diagnoses?status=pending")} />
            <StatCard label="Diagnoses (7 days)" value={s.diagnoses_7d} hint={`${s.diagnoses_total} all time`} />
            <StatCard label="Approval rate" value={pct(s.approval_rate)}
                      hint={`${s.approved_fixes} approved · ${s.rejected_fixes} rejected`} />
            <StatCard label="Repositories" value={s.repositories} hint={<a href={link("/repos")}>Manage →</a>} />
            <StatCard label="AI coverage" value={s.heuristic_share === null ? "–" : pct(1 - s.heuristic_share)}
                      hint="Diagnoses that used Claude" />
            <StatCard label="Claude spend (7 days)" value={`$${s.est_cost_7d_usd.toFixed(2)}`}
                      hint={`${s.tokens_7d.toLocaleString()} tokens · estimate`} />
          </section>

          <section className="grid two">
            <div className="card">
              <h2>Diagnoses per day</h2>
              <BarChart data={s.per_day.map((d) => ({ label: d.date, value: d.count }))} />
            </div>
            <div className="card">
              <h2>What fails most</h2>
              {s.by_category.length === 0 ? <p className="muted">No diagnoses yet.</p> : (
                <ul className="bars">
                  {s.by_category.map((c) => (
                    <li key={c.category}>
                      <a href={link(`/diagnoses?category=${c.category}`)}>
                        <span className="bars-label">{categoryLabel(c.category)}</span>
                        <span className="bars-track"><span className={`bars-fill cat-${c.category}`}
                          style={{ width: `${(c.count / s.by_category[0].count) * 100}%` }} /></span>
                        <span className="bars-count">{c.count}</span>
                      </a>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>
        </>
      )}

      <section className="card">
        <div className="section-head">
          <h2>Recent diagnoses</h2>
          <a href={link("/diagnoses")}>View all history →</a>
        </div>
        <ErrorBox message={recent.error} onRetry={recent.reload} />
        {recent.loading && !recent.data && <Spinner />}
        {recent.data && recent.data.length === 0 && (
          <Empty title="Nothing diagnosed yet"
                 action={<a className="btn btn-ghost" href={link("/diagnose")}>Paste a failing log</a>}>
            Connect a repository above, or paste a CI log to try it out.
          </Empty>
        )}
        {recent.data && recent.data.length > 0 && (
          <ul className="list">
            {recent.data.map((d) => (
              <li key={d.id}>
                <a className="list-row" href={link(`/diagnoses/${d.id}`)}>
                  <div className="list-main">
                    <div className="row gap">
                      <CategoryBadge category={d.category} />
                      <span className="muted small">{d.repository ?? "Pasted log"} · {timeAgo(d.created_at)}</span>
                    </div>
                    <div className="clamp">{summarize(d)}</div>
                  </div>
                  <div className="list-side"><Confidence value={d.confidence} /><ModelTag model={d.model} /><StatusBadge status={d.fix?.status} /></div>
                </a>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
