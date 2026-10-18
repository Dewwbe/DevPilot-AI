import { useEffect, useState } from "react";
import { api, type Repository } from "../api/client";

export function RepositoriesPage() {
  const [repos, setRepos] = useState<Repository[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const load = () => api.repos().then(setRepos).catch((e) => setError(String(e)));
  useEffect(() => { load(); }, []);

  return (
    <div>
      <h2>Repositories</h2>
      <div className="row">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="owner/repo" />
        <button onClick={() => api.connect(name).then(() => { setName(""); load(); })
          .catch((e) => setError(String(e)))}>Connect</button>
      </div>
      {error && <p className="warn">{error}</p>}
      <table>
        <thead><tr><th>Repository</th><th>Branch</th><th></th></tr></thead>
        <tbody>{repos.map((r) => (
          <tr key={r.id}><td>{r.full_name}</td><td>{r.default_branch}</td>
            <td><button onClick={() => api.analyze(r.id)}>Analyse</button></td></tr>
        ))}</tbody>
      </table>
    </div>
  );
}
