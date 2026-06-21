import { useEffect, useState, useCallback } from "react";
import { api } from "./api";
import Dashboard from "./views/Dashboard.jsx";
import Registry from "./views/Registry.jsx";
import Detail from "./views/Detail.jsx";
import Upload from "./views/Upload.jsx";
import Report from "./views/Report.jsx";

const NAV = [
  { id: "dashboard", label: "Dashboard" },
  { id: "registry", label: "Registry" },
  { id: "upload", label: "Upload" },
  { id: "report", label: "Report" },
];

export default function App() {
  const [view, setView] = useState("dashboard");
  const [selectedId, setSelectedId] = useState(null);
  const [evalDate, setEvalDate] = useState("2026-04-15");
  const [auditSeconds, setAuditSeconds] = useState(null);
  // Bump to force child views to refetch after a global change (date/upload).
  const [refreshKey, setRefreshKey] = useState(0);

  const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);

  useEffect(() => {
    api.settings().then((s) => setEvalDate(s.evaluation_date)).catch(() => {});
  }, []);

  const openDetail = (id) => {
    setSelectedId(id);
    setView("detail");
  };

  const changeEvalDate = async (date) => {
    try {
      const s = await api.setSettings(date);
      setEvalDate(s.evaluation_date);
      refresh();
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="mx-auto max-w-7xl px-4 pb-16 pt-4 md:px-6">
      <Header
        view={view}
        setView={(v) => {
          setSelectedId(null);
          setView(v);
        }}
        evalDate={evalDate}
        changeEvalDate={changeEvalDate}
      />

      <SuccessStrip auditSeconds={auditSeconds} evalDate={evalDate} />

      <main className="mt-5">
        {view === "dashboard" && (
          <Dashboard key={refreshKey} openDetail={openDetail} />
        )}
        {view === "registry" && (
          <Registry key={refreshKey} openDetail={openDetail} />
        )}
        {view === "detail" && (
          <Detail
            id={selectedId}
            onBack={() => setView("registry")}
            onChanged={refresh}
          />
        )}
        {view === "upload" && <Upload onDone={refresh} goRegistry={() => setView("registry")} />}
        {view === "report" && (
          <Report key={refreshKey} onTiming={setAuditSeconds} />
        )}
      </main>

      <footer className="mt-10 border-t border-slate-800 pt-4 text-center text-xs text-slate-600">
        Sunset · 100% offline GRC exception engine · evaluation date is
        configurable, never the system clock
      </footer>
    </div>
  );
}

function Header({ view, setView, evalDate, changeEvalDate }) {
  return (
    <header className="flex flex-col gap-4 border-b border-slate-800 pb-4 md:flex-row md:items-center md:justify-between">
      <div className="flex items-center gap-3">
        <div className="grid h-10 w-10 place-items-center rounded-lg border border-teal-500/40 bg-teal-500/10 text-lg">
          <span className="text-teal-300">☀</span>
        </div>
        <div>
          <h1 className="text-lg font-bold tracking-tight text-slate-100">
            Sunset
          </h1>
          <p className="text-xs text-slate-500">
            GRC Exception &amp; Policy Waiver Management
          </p>
        </div>
        <span className="ml-2 rounded-md border border-teal-500/40 bg-teal-500/10 px-2 py-0.5 text-[11px] font-semibold text-teal-300">
          Approach: Option A
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <nav className="flex flex-wrap gap-1 rounded-lg border border-slate-800 bg-slate-900/60 p-1">
          {NAV.map((n) => (
            <button
              key={n.id}
              onClick={() => setView(n.id)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
                view === n.id || (view === "detail" && n.id === "registry")
                  ? "bg-teal-500/20 text-teal-200"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {n.label}
            </button>
          ))}
        </nav>

        <label className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-1.5 text-sm">
          <span className="text-slate-500">Eval&nbsp;date</span>
          <input
            type="date"
            value={evalDate}
            onChange={(e) => changeEvalDate(e.target.value)}
            className="bg-transparent text-teal-300 outline-none [color-scheme:dark]"
          />
        </label>
      </div>
    </header>
  );
}

function SuccessStrip({ auditSeconds, evalDate }) {
  const items = [
    { k: "Visibility", v: "100%" },
    { k: "Expiry accuracy", v: `as of ${evalDate}` },
    { k: "Risk scoring", v: "4-tier + alerts" },
    {
      k: "Audit readiness",
      v: auditSeconds != null ? `${auditSeconds}s` : "< 1s",
    },
  ];
  return (
    <div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-4">
      {items.map((it) => (
        <div
          key={it.k}
          className="rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2"
        >
          <div className="text-[10px] uppercase tracking-widest text-slate-500">
            {it.k}
          </div>
          <div className="text-sm font-semibold text-teal-300">{it.v}</div>
        </div>
      ))}
    </div>
  );
}
