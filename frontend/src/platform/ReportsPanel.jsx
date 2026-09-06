import { useEffect, useState } from "react";

import { fetchReport, fetchReports, fetchShare, postReport, postShare, revokeShare } from "./api";
import PanelState from "./PanelState";
import ProvenanceBadge from "./ProvenanceBadge";

export default function ReportsPanel({ cityId, visible, baselineJob, scenarioJob, eventId, mapState }) {
  const [report, setReport] = useState(null);
  const [reports, setReports] = useState([]);
  const [share, setShare] = useState(null);
  const [shareView, setShareView] = useState(null);
  const [shareId, setShareId] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!visible) return undefined;
    fetchReports()
      .then((data) => setReports(data.reports || []))
      .catch(() => setReports([]));
    return undefined;
  }, [visible, report]);

  if (!visible) return null;

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await postReport(cityId, { baselineJob, scenarioJob, eventId, mapState });
      setReport(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const download = async (format) => {
    if (!report?.id) return;
    const response = await fetchReport(report.id, format);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${report.id}.${format}`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const population =
    report?.body?.population_impact?.available === false
      ? null
      : report?.body?.population_impact?.population_exposed;

  return (
    <PanelState
      title="Reports and sharing"
      state={loading ? "LOADING" : error ? "ERROR" : report ? "SUCCESS" : "EMPTY"}
      message={error || (!report ? "Generate an immutable snapshot from currently available products." : undefined)}
    >
      <button type="button" onClick={run} className="rounded bg-slate-700 px-2 py-1 text-[10px] font-semibold uppercase text-white" aria-label="Generate report">
        Generate report
      </button>
      {report && (
        <div className="mt-2 space-y-1 text-xs">
          <p className="rounded border border-amber-800 bg-amber-950/40 px-2 py-1" role="status">
            SNAPSHOT GENERATED AT: {report.snapshot_time || report.generated_at}. This is a historical snapshot.
          </p>
          <p className="font-mono text-slate-100">{report.id}</p>
          <p>model {report.model_version || "UNAVAILABLE"}</p>
          <p>dataset {(report.source_versions || {}).data_version || "UNAVAILABLE"}</p>
          <p>kind {report.kind} · live={String(report.live === true)}</p>
          <p>POPULATION EXPOSURE: {population == null ? "UNAVAILABLE" : population}</p>
          <p>river_level_applied_to_solver: STORED ONLY / NOT APPLIED</p>
          {report.body?.forecast_accuracy_omitted && <p>FORECAST VS REALITY: UNAVAILABLE</p>}
          <ProvenanceBadge status={report.body?.provenance?.data_status || "PARTIAL"} />
          <div className="flex flex-wrap gap-2">
            <button type="button" className="underline" onClick={() => download("json")} aria-label="Export report JSON">
              Export JSON
            </button>
            <button type="button" className="underline" onClick={() => download("csv")} aria-label="Export report CSV">
              Export CSV
            </button>
            <button type="button" className="underline" onClick={() => download("pdf")} aria-label="Export report PDF">
              Export PDF
            </button>
            <button
              type="button"
              className="underline"
              aria-label="Share this analysis"
              onClick={() => postShare(report.id, "private").then(setShare)}
            >
              Share this analysis
            </button>
          </div>
          {share && (
            <p className="text-slate-300">
              Share {share.id}. {share.banner}
              <button type="button" className="ml-2 underline" aria-label="Revoke share" onClick={() => revokeShare(share.id).then(() => setShare({ ...share, status: "SHARE UNAVAILABLE" }))}>
                Revoke
              </button>
            </p>
          )}
        </div>
      )}
      <div className="mt-3">
        <h3 className="text-[10px] uppercase text-slate-400">Open share</h3>
        <label>
          Share id
          <input
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1"
            value={shareId}
            onChange={(event) => setShareId(event.target.value)}
            aria-label="Share identifier"
          />
        </label>
        <button
          type="button"
          className="mt-1 rounded border border-slate-600 px-2 py-1"
          onClick={() =>
            fetchShare(shareId)
              .then(setShareView)
              .catch((err) => setShareView({ available: false, status: "SHARE UNAVAILABLE", reason: err.message }))
          }
        >
          Open share
        </button>
        {shareView && (
          <div className="mt-2 rounded border border-slate-700 p-2" role="status">
            <p>{shareView.status || shareView.banner}</p>
            <p>{shareView.stale_notice}</p>
            <p>generated {shareView.generated_at || "UNAVAILABLE"}</p>
            <p>model {shareView.model_version || "UNAVAILABLE"}</p>
            <p>dataset {shareView.dataset_version || "UNAVAILABLE"}</p>
            <p>live={String(shareView.live === true)}</p>
          </div>
        )}
      </div>
      <ul className="mt-3 space-y-1 text-[10px] text-slate-500">
        {reports.map((row) => (
          <li key={row.id}>
            {row.id} · {row.kind} · {row.generated_at}
          </li>
        ))}
      </ul>
    </PanelState>
  );
}
