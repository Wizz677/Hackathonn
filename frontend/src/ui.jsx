// Shared presentational helpers used across views.

export const RISK_STYLES = {
  CRITICAL: "text-rose-300 bg-rose-500/15 border-rose-500/40",
  HIGH: "text-orange-300 bg-orange-500/15 border-orange-500/40",
  MEDIUM: "text-amber-300 bg-amber-500/15 border-amber-500/40",
  LOW: "text-emerald-300 bg-emerald-500/15 border-emerald-500/40",
};

export const STATUS_STYLES = {
  ACTIVE: "text-cyan-300 bg-cyan-500/10 border-cyan-500/30",
  EXPIRED: "text-rose-300 bg-rose-500/10 border-rose-500/30",
  PENDING: "text-amber-300 bg-amber-500/10 border-amber-500/30",
  REVOKED: "text-slate-400 bg-slate-500/10 border-slate-500/30",
  RENEWED: "text-emerald-300 bg-emerald-500/10 border-emerald-500/30",
};

export const TYPE_LABELS = {
  admin_access: "Admin Access",
  firewall_rule_open: "Firewall Rule",
  encryption_waiver: "Encryption Waiver",
  data_access: "Data Access",
  dev_environment: "Dev Environment",
};

export function Badge({ children, className = "" }) {
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-semibold tracking-wide ${className}`}
    >
      {children}
    </span>
  );
}

export function RiskBadge({ level }) {
  return (
    <Badge className={RISK_STYLES[level] || RISK_STYLES.LOW}>{level}</Badge>
  );
}

export function StatusBadge({ status }) {
  return (
    <Badge className={STATUS_STYLES[status] || STATUS_STYLES.REVOKED}>
      {status}
    </Badge>
  );
}

export function Card({ title, children, className = "", action }) {
  return (
    <div
      className={`rounded-xl border border-slate-800 bg-slate-900/50 backdrop-blur p-4 ${className}`}
    >
      {(title || action) && (
        <div className="mb-3 flex items-center justify-between">
          {title && (
            <h3 className="text-xs font-semibold uppercase tracking-widest text-slate-400">
              {title}
            </h3>
          )}
          {action}
        </div>
      )}
      {children}
    </div>
  );
}

export function StatCard({ label, value, accent = "text-slate-100", hint }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
      <div className="text-xs uppercase tracking-widest text-slate-400">
        {label}
      </div>
      <div className={`mt-1 text-3xl font-bold ${accent}`}>{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

export function Spinner({ label = "Loading…" }) {
  return (
    <div className="flex items-center gap-3 p-8 text-slate-400">
      <div className="h-4 w-4 animate-spin rounded-full border-2 border-teal-400 border-t-transparent" />
      {label}
    </div>
  );
}

export function typeLabel(t) {
  return TYPE_LABELS[t] || t;
}
