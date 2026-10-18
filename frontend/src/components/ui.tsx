import type { ReactNode } from "react";
import type { FixStatus, Risk } from "../api/client";
import { categoryLabel, pct } from "../lib";

export function Spinner({ label }: { label?: string }) {
  return <span className="spinner-wrap"><span className="spinner" aria-hidden />{label && <span>{label}</span>}</span>;
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  if (!message) return null;
  return (
    <div className="notice notice-error" role="alert">
      <span>{message}</span>
      {onRetry && <button className="btn btn-ghost btn-sm" onClick={onRetry}>Retry</button>}
    </div>
  );
}

export function Notice({ kind = "info", children }: { kind?: "info" | "warn" | "ok"; children: ReactNode }) {
  return <div className={`notice notice-${kind}`}>{children}</div>;
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      <div className="empty-icon" aria-hidden>◌</div>
      <h3>{title}</h3>
      {children && <p className="muted">{children}</p>}
      {action}
    </div>
  );
}

export function CategoryBadge({ category }: { category: string }) {
  return <span className={`badge cat-${category}`}>{categoryLabel(category)}</span>;
}

export function RiskBadge({ risk }: { risk: Risk }) {
  return <span className={`badge risk-badge risk-${risk}`}>{risk} risk</span>;
}

const STATUS_LABEL: Record<FixStatus, string> = {
  pending: "Needs review", approved: "Approved", rejected: "Rejected",
};
export function StatusBadge({ status }: { status: FixStatus | null | undefined }) {
  if (!status) return <span className="badge badge-muted">No fix</span>;
  return <span className={`badge status-${status}`}>{STATUS_LABEL[status]}</span>;
}

export function Confidence({ value }: { value: number }) {
  const tone = value >= 0.7 ? "high" : value >= 0.4 ? "mid" : "low";
  return (
    <span className="confidence" title={`Confidence ${pct(value)}`}>
      <span className="confidence-track"><span className={`confidence-fill c-${tone}`} style={{ width: pct(value) }} /></span>
      <span className="muted small">{pct(value)}</span>
    </span>
  );
}

export function ModelTag({ model }: { model: string }) {
  return model === "heuristic"
    ? <span className="badge badge-muted" title="Claude was not used for this diagnosis">heuristic</span>
    : <span className="badge badge-ai" title={model}>Claude</span>;
}

export function StatCard({ label, value, hint, tone, href }:
  { label: string; value: ReactNode; hint?: ReactNode; tone?: "warn" | "ok"; href?: string }) {
  const body = (
    <>
      <div className="stat-label">{label}</div>
      <div className={`stat-value ${tone ? `tone-${tone}` : ""}`}>{value}</div>
      {hint && <div className="stat-hint muted">{hint}</div>}
    </>
  );
  return href ? <a className="card stat stat-link" href={href}>{body}</a>
              : <div className="card stat">{body}</div>;
}

/** Unified-diff viewer: colours added/removed lines and hunk headers. */
export function DiffView({ patch }: { patch: string }) {
  return (
    <pre className="diff" aria-label="Proposed patch">
      {patch.split("\n").map((line, i) => {
        const cls = line.startsWith("+++") || line.startsWith("---") ? "d-file"
          : line.startsWith("@@") ? "d-hunk"
          : line.startsWith("+") ? "d-add" : line.startsWith("-") ? "d-del" : "";
        return <span key={i} className={`d-line ${cls}`}>{line || " "}{"\n"}</span>;
      })}
    </pre>
  );
}

export function Avatar({ src, name, size = 28 }: { src?: string; name: string; size?: number }) {
  return src
    ? <img className="avatar" src={src} alt="" width={size} height={size} />
    : <span className="avatar avatar-fallback" style={{ width: size, height: size }}>{name.slice(0, 1).toUpperCase()}</span>;
}

/** Simple SVG column chart with a hover title per bar. */
export function BarChart({ data }: { data: { label: string; value: number }[] }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  const W = 560, H = 150, pad = 22, gap = 6;
  const bw = (W - pad) / data.length - gap;
  return (
    <svg viewBox={`0 0 ${W} ${H + 22}`} className="chart" role="img" aria-label="Diagnoses per day">
      {[0, 0.5, 1].map((f) => (
        <line key={f} x1={pad} x2={W} y1={H - f * (H - 8)} y2={H - f * (H - 8)} className="chart-grid" />
      ))}
      <text x={0} y={14} className="chart-axis">{max}</text>
      <text x={0} y={H} className="chart-axis">0</text>
      {data.map((d, i) => {
        const h = d.value === 0 ? 2 : Math.max(4, (d.value / max) * (H - 8));
        const x = pad + i * (bw + gap);
        return (
          <g key={d.label}>
            <rect x={x} y={H - h} width={bw} height={h} rx={3} className={d.value ? "chart-bar" : "chart-bar-empty"}>
              <title>{`${d.label}: ${d.value}`}</title>
            </rect>
            {(i % 2 === 0 || data.length < 8) && (
              <text x={x + bw / 2} y={H + 16} textAnchor="middle" className="chart-axis">{d.label.slice(5)}</text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
