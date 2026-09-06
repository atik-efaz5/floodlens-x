import { useState } from "react";
import { postChat, postReport } from "./api";

const TOOL_LABELS = {
  get_region: "Checking region…",
  get_current_risk: "Checking current risk…",
  explain_risk: "Explaining risk formula…",
  get_forecast: "Checking forecast…",
  explain_forecast: "Explaining heuristic forecast…",
  get_spatial_ai_status: "Checking spatial AI status…",
  get_infrastructure_risk: "Checking infrastructure exposure…",
  get_impact: "Checking impact analysis…",
  get_shelters: "Checking shelters…",
  get_planning_priorities: "Checking planning priorities…",
  run_scenario: "Running scenario…",
  compare_scenarios: "Comparing results…",
  generate_report: "Generating report…",
  share_analysis: "Creating share snapshot…",
  get_population_exposure: "Checking population exposure…",
  get_river_status: "Checking river topology…",
  get_river_forecast: "Checking river observations…",
  get_equilibrium_residual: "Reading equilibrium residual…",
  get_lake_at_rest_status: "Reading Lake-at-Rest status…",
  get_nyquist_energy: "Reading Nyquist-mode energy…",
  get_spectral_radius: "Reading spectral radius…",
  generate_research_report: "Generating research report…",
};

