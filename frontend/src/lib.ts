import { useCallback, useEffect, useRef, useState } from "react";

// ---------- tiny hash router: "#/diagnoses/abc?status=pending" ----------

export interface Route { path: string[]; query: URLSearchParams }

function parse(): Route {
  const raw = window.location.hash.replace(/^#/, "") || "/";
  const [p, q = ""] = raw.split("?");
  return { path: p.split("/").filter(Boolean), query: new URLSearchParams(q) };
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(parse);
  useEffect(() => {
    const on = () => { setRoute(parse()); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

export const link = (path: string) => `#${path}`;
export const go = (path: string) => { window.location.hash = path; };

// ---------- data loading ----------

export interface Loadable<T> {
  data: T | null; error: string; loading: boolean; reload: () => void;
  setData: (d: T | null) => void;
}

/** Load once (and on `deps` change). `pollMs` re-fetches quietly while `poll(data)` is true. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = [],
                           poll?: (d: T) => boolean, pollMs = 3000): Loadable<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const load = useCallback((quiet = false) => {
    if (!quiet) setLoading(true);
    return fnRef.current()
      .then((d) => { setData(d); setError(""); return d; })
      .catch((e: Error) => { setError(e.message); return null; })
      .finally(() => setLoading(false));
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { void load(); }, deps);

  const wantsPoll = !!poll && data !== null && poll(data);
  useEffect(() => {
    if (!wantsPoll) return;
    const id = setInterval(() => { void load(true); }, pollMs);
    return () => clearInterval(id);
  }, [wantsPoll, load, pollMs]);

  return { data, error, loading, reload: () => { void load(); }, setData };
}

// ---------- formatting ----------

export function timeAgo(iso: string | Date): string {
  const t = typeof iso === "string" ? new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + "Z")
                                    : iso;
  const s = Math.max(0, (Date.now() - t.getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 86400 * 30) return `${Math.floor(s / 86400)} d ago`;
  return t.toLocaleDateString();
}

export const pct = (v: number | null | undefined, digits = 0) =>
  v === null || v === undefined ? "–" : `${(v * 100).toFixed(digits)}%`;

export const CATEGORY_LABEL: Record<string, string> = {
  dependency: "Dependency", test_failure: "Test failure", lint_type: "Lint / types",
  docker_build: "Docker build", timeout_infra: "Timeout / infra", config: "Configuration",
  unknown: "Unknown",
};
export const categoryLabel = (c: string) => CATEGORY_LABEL[c] ?? c;

/** One readable line for lists. Offline-classifier results carry a placeholder root cause. */
export const summarize = (d: { model: string; category: string; root_cause: string }) =>
  d.model === "heuristic"
    ? `Classified as "${categoryLabel(d.category)}" by the offline classifier (Claude was not used).`
    : d.root_cause;

export const githubUrl = (fullName: string) => `https://github.com/${fullName}`;
