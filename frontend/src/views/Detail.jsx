import { useEffect, useState } from "react";
import { api } from "../api";
import {
  Badge,
  Card,
  ExactJsonPanel,
  RiskBadge,
  StatusBadge,
  Spinner,
  typeLabel,
} from "../ui.jsx";

export default function Detail({ id, onBack, onChanged }) {
  const [rec, setRec] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = () =>
    api.detail(id).then(setRec).catch((e) => setError(e.message));

  useEffect(() => {
    setRec(null);
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const act = async (action) => {
    setBusy(true);
    try {
      await api.action(id, action);
      await load();
      onChanged?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  if (error) return <div className="text-rose-300">{error}</div>;
  if (!rec) return <Spinner label="Loading record…" />;

  const closed = rec.status === "REVOKED";

  return (
    <div className="space-y-5">
      <button
        onClick={onBack}
        className="text-sm text-slate-400 transition hover:text-teal-300"
      >
        ← Back to registry
      </button>

      <div className="flex flex-wrap items-center gap-3">
        <h2 className="mono text-2xl font-bold text-slate-100">
          {rec.exception_id}
        </h2>
        <RiskBadge level={rec.computed_risk_level} />
        <StatusBadge status={rec.status} />
        <RiskTooltip rec={rec} />
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <Card title="Recommendation" className="lg:col-span-2">
          <p
            className={`text-lg font-semibold ${
              rec.computed_risk_level === "CRITICAL"
                ? "text-rose-300"
                : "text-teal-200"
            }`}
          >
            {rec.recommendation}
          </p>

          <h4 className="mt-5 mb-2 text-xs uppercase tracking-widest text-slate-500">
            Alerts ({rec.alerts.length})
          </h4>
          {rec.alerts.length === 0 ? (
            <p className="text-sm text-emerald-300">
              No alerts — within policy.
            </p>
          ) : (
            <ul className="space-y-2">
              {rec.alerts.map((a) => {
                const [code, ...rest] = a.split(":");
                return (
                  <li
                    key={a}
                    className="flex items-start gap-2 rounded-lg border border-slate-800 bg-slate-900/60 p-2.5"
                  >
                    <span className="mono text-xs font-bold text-rose-300">
                      {code}
                    </span>
                    <span className="text-sm text-slate-300">
                      {rest.join(":").trim()}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <div className="space-y-5">
        <Card title="Lifecycle actions">
          <div className="flex flex-col gap-2">
            <button
              disabled={busy || closed}
              onClick={() => act("renew")}
              className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm font-semibold text-emerald-200 transition hover:bg-emerald-500/20 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Renew
            </button>
            <button
              disabled={busy || closed}
              onClick={() => act("revoke")}
              className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm font-semibold text-rose-200 transition hover:bg-rose-500/20 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Revoke
            </button>
            <button
              disabled={busy || closed}
              onClick={() => act("escalate")}
              title="Route this exception to its approver / risk owner for review (logged)"
              className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm font-semibold text-amber-200 transition hover:bg-amber-500/20 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Escalate to owner
            </button>
            {closed && (
              <p className="text-xs text-slate-500">
                This exception is revoked (closed).
              </p>
            )}
          </div>

          <h4 className="mb-2 mt-5 text-xs uppercase tracking-widest text-slate-500">
            Activity log
          </h4>
          {rec.activity?.length ? (
            <ul className="space-y-1.5 text-xs">
              {rec.activity.map((a) => (
                <li key={a.id} className="text-slate-400">
                  <span className="text-teal-300">{a.action}</span> — {a.detail}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-slate-600">No actions yet.</p>
          )}
        </Card>

          <ExactJsonPanel record={rec} />
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Record">
          <dl className="grid grid-cols-3 gap-y-2 text-sm">
            <Field k="Type" v={typeLabel(rec.type)} />
            <Field k="Requester" v={rec.requester} mono />
            <Field k="Approver" v={rec.approver} mono />
            <Field k="Start" v={rec.start_date} mono />
            <Field k="End (expiry)" v={rec.end_date} mono />
            <Field k="Input risk" v={rec.risk_level} />
            <Field k="Renewals" v={rec.renewal_count} />
            <Field
              k="Days past expiry"
              v={rec.days_past_expiry > 0 ? rec.days_past_expiry : "—"}
            />
            <div className="col-span-3">
              <dt className="text-slate-500">Justification</dt>
              <dd className="mt-0.5 text-slate-300">
                {rec.justification || (
                  <span className="text-slate-600">— none provided —</span>
                )}
              </dd>
            </div>
          </dl>
        </Card>

        <Card title="Compliance mapping">
          <h4 className="mb-1 text-xs uppercase tracking-widest text-slate-500">
            Frameworks
          </h4>
          <div className="flex flex-wrap gap-2">
            {rec.framework_tags.map((t) => (
              <Badge
                key={t}
                className="border-teal-500/30 bg-teal-500/10 text-teal-200"
              >
                {t}
              </Badge>
            ))}
          </div>
          <h4 className="mb-1 mt-4 text-xs uppercase tracking-widest text-slate-500">
            CIA triad
          </h4>
          <div className="flex flex-wrap gap-2">
            {rec.cia_tags.map((t) => (
              <Badge
                key={t}
                className="border-slate-600 bg-slate-700/30 text-slate-200"
              >
                {t}
              </Badge>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

function Field({ k, v, mono }) {
  return (
    <>
      <dt className="col-span-1 text-slate-500">{k}</dt>
      <dd className={`col-span-2 text-slate-200 ${mono ? "mono" : ""}`}>
        {v ?? "—"}
      </dd>
    </>
  );
}

// Tooltip explaining how the computed risk was derived (spec §7.3).
function RiskTooltip({ rec }) {
  const [open, setOpen] = useState(false);
  return (
    <span
      className="relative"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        onClick={() => setOpen((o) => !o)}
        className="grid h-5 w-5 place-items-center rounded-full border border-slate-600 text-xs text-slate-400"
        aria-label="How was this risk computed?"
      >
        ?
      </button>
      {open && (
        <div className="absolute left-0 top-7 z-10 w-72 rounded-lg border border-slate-700 bg-slate-900 p-3 text-xs text-slate-300 shadow-xl">
          <p className="mb-1 font-semibold text-teal-300">How risk was computed</p>
          <p>
            Base risk from type <b>{typeLabel(rec.type)}</b> and the declared
            input level <b>{rec.risk_level}</b>, then escalated by the alert
            engine. Elevated privilege combined with an expiry/overdue problem,
            or three or more stacked alerts, escalate to <b>CRITICAL</b>. This
            record raised <b>{rec.alerts.length}</b> alert
            {rec.alerts.length === 1 ? "" : "s"} →{" "}
            <b>{rec.computed_risk_level}</b>.
          </p>
        </div>
      )}
    </span>
  );
}
