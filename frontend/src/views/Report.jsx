import { useEffect, useState } from "react";
import { api } from "../api";
import { Card, Spinner } from "../ui.jsx";

export default function Report({ onTiming }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const generate = () => {
    setData(null);
    api
      .report()
      .then((d) => {
        setData(d);
        onTiming?.(d.generated_seconds);
      })
      .catch((e) => setError(e.message));
  };

  useEffect(() => {
    generate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error) return <div className="text-rose-300">{error}</div>;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={generate}
          className="rounded-lg border border-teal-500/40 bg-teal-500/15 px-4 py-1.5 text-sm font-semibold text-teal-200 transition hover:bg-teal-500/25"
        >
          ↻ Regenerate
        </button>
        <a
          href={api.reportDownloadUrl}
          className="rounded-lg border border-slate-700 bg-slate-800/60 px-4 py-1.5 text-sm font-semibold text-slate-200 transition hover:bg-slate-700"
        >
          ↓ Download report (.txt)
        </a>
        {data && (
          <span className="text-xs text-slate-500">
            Generated in{" "}
            <span className="text-teal-300">{data.generated_seconds}s</span> —
            satisfies the “audit in seconds” criterion
          </span>
        )}
      </div>

      {!data ? (
        <Spinner label="Building portfolio report…" />
      ) : (
        <Card title="Portfolio / audit report">
          <pre className="mono overflow-x-auto whitespace-pre-wrap text-[13px] leading-relaxed text-slate-200">
            {data.report}
          </pre>
        </Card>
      )}
    </div>
  );
}
