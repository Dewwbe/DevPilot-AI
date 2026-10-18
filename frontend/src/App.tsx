import { useState } from "react";
import { DiagnosePage } from "./pages/Diagnose";
import { RepositoriesPage } from "./pages/Repositories";
import { AuditPage } from "./pages/Audit";

const tabs = { Diagnose: DiagnosePage, Repositories: RepositoriesPage, Audit: AuditPage } as const;
type Tab = keyof typeof tabs;

export default function App() {
  const [tab, setTab] = useState<Tab>("Diagnose");
  const Page = tabs[tab];
  return (
    <div className="shell">
      <nav>
        <strong>DevPilot AI</strong>
        {(Object.keys(tabs) as Tab[]).map((t) => (
          <button key={t} className={t === tab ? "active" : ""} onClick={() => setTab(t)}>{t}</button>
        ))}
      </nav>
      <main><Page /></main>
    </div>
  );
}
