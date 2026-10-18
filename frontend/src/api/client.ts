export type Risk = "low" | "medium" | "high";
export type FixStatus = "pending" | "approved" | "rejected";

export interface User { login: string; name: string; avatar_url: string }
export interface Me { authenticated: boolean; auth_enabled: boolean; user: User | null }

export interface Repository {
  id: string; full_name: string; default_branch: string; created_at: string;
  diagnosis_count: number; analysis_status: string | null;
}
export interface Run {
  id: string; name: string; title: string; branch: string; sha: string; url: string;
  created_at: string; conclusion: string;
  diagnosis_id: string | null; diagnosing: boolean; error: string | null;
}
export interface Analysis {
  id: string; status: string; created_at: string;
  profile: { primary_language?: string | null; languages?: Record<string, number>;
             frameworks?: string[]; findings?: string[]; has_dockerfile?: boolean;
             ci_workflows?: string[]; error?: string };
}

export interface Diagnosis {
  id: string; fix_id: string | null; category: string; root_cause: string; evidence: string[];
  confidence: number; fix_summary: string; patch: string; risk: Risk; model: string;
  prompt_version: string; warnings: string[];
}
export interface Fix {
  id: string; summary: string; patch: string; risk: Risk; status: FixStatus;
  decided_by: string | null; pr_url: string | null;
}
export interface StoredDiagnosis {
  id: string; repository: string | null; provider_run_id: string | null;
  source: "run" | "pasted"; created_by: string | null; category: string; root_cause: string;
  evidence: string[]; confidence: number; model: string; prompt_version: string;
  created_at: string; fix: Fix | null;
}
export interface DiagnosisDetail extends StoredDiagnosis { log_excerpt: string; warnings: string[] }

export interface Stats {
  repositories: number; diagnoses_total: number; diagnoses_7d: number; pending_fixes: number;
  approved_fixes: number; rejected_fixes: number; prs_opened: number;
  approval_rate: number | null; avg_confidence: number | null; heuristic_share: number | null;
  tokens_7d: number; est_cost_7d_usd: number;
  by_category: { category: string; count: number }[];
  per_day: { date: string; count: number }[];
}
export interface AuditEvent {
  actor: string; action: string; target: string; at: string; detail?: Record<string, unknown>;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

/** Turn FastAPI error bodies ({"detail": "..."} or a list of validation errors) into one sentence. */
function messageFrom(status: number, body: string): string {
  try {
    const d = JSON.parse(body).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d.length) {
      const first = d[0] as { msg?: string; loc?: string[] };
      return `${first.loc?.slice(-1)[0] ?? "input"}: ${first.msg ?? "is invalid"}`;
    }
  } catch { /* not JSON */ }
  return body || `Request failed (${status})`;
}

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const r = await fetch(path, {
    credentials: "same-origin",
    ...init,
    headers: { "Content-Type": "application/json", "X-Requested-With": "devpilot",
               ...(init.headers ?? {}) },
  });
  if (r.status === 401) window.dispatchEvent(new Event("devpilot:unauthorized"));
  if (!r.ok) throw new ApiError(r.status, messageFrom(r.status, await r.text()));
  return r.json() as Promise<T>;
}

const post = <T>(path: string, body?: unknown) =>
  req<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export interface DiagnosisFilter {
  repository?: string; category?: string; status?: string; source?: string;
  limit?: number; offset?: number;
}

export const api = {
  authConfig: () => req<{ enabled: boolean }>("/api/auth/config"),
  me: () => req<Me>("/api/auth/me"),
  logout: () => post<{ status: string }>("/api/auth/logout"),

  stats: () => req<Stats>("/api/stats"),

  repos: () => req<Repository[]>("/api/repositories"),
  connect: (full_name: string) => post<Repository>("/api/repositories", { full_name }),
  analyze: (id: string) => post<Analysis>(`/api/repositories/${id}/analyses`),
  analyses: (id: string) => req<Analysis[]>(`/api/repositories/${id}/analyses`),
  runs: (id: string) => req<Run[]>(`/api/repositories/${id}/runs`),
  diagnoseRun: (repoId: string, runId: string) =>
    post<{ pipeline_run_id: string; status: string; diagnosis_id?: string }>(
      `/api/repositories/${repoId}/runs/${runId}/diagnose`),

  diagnoseLog: (log: string) => post<Diagnosis>("/api/diagnose-log", { log }),
  diagnoses: (f: DiagnosisFilter = {}) => {
    const q = new URLSearchParams();
    Object.entries(f).forEach(([k, v]) => { if (v !== undefined && v !== "") q.set(k, String(v)); });
    return req<StoredDiagnosis[]>(`/api/diagnoses?${q}`);
  },
  diagnosis: (id: string) => req<DiagnosisDetail>(`/api/diagnoses/${id}`),
  decide: (fixId: string, decision: "approved" | "rejected", comment: string) =>
    post<{ id: string; status: FixStatus; decided_by: string }>(
      `/api/fixes/${fixId}/decision`, { decision, comment }),
  openPr: (fixId: string) => post<{ id: string; status: string }>(`/api/fixes/${fixId}/open-pr`),

  audit: () => req<AuditEvent[]>("/api/audit?limit=200"),
};
