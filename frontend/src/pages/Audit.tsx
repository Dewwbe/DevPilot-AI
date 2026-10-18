import { useEffect, useState } from "react";
import { api, type AuditEvent } from "../api/client";

export function AuditPage() {
  const [rows, setRows] = useState<AuditEvent[]>([]);
  useEffect(() => { api.audit().then(setRows).catch(() => setRows([])); }, []);
  return (
    <div>
      <h2>Audit trail</h2>
      <table>
        <thead><tr><th>When</th><th>Actor</th><th>Action</th><th>Target</th></tr></thead>
        <tbody>{rows.map((r, i) => (
          <tr key={i}><td>{new Date(r.at).toLocaleString()}</td><td>{r.actor}</td>
            <td>{r.action}</td><td>{r.target}</td></tr>))}</tbody>
      </table>
    </div>
  );
}
