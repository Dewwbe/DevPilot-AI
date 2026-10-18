export type Risk = "low" | "medium" | "high";

export interface Repository { id: string; full_name: string; default_branch: string; created_at: string }
export interface Diagnosis {
  category: string; root_cause: string; evidence: string[]; confidence: number;
  fix_summary: string; patch: string; risk: Risk; model: string; warnings: string[];
}
export interface AuditEvent { actor: string; action: string; target: string; at: string }

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json() as Promise<T>;
}

export const api = {
  repos: () => req<Repository[]>("/api/repositories"),
  connect: (full_name: string) =>
    req<Repository>("/api/repositories", { method: "POST", body: JSON.stringify({ full_name }) }),
  analyze: (id: string) => req(`/api/repositories/${id}/analyses`, { method: "POST" }),
  diagnoseLog: (log: string) =>
    req<Diagnosis>("/api/diagnose-log", { method: "POST", body: JSON.stringify({ log }) }),
  audit: () => req<AuditEvent[]>("/api/audit"),
};
