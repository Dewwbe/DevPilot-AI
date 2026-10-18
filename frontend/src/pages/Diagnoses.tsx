import { useEffect, useState } from "react";
import { api, type StoredDiagnosis } from "../api/client";
import { CategoryBadge, Confidence, Empty, ErrorBox, ModelTag, RiskBadge, Spinner, StatusBadge } from "../components/ui";
import { CATEGORY_LABEL, go, link, summarize, timeAgo, useRoute } from "../lib";

const PAGE = 25;

export function DiagnosesPage() {
  const { query } = useRoute();
  const filters = {
    repository: query.get("repository") ?? "", category: query.get("category") ?? "",
    status: query.get("status") ?? "", source: query.get("source") ?? "",
  };
  const key = JSON.stringify(filters);

  const [rows, setRows] = useState<StoredDiagnosis[]>([]);
  const [more, setMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [repos, setRepos] = useState<string[]>([]);

  useEffect(() => { api.repos().then((r) => setRepos(r.map((x) => x.full_name))).catch(() => {}); }, []);

  function load(offset: number) {
    setLoading(true); setError("");
    api.diagnoses({ ...filters, limit: PAGE, offset })
      .then((d) => { setRows((prev) => (offset ? [...prev, ...d] : d)); setMore(d.length === PAGE); })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(0); }, [key]);

  function setFilter(name: string, value: string) {
    const q = new URLSearchParams(query);
    if (value) q.set(name, value); else q.delete(name);
    go(`/diagnoses${q.toString() ? `?${q}` : ""}`);
  }
  const active = Object.values(filters).some(Boolean);

  return (
    <div className="page">
      <header className="page-head">
        <div><h1>History</h1><p className="muted">Every diagnosis, with its review status.</p></div>
        <a className="btn btn-primary" href={link("/diagnose")}>+ Diagnose a log</a>
      </header>

      <div className="card filters">
        <select value={filters.repository} onChange={(e) => setFilter("repository", e.target.value)} aria-label="Repository">
          <option value="">All repositories</option>
          {repos.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        <select value={filters.category} onChange={(e) => setFilter("category", e.target.value)} aria-label="Category">
          <option value="">All categories</option>
          {Object.entries(CATEGORY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select value={filters.status} onChange={(e) => setFilter("status", e.target.value)} aria-label="Review status">
          <option value="">Any review status</option>
          <option value="pending">Needs review</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
        </select>
        <select value={filters.source} onChange={(e) => setFilter("source", e.target.value)} aria-label="Source">
          <option value="">Any source</option>
          <option value="run">GitHub runs</option>
          <option value="pasted">Pasted logs</option>
        </select>
        {active && <button className="btn btn-ghost btn-sm" onClick={() => go("/diagnoses")}>Clear filters</button>}
      </div>

      <ErrorBox message={error} onRetry={() => load(0)} />
      {loading && rows.length === 0 && <Spinner label="Loading history…" />}
      {!loading && !error && rows.length === 0 && (
        <Empty title={active ? "No diagnoses match these filters" : "No diagnoses yet"}
               action={active ? <button className="btn btn-ghost" onClick={() => go("/diagnoses")}>Clear filters</button>
                             : <a className="btn btn-primary" href={link("/repos")}>Connect a repository</a>}>
          {active ? "Try removing a filter." : "Connect a repository and diagnose a failed run, or paste a log."}
        </Empty>
      )}

      {rows.length > 0 && (
        <div className="card table-wrap">
          <table className="table table-click">
            <thead><tr><th>When</th><th>Source</th><th>Category</th><th>Root cause</th><th>Confidence</th><th>Review</th></tr></thead>
            <tbody>
              {rows.map((d) => (
                <tr key={d.id} onClick={() => go(`/diagnoses/${d.id}`)}>
                  <td className="nowrap muted small">{timeAgo(d.created_at)}</td>
                  <td className="small nowrap">{d.repository ?? "Pasted log"}{d.created_by && d.source === "pasted" && <div className="muted">by {d.created_by}</div>}</td>
                  <td><CategoryBadge category={d.category} /></td>
                  <td><a href={link(`/diagnoses/${d.id}`)} className="clamp-2 plain-link">{summarize(d)}</a></td>
                  <td className="nowrap"><Confidence value={d.confidence} /> <ModelTag model={d.model} /></td>
                  <td className="nowrap">
                    <StatusBadge status={d.fix?.status} />
                    {d.fix && <div className="mt-s"><RiskBadge risk={d.fix.risk} /></div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {more && <div className="center pad"><button className="btn btn-ghost" disabled={loading} onClick={() => load(rows.length)}>{loading ? "Loading…" : "Load more"}</button></div>}
        </div>
      )}
    </div>
  );
}
