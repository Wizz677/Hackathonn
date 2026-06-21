import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import {
  Card,
  RiskBadge,
  StatusBadge,
  Spinner,
  typeLabel,
} from "../ui.jsx";

const TYPES = [
  "admin_access",
  "firewall_rule_open",
  "encryption_waiver",
  "data_access",
  "dev_environment",
];
const STATUSES = ["ACTIVE", "EXPIRED", "PENDING", "REVOKED", "RENEWED"];
const RISKS = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

export default function Registry({ openDetail }) {
  const [filters, setFilters] = useState({
    type: "",
    status: "",
    computed_risk: "",
    search: "",
    sort: "risk",
  });
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setData(null);
    const t = setTimeout(() => {
      api.list(filters).then(setData).catch((e) => setError(e.message));
    }, 150); // debounce search typing
    return () => clearTimeout(t);
  }, [filters]);

  const set = (k) => (e) => setFilters((f) => ({ ...f, [k]: e.target.value }));

  const select =
    "rounded-md border border-slate-800 bg-slate-900 px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-teal-500/50";

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={filters.search}
            onChange={set("search")}
            placeholder="Search id, requester, approver, justification…"
            className={`${select} min-w-[220px] flex-1`}
          />
          <select value={filters.type} onChange={set("type")} className={select}>
            <option value="">All types</option>
            {TYPES.map((t) => (
              <option key={t} value={t}>
                {typeLabel(t)}
              </option>
            ))}
          </select>
          <select value={filters.status} onChange={set("status")} className={select}>
            <option value="">All statuses</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <select
            value={filters.computed_risk}
            onChange={set("computed_risk")}
            className={select}
          >
            <option value="">All risk</option>
            {RISKS.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
          <select value={filters.sort} onChange={set("sort")} className={select}>
            <option value="risk">Sort: risk</option>
            <option value="expiry">Sort: expiry</option>
            <option value="id">Sort: id</option>
          </select>
        </div>
      </Card>

      {error && (
        <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 p-4 text-sm text-rose-200">
          {error}
        </div>
      )}

      {!data ? (
        <Spinner label="Querying registry…" />
      ) : (
        <Card title={`${data.count} exceptions`}>
          <Table records={data.records} openDetail={openDetail} />
        </Card>
      )}
    </div>
  );
}

function Table({ records, openDetail }) {
  const rows = useMemo(() => records.slice(0, 400), [records]);
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wider text-slate-500">
            <th className="py-2 pr-3">ID</th>
            <th className="py-2 pr-3">Type</th>
            <th className="py-2 pr-3">Status</th>
            <th className="py-2 pr-3">Risk</th>
            <th className="py-2 pr-3">Alerts</th>
            <th className="py-2 pr-3">Expiry</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800">
          {rows.map((r) => (
            <tr
              key={r.exception_id}
              onClick={() => openDetail(r.exception_id)}
              className="cursor-pointer transition hover:bg-slate-800/40"
            >
              <td className="mono py-2 pr-3 text-slate-300">{r.exception_id}</td>
              <td className="py-2 pr-3 text-slate-300">{typeLabel(r.type)}</td>
              <td className="py-2 pr-3">
                <StatusBadge status={r.status} />
              </td>
              <td className="py-2 pr-3">
                <RiskBadge level={r.computed_risk_level} />
              </td>
              <td className="py-2 pr-3">
                {r.alerts.length > 0 ? (
                  <span className="rounded-md bg-slate-800 px-2 py-0.5 text-xs text-slate-300">
                    {r.alerts.length}
                  </span>
                ) : (
                  <span className="text-xs text-slate-600">—</span>
                )}
              </td>
              <td className="mono py-2 pr-3 text-slate-400">
                {r.end_date || "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {records.length > rows.length && (
        <p className="mt-3 text-xs text-slate-500">
          Showing first {rows.length} of {records.length}. Narrow the filters to
          see more.
        </p>
      )}
    </div>
  );
}