export default function AssistantDock({ cityId, visible, context = {}, role }) {
  const [message, setMessage] = useState("Will this area flood within 24 hours?");
  const [turns, setTurns] = useState([]);
  const [reply, setReply] = useState(null);
  const [error, setError] = useState(null);
  const [waiting, setWaiting] = useState(false);
  const [showEvidence, setShowEvidence] = useState(false);

  if (!visible) {
    return null;
  }

  const send = async () => {
    try {
      setError(null);
      setWaiting(true);
      const data = await postChat(message, cityId, context);
      setReply(data);
      setTurns((current) => [...current, { user: message, assistant: data }].slice(-8));
    } catch (err) {
      setError(err.message);
    } finally {
      setWaiting(false);
    }
  };

  const exportReport = async () => {
    try {
      const report = await postReport(cityId, {
        baselineJob: context.baseline_id,
        scenarioJob: context.scenario_id || context.selected_job,
      });
      const data = {
        reply: `Report ${report.id} generated at ${report.generated_at} using ${report.model_version}.`,
        tools_called: ["generate_report"],
        tool_results: { generate_report: report },
        generated_at: report.generated_at,
        disclaimer: "AI-generated planning support. Not an official evacuation order.",
        export: {
          timestamp: report.generated_at,
          region: cityId,
          scenario: context.scenario_id,
          model_method: report.model_version,
          evidence: [{ tool: "generate_report", job_id: report.id }],
          limitations: ["Report numbers come from backend products, not the assistant."],
        },
      };
      setReply(data);
    } catch (err) {
      setError(err.message);
    }
  };

  const shareAnalysis = async () => {
    try {
      setError(null);
      setWaiting(true);
      const data = await postChat("Share this analysis.", cityId, context);
      setReply(data);
      setTurns((current) => [...current, { user: "Share this analysis.", assistant: data }].slice(-8));
    } catch (err) {
      setError(err.message);
    } finally {
      setWaiting(false);
    }
  };

  const copyAnalysis = async () => {
    if (!reply) return;
    const exported = reply.export || {};
    const text = [
      `FloodLens-X assistant analysis`,
      `timestamp: ${exported.timestamp || reply.generated_at || "UNAVAILABLE"}`,
      `region: ${exported.region || cityId || "UNAVAILABLE"}`,
      `scenario: ${exported.scenario || "UNAVAILABLE"}`,
      `model/method: ${exported.model_method || "UNAVAILABLE"}`,
      `role: ${role || "UNAVAILABLE"}`,
      `ANSWER: ${reply.reply}`,
      `evidence: ${JSON.stringify(exported.evidence || reply.evidence || [])}`,
      `limitations: ${(exported.limitations || []).join(" ")}`,
      reply.disclaimer || "",
    ].join("\n");
    try {
      await navigator.clipboard.writeText(text);
    } catch (err) {
      setError(err.message);
    }
  };

  const activity = waiting
    ? ["Waiting for backend…"]
    : (reply?.activity || []).map((row) => row.label || TOOL_LABELS[row.tool] || row.tool);

  return (
    <div className="pointer-events-auto absolute bottom-28 right-6 z-[1000] w-96 rounded-xl border border-slate-700 bg-slate-900/95 p-4 text-slate-100 shadow-xl" aria-label="AI assistant">
      <p className="text-xs uppercase tracking-wide text-slate-400">AI assistant (tool-calling)</p>
      <p className="text-[10px] text-slate-500">
        Context: {context.selected_region || cityId || "UNAVAILABLE"} · river {context.selected_river || "UNAVAILABLE"} · job {context.selected_job || "UNAVAILABLE"}
      </p>
      <div className="sr-only" aria-live="polite">
        {waiting ? "Waiting for backend tools." : reply ? "Assistant response ready." : ""}
      </div>
      <textarea
        value={message}
        onChange={(event) => setMessage(event.target.value)}
        aria-label="Assistant question"
        className="mt-2 h-16 w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm"
      />
      <div className="mt-2 flex flex-wrap gap-2">
        <button type="button" onClick={send} className="rounded-md bg-flood-500 px-3 py-1 text-sm">
          Ask
        </button>
        <button type="button" onClick={exportReport} className="rounded-md bg-slate-700 px-3 py-1 text-sm">
          Export report
        </button>
        <button type="button" onClick={shareAnalysis} className="rounded-md bg-slate-700 px-3 py-1 text-sm">
          Share analysis
        </button>
        <button type="button" onClick={copyAnalysis} className="rounded-md bg-slate-800 px-3 py-1 text-sm" disabled={!reply}>
          Copy analysis
        </button>
      </div>
      {error && <p className="mt-2 text-xs text-red-300">{error}</p>}
      {activity.length > 0 && (
        <ul className="mt-2 text-[10px] text-sky-200" aria-label="Tool activity">
          {activity.map((label) => (
            <li key={label}>{label}</li>
          ))}
        </ul>
      )}
      {reply && (
        <div className="mt-2 max-h-48 overflow-y-auto text-xs text-slate-300">
          {turns.length > 0 && (
            <ol className="mb-2 space-y-1 text-[10px] text-slate-400">
              {turns.map((turn, index) => (
                <li key={`${turn.user}-${index}`}>
                  <p>User: {turn.user}</p>
                  <p>Assistant: {(turn.assistant?.reply || "").slice(0, 180)}</p>
                </li>
              ))}
            </ol>
          )}
          <p>{reply.reply}</p>
          <p className="mt-1 text-slate-500">Tools: {(reply.tools_called || []).join(", ")}</p>
          {(reply.authorized_denied || []).length > 0 && (
            <p className="text-amber-200">Denied tools: {reply.authorized_denied.join(", ")}</p>
          )}
          {reply.tool_results?.run_scenario?.status && (
            <p>Scenario/job status: {reply.tool_results.run_scenario.status} {reply.tool_results.run_scenario.id || ""}</p>
          )}
          <button
            type="button"
            className="mt-1 text-[11px] text-sky-300 underline"
            onClick={() => setShowEvidence((value) => !value)}
            aria-expanded={showEvidence}
          >
            {showEvidence ? "Hide evidence / sources" : "Evidence / sources"}
          </button>
          {showEvidence && (
            <div className="mt-1 rounded border border-slate-800 p-2 text-[10px]">
              {(reply.evidence || []).map((row) => (
                <p key={`${row.tool}-${row.job_id || ""}`}>
                  {row.tool}: source={row.source || "UNAVAILABLE"} timestamp={row.timestamp || "UNAVAILABLE"} status={row.data_status || "UNAVAILABLE"} model={row.model || "UNAVAILABLE"} job={row.job_id || "none"}
                </p>
              ))}
              {(reply.sources || []).map((row) => (
                <p key={row.title}>
                  Source {row.title}: {row.data_status} {row.url ? row.url : "(no URL invented)"}
                </p>
              ))}
            </div>
          )}
          <p className="text-amber-200">{reply.disclaimer}</p>
        </div>
      )}
    </div>
  );
}
