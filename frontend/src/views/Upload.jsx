import { useState } from "react";
import { api } from "../api";
import { Card, ExactJsonPanel, RiskBadge, typeLabel } from "../ui.jsx";

export default function Upload({ onDone, goRegistry }) {
  const [file, setFile] = useState(null);
  const [mode, setMode] = useState("replace");
  const [result, setResult] = useState(null);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    setSelected(null);
    try {
      const r = await api.upload(file, mode);
      setResult(r);
      onDone?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  // The record whose exact JSON is shown — the clicked row, else the first.
  const selectedRec = selected || result?.records?.[0] || null;

  return (
    <div className="space-y-5">
      <Card title="Upload exceptions CSV">
        <p className="mb-4 text-sm text-slate-400">
          Provide a <span className="mono text-slate-300">.csv</span> in the
          schema (<span className="mono text-slate-300">exception_id, type,
          requester, approver, justification, start_date, end_date, status,
          risk_level</span>). The engine analyzes every row on upload.
        </p>

        <div className="flex flex-wrap items-center gap-3">
          <input
            type="file"
            accept=".csv"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="text-sm text-slate-300 file:mr-3 file:rounded-md file:border file:border-slate-700 file:bg-slate-800 file:px-3 file:py-1.5 file:text-sm file:text-slate-200"
          />
          <div className="flex gap-1 rounded-lg border border-slate-800 bg-slate-900/60 p-1">
            {["replace", "add"].map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`rounded-md px-3 py-1.5 text-sm capitalize transition ${
                  mode === m
                    ? "bg-teal-500/20 text-teal-200"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {m}
              </button>
            ))}
          </div>
          <button
            disabled={!file || busy}
            onClick={submit}
            className="rounded-lg border border-teal-500/40 bg-teal-500/15 px-4 py-1.5 text-sm font-semibold text-teal-200 transition hover:bg-teal-500/25 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy ? "Analyzing…" : "Upload & analyze"}
          </button>
        </div>

        {error && (
          <div className="mt-4 rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-200">
            {error}
          </div>
        )}
      </Card>

      {result && (
        <div className="grid gap-5 lg:grid-cols-3">
          <Card
            className="lg:col-span-2"
            title={`Analyzed ${result.records.length} of ${result.received} received (${result.mode})`}
            action={
              <button
                onClick={goRegistry}
                className="text-xs text-teal-300 hover:underline"
              >
                View full registry →
              </button>
            }
          >
            <p className="mb-2 text-xs text-slate-500">
              Select a row to see its exact per-record JSON →
            </p>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wider text-slate-500">
                    <th className="py-2 pr-3">ID</th>
                    <th className="py-2 pr-3">Type</th>
                    <th className="py-2 pr-3">Risk</th>
                    <th className="py-2 pr-3">Recommendation</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {result.records.slice(0, 50).map((r) => (
                    <tr
                      key={r.exception_id}
                      onClick={() => setSelected(r)}
                      className={`cursor-pointer transition ${
                        selectedRec?.exception_id === r.exception_id
                          ? "bg-teal-500/10"
                          : "hover:bg-slate-800/40"
                      }`}
                    >
                      <td className="mono py-2 pr-3 text-slate-300">
                        {r.exception_id}
                      </td>
                      <td className="py-2 pr-3 text-slate-300">
                        {typeLabel(r.type)}
                      </td>
                      <td className="py-2 pr-3">
                        <RiskBadge level={r.computed_risk_level} />
                      </td>
                      <td className="py-2 pr-3 text-slate-400">
                        {r.recommendation}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-4 flex gap-3">
              <a
                href={api.exportJsonUrl}
                className="text-sm text-teal-300 hover:underline"
              >
                ↓ Download analyzed JSON
              </a>
              <a
                href={api.exportCsvUrl}
                className="text-sm text-teal-300 hover:underline"
              >
                ↓ Download analyzed CSV
              </a>
            </div>
          </Card>

          <ExactJsonPanel
            record={selectedRec}
            className="lg:sticky lg:top-4 lg:self-start"
          />
        </div>
      )}
    </div>
  );
}
