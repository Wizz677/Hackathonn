import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api";
import {
  Card,
  RiskBadge,
  StatCard,
  Spinner,
  typeLabel,
} from "../ui.jsx";

const RISK_COLORS = {
  CRITICAL: "#fb7185",
  HIGH: "#fb923c",
  MEDIUM: "#fbbf24",
  LOW: "#34d399",
};

export default function Dashboard({ openDetail }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.dashboard().then(setData).catch((e) => setError(e.message));
  }, []);

  if (error) return <ErrorBox msg={error} />;
  if (!data) return <Spinner label="Loading portfolio…" />;

  const s = data.summary;
  const chart = Object.entries(data.risk_distribution).map(([name, value]) => ({
    name,
    value,
  }));

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <StatCard label="Active" value={s.total_active} accent="text-cyan-300" />
        <StatCard label="Critical" value={s.critical_risk} accent="text-rose-300" />
        <StatCard label="High" value={s.high_risk} accent="text-orange-300" />
        <StatCard label="Medium" value={s.medium_risk} accent="text-amber-300" />
        <StatCard label="Low" value={s.low_risk} accent="text-emerald-300" />
        <StatCard
          label="Expired · not revoked"
          value={s.expired_not_revoked}
          accent="text-rose-300"
          hint={`${s.expiring_this_month} expiring this month`}
        />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Risk distribution (active)">
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chart} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
                <XAxis
                  dataKey="name"
                  tick={{ fill: "#94a3b8", fontSize: 12 }}
                  axisLine={{ stroke: "#1e293b" }}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fill: "#94a3b8", fontSize: 12 }}
                  axisLine={false}
                  tickLine={false}
                  allowDecimals={false}
                />
                <Tooltip
                  cursor={{ fill: "rgba(148,163,184,0.08)" }}
                  contentStyle={{
                    background: "#0f172a",
                    border: "1px solid #1e293b",
                    borderRadius: 8,
                    color: "#e2e8f0",
                  }}
                />
                <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                  {chart.map((entry) => (
                    <Cell key={entry.name} fill={RISK_COLORS[entry.name]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card title="Breakdown by type (active)">
          <ul className="space-y-2">
            {Object.entries(data.by_type)
              .sort((a, b) => b[1] - a[1])
              .map(([t, n]) => (
                <li key={t} className="flex items-center gap-3">
                  <span className="w-36 shrink-0 text-sm text-slate-300">
                    {typeLabel(t)}
                  </span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-800">
                    <div
                      className="h-full rounded-full bg-teal-400/70"
                      style={{
                        width: `${
                          (n / Math.max(...Object.values(data.by_type), 1)) * 100
                        }%`,
                      }}
                    />
                  </div>
                  <span className="w-8 text-right text-sm font-semibold text-slate-200">
                    {n}
                  </span>
                </li>
              ))}
          </ul>
        </Card>
      </div>

      <Card title="Top high-risk exceptions">
        <div className="divide-y divide-slate-800">
          {data.top_high_risk.map((r) => (
            <button
              key={r.exception_id}
              onClick={() => openDetail(r.exception_id)}
              className="flex w-full items-center gap-3 py-2.5 text-left transition hover:bg-slate-800/40"
            >
              <RiskBadge level={r.computed_risk_level} />
              <span className="mono w-24 shrink-0 text-sm text-slate-400">
                {r.exception_id}
              </span>
              <span className="hidden w-32 shrink-0 text-sm text-slate-300 sm:block">
                {typeLabel(r.type)}
              </span>
              <span className="flex-1 truncate text-sm text-slate-400">
                {r.recommendation}
              </span>
              <span className="shrink-0 text-xs text-slate-500">
                {r.alerts.length} alert{r.alerts.length === 1 ? "" : "s"}
              </span>
            </button>
          ))}
        </div>
      </Card>
    </div>
  );
}

function ErrorBox({ msg }) {
  return (
    <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 p-4 text-sm text-rose-200">
      Could not reach the API ({msg}). Is the backend running on :8000?
    </div>
  );
}
