import type { ReactNode } from "react";
import { useAuth } from "./auth";
import { Avatar, Spinner } from "./components/ui";
import { link, useRoute } from "./lib";
import { AuditPage } from "./pages/Audit";
import { DashboardPage } from "./pages/Dashboard";
import { DiagnosePage } from "./pages/Diagnose";
import { DiagnosesPage } from "./pages/Diagnoses";
import { DiagnosisDetailPage } from "./pages/DiagnosisDetail";
import { LoginPage } from "./pages/Login";
import { RepoDetailPage } from "./pages/RepoDetail";
import { RepositoriesPage } from "./pages/Repositories";

const icon = (d: string) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d={d} /></svg>
);
const NAV: { key: string; to: string; label: string; icon: ReactNode }[] = [
  { key: "", to: "/", label: "Dashboard", icon: icon("M3 12l9-9 9 9M5 10v10h5v-6h4v6h5V10") },
  { key: "repos", to: "/repos", label: "Repositories", icon: icon("M4 4h16v16H4zM4 9h16M9 4v16") },
  { key: "diagnoses", to: "/diagnoses", label: "History", icon: icon("M12 8v4l3 2M21 12a9 9 0 11-3-6.7L21 8M21 3v5h-5") },
  { key: "diagnose", to: "/diagnose", label: "Diagnose a log", icon: icon("M8 9l-4 3 4 3M16 9l4 3-4 3M13 6l-2 12") },
  { key: "audit", to: "/audit", label: "Audit", icon: icon("M9 12l2 2 4-4M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z") },
];

function Page() {
  const { path } = useRoute();
  const [section, id] = path;
  switch (section) {
    case undefined: return <DashboardPage />;
    case "repos": return id ? <RepoDetailPage id={id} /> : <RepositoriesPage />;
    case "diagnoses": return id ? <DiagnosisDetailPage id={id} /> : <DiagnosesPage />;
    case "diagnose": return <DiagnosePage />;
    case "audit": return <AuditPage />;
    default: return <DashboardPage />;
  }
}

export default function App() {
  const { loading, me, needsLogin, signOut } = useAuth();
  const { path } = useRoute();

  if (loading) return <div className="center-screen"><Spinner label="Loading…" /></div>;
  if (needsLogin) return <LoginPage />;

  const active = path[0] ?? "";
  const user = me?.user;
  return (
    <div className="shell">
      <aside className="sidebar">
        <a className="logo" href={link("/")}><span className="logo-mark">DP</span> DevPilot AI</a>
        <nav aria-label="Main">
          {NAV.map((n) => (
            <a key={n.key} href={link(n.to)} className={n.key === active ? "nav-item active" : "nav-item"}
               aria-current={n.key === active ? "page" : undefined}>{n.icon}<span>{n.label}</span></a>
          ))}
        </nav>
        <div className="sidebar-foot">
          {me?.auth_enabled && user ? (
            <div className="user">
              <Avatar src={user.avatar_url} name={user.login} />
              <div className="user-meta"><div className="user-name">{user.name || user.login}</div><div className="muted small">@{user.login}</div></div>
              <button className="btn btn-ghost btn-sm" onClick={signOut} title="Sign out">Sign out</button>
            </div>
          ) : (
            <div className="muted small" title="Set the GitHub OAuth variables to require sign-in">Sign-in is off (local mode)</div>
          )}
        </div>
      </aside>
      <main><Page /></main>
    </div>
  );
}
