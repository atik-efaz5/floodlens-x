import { useEffect, useMemo, useState } from "react";

import {
  fetchResearchAi,
  fetchResearchExperiment,
  fetchResearchExperiments,
  fetchResearchInventory,
  fetchResearchOverview,
  postResearchReport,
  runResearchSuite,
} from "./api";
import PanelState from "./PanelState";

const NAV = [
  { id: "overview", label: "Overview" },
  { id: "lake_at_rest", label: "Lake at Rest" },
  { id: "parabolic_bowl", label: "Parabolic Bowl" },
  { id: "conservation", label: "Conservation" },
  { id: "spectral", label: "Spectral Analysis" },
  { id: "perturbation", label: "Perturbation" },
  { id: "flux_source", label: "Flux / Source" },
  { id: "interface_balance", label: "Interface Balance" },
  { id: "jacobian", label: "Numerical Jacobian" },
  { id: "long_term", label: "Long-Term Stability" },
  { id: "ai", label: "AI Experiments" },
  { id: "provenance", label: "Provenance" },
];

function sci(value) {
  if (value == null || value === "") return "UNAVAILABLE";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "UNAVAILABLE";
    return value.toExponential(4);
  }
  return String(value);
}

function StatusText({ status }) {
  const label = status || "NOT_RUN";
  const failed = /FAIL/i.test(label);
  return (
    <span
      className={`inline-block rounded border px-2 py-0.5 text-[10px] font-semibold uppercase ${
        failed ? "border-red-500 bg-red-950 text-red-100" : "border-slate-600 bg-slate-800 text-slate-100"
      }`}
      role="status"
    >
      {label}
    </span>
  );
}

function Sparkline({ values, label }) {
  const series = (values || []).filter((v) => v != null && Number.isFinite(Number(v))).map(Number);
  if (!series.length) {
    return <p className="text-[11px] text-slate-500">{label}: UNAVAILABLE</p>;
  }
  const max = Math.max(...series, 1e-30);
  const min = Math.min(...series, 0);
  const span = max - min || 1;
  return (
    <div>
      <p className="sr-only">
        {label}: {series.map((v) => v.toExponential(3)).join(", ")}
      </p>
      <svg viewBox="0 0 160 36" className="h-9 w-full text-sky-300" role="img" aria-label={label}>
        {series.map((v, i) => {
          const x = (i / Math.max(series.length - 1, 1)) * 150 + 5;
          const y = 32 - ((v - min) / span) * 28;
          return <circle key={i} cx={x} cy={y} r="1.6" fill="currentColor" />;
        })}
      </svg>
    </div>
  );
}

function JsonBlock({ data }) {
  const text = JSON.stringify(data, null, 2);
  return (
    <div className="mt-2">
      <button
        type="button"
        className="mr-2 text-[10px] underline"
        onClick={() => navigator.clipboard?.writeText(text)}
      >
        Copy diagnostics
      </button>
      <a
        className="text-[10px] underline"
        href={`data:application/json,${encodeURIComponent(text)}`}
        download={`${data?.experiment_id || "diagnostics"}.json`}
      >
        Download artifact
      </a>
      <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-all rounded bg-slate-950 p-2 text-[10px] text-slate-400">
        {text}
      </pre>
    </div>
  );
}

export default function ResearchCenter({ visible, role }) {
  const [tab, setTab] = useState("overview");
  const [overview, setOverview] = useState(null);
  const [inventory, setInventory] = useState(null);
  const [result, setResult] = useState(null);
  const [experiments, setExperiments] = useState([]);
  const [ai, setAi] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [steps, setSteps] = useState(50);
  const [amplitude, setAmplitude] = useState("1e-12");
  const [ifaceI, setIfaceI] = useState("8");
  const [ifaceJ, setIfaceJ] = useState("8");
  const [report, setReport] = useState(null);

  const reloadMeta = () => {
    fetchResearchOverview().then(setOverview).catch(() => undefined);
    fetchResearchExperiments()
      .then((data) => setExperiments(data.experiments || []))
      .catch(() => undefined);
    fetchResearchInventory().then(setInventory).catch(() => undefined);
    fetchResearchAi().then(setAi).catch(() => undefined);
  };

  useEffect(() => {
    if (!visible) return undefined;
    reloadMeta();
    return undefined;
  }, [visible, result]);

  const run = async (suite, extra = {}) => {
    setLoading(true);
    setError(null);
    try {
      const data = await runResearchSuite(suite, extra);
      setResult(data);
      if (data.status && /FAIL/i.test(data.status)) {
        setError(data.status);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const reopen = async (id) => {
    const data = await fetchResearchExperiment(id);
    setResult(data);
    const match = NAV.find((row) => row.id === data.suite || (data.suite === "long_term_stability" && row.id === "long_term"));
    if (match) setTab(match.id);
  };

  const generate = async () => {
    const data = await postResearchReport(result?.experiment_id);
    setReport(data);
  };

  const failedBanner = result && (/FAIL/i.test(result.status) || result.passed === false);

  const provenance = result?.provenance || overview;

  const config = useMemo(() => provenance?.config || result?.provenance?.config, [provenance, result]);

  if (!visible) return null;

  return (
    <section className="space-y-3 text-xs text-slate-200" aria-label="Research center">
      <h2 className="text-lg font-semibold">Research Center</h2>
      <p className="text-[11px] text-slate-400">
        Scientific diagnostics on the existing SWE solver. SIMULATED. Spatial AI remains NOT_VALIDATED.
        Local Jacobian spectral radius is not proof of global stability. Pause is UNAVAILABLE.
      </p>
      <nav className="flex flex-wrap gap-1" aria-label="Research diagnostics">
        {NAV.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`rounded px-2 py-1 text-[10px] uppercase ${tab === item.id ? "bg-sky-800 text-white" : "bg-slate-800"}`}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>
      {failedBanner && (
        <p className="rounded border border-red-600 bg-red-950/70 px-2 py-2 font-semibold text-red-100" role="alert">
          {result.failed_at_step ? `FAILED AT STEP ${result.failed_at_step}` : result.status || "VALIDATION FAILED"}
        </p>
      )}
      {error && !failedBanner && (
        <p className="text-amber-200" role="alert">
          {error}
        </p>
      )}
      {loading && <p className="text-slate-400">Running diagnostic…</p>}

      {tab === "overview" && (
        <PanelState title="Validation overview" state="SUCCESS">
          <p>Solver {overview?.solver_version || "UNAVAILABLE"}</p>
          <p>Experiment {overview?.experiment_id || "NOT_RUN"}</p>
          <p>Dataset {overview?.dataset}</p>
          <p>Timestamp {overview?.run_timestamp || "NOT_RUN"}</p>
          <p>
            Status <StatusText status={overview?.status} />
          </p>
          <ul className="mt-2 grid grid-cols-1 gap-2">
            {(overview?.cards || []).map((card) => (
              <li key={card.id} className="rounded border border-slate-800 p-2">
                <p className="font-semibold">{card.id}</p>
                <StatusText status={card.status} />
                <p>value {sci(card.value)}</p>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[11px] text-slate-500">{overview?.physics_vs_ai?.label}</p>
        </PanelState>
      )}

      {tab === "lake_at_rest" && (
        <PanelState title="Lake-at-Rest" state="SUCCESS">
          <button type="button" className="rounded bg-sky-800 px-2 py-1" onClick={() => run("lake_at_rest")}>
            Run
          </button>
          <button type="button" className="ml-2 rounded border border-slate-600 px-2 py-1" onClick={() => setResult(null)}>
            Reset
          </button>
          <p className="mt-1 text-slate-500">Pause: UNAVAILABLE</p>
          {result?.suite === "lake_at_rest" && (
            <div className="mt-2 space-y-1">
              <StatusText status={result.status} />
              <p>Initial mass {sci(result.initial_state?.mass_m3)} m³</p>
              <p>Final mass {sci(result.final_state?.mass_m3)} m³</p>
              <p>Velocity max {sci(result.final_state?.max_velocity_mps)} m/s</p>
              <p>Momentum residual {sci(result.momentum_residual)} (tol {sci(result.tolerance?.momentum_residual)})</p>
              <p>
                Equilibrium L∞ {sci(result.equilibrium_residual?.Linf)} · L2 {sci(result.equilibrium_residual?.L2)} · L1{" "}
                {sci(result.equilibrium_residual?.L1)}
              </p>
              <p className="text-slate-500">{result.equilibrium_residual?.norm_definition}</p>
              <p>dt {sci(result.cfl?.dt_s)} s · CFL max {sci(result.cfl?.cfl_max)}</p>
              <p className="text-slate-500">{result.cfl?.note}</p>
              <JsonBlock data={result} />
            </div>
          )}
        </PanelState>
      )}

      {tab === "parabolic_bowl" && (
        <PanelState title="Parabolic bowl" state="SUCCESS">
          <button type="button" className="rounded bg-sky-800 px-2 py-1" onClick={() => run("parabolic_bowl")}>
            Run
          </button>
          <button type="button" className="ml-2 rounded border border-slate-600 px-2 py-1" onClick={() => setResult(null)}>
            Reset
          </button>
          <p>Pause: UNAVAILABLE</p>
          {result?.suite === "parabolic_bowl" && (
            <div className="mt-2 space-y-1">
              <StatusText status={result.status} />
              <p>Free-surface max {sci(result.final_state?.free_surface_max_m)} m</p>
              <p>Depth max {sci(result.final_state?.max_depth_m)} m</p>
              <p>Velocity max {sci(result.max_speed)} m/s</p>
              <p>Mass {sci(result.conservation?.mass_final)} m³</p>
              <p>dt {sci(result.cfl?.dt_s)} · CFL {sci(result.cfl?.cfl_max)}</p>
              <JsonBlock data={result} />
            </div>
          )}
        </PanelState>
      )}

      {tab === "conservation" && (
        <PanelState title="Conservation" state="SUCCESS">
          <button type="button" className="rounded bg-sky-800 px-2 py-1" onClick={() => run("conservation")}>
            Run
          </button>
          {result?.conservation && (
            <table className="mt-2 w-full text-left">
              <caption className="sr-only">Mass conservation</caption>
              <thead>
                <tr>
                  <th>Quantity</th>
                  <th>Value</th>
                  <th>Units</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Mass initial</td>
                  <td>{sci(result.conservation.mass_initial)}</td>
                  <td>m³</td>
                </tr>
                <tr>
                  <td>Mass final</td>
                  <td>{sci(result.conservation.mass_final)}</td>
                  <td>m³</td>
                </tr>
                <tr>
                  <td>Mass error</td>
                  <td>{sci(result.conservation.mass_error)}</td>
                  <td>relative</td>
                </tr>
                <tr>
                  <td>Momentum residual</td>
                  <td>{sci(result.momentum_residual)}</td>
                  <td>m²/s</td>
                </tr>
              </tbody>
            </table>
          )}
        </PanelState>
      )}

      {tab === "spectral" && (
        <PanelState title="Spectral analysis" state="SUCCESS">
          <button type="button" className="rounded bg-sky-800 px-2 py-1" onClick={() => run("spectral")}>
            Run
          </button>
          {(result?.spectral || result?.suite === "spectral") && (
            <div className="mt-2 space-y-1">
              <p>Nyquist-mode energy {sci(result.nyquist_mode_energy || result.spectral?.nyquist_mode_energy)}</p>
              <p>Nyquist energy ratio {sci(result.nyquist_energy_ratio || result.spectral?.nyquist_energy_ratio)}</p>
              <p>Anti-symmetry ratio {sci(result.anti_symmetry_ratio || result.spectral?.anti_symmetry_ratio)}</p>
              <p>UNSTABLE classified: {String(result.unstable_classified || result.spectral?.unstable_classified || false)}</p>
              <Sparkline
                label="Nyquist energy ratio versus step"
                values={result.nyquist_energy_ratio_series || result.spectral?.nyquist_energy_ratio_series}
              />
              <p className="text-slate-500">{result.unstable_reason || result.spectral?.unstable_reason}</p>
            </div>
          )}
        </PanelState>
      )}

      {tab === "perturbation" && (
        <PanelState title="Perturbation testing" state="SUCCESS">
          <label>
            Amplitude
            <select
              aria-label="Perturbation amplitude"
              className="ml-2 bg-slate-900"
              value={amplitude}
              onChange={(event) => setAmplitude(event.target.value)}
            >
              <option value="1e-15">1e-15</option>
              <option value="1e-12">1e-12</option>
              <option value="1e-9">1e-9</option>
            </select>
          </label>
          <button
            type="button"
            className="ml-2 rounded bg-sky-800 px-2 py-1"
            onClick={() => run("perturbation", { amplitude: Number(amplitude) })}
          >
            Run
          </button>
          {result?.suite === "perturbation" && (
            <div className="mt-2 space-y-1">
              <p>Initial amplitude {sci(result.initial_amplitude)}</p>
              <p>Final amplitude {sci(result.final_amplitude)}</p>
              <p>Growth factor {sci(result.growth_factor)}</p>
              <p>OBSERVED GROWTH {sci(result.observed_growth)}</p>
              <p>INTERPRETATION {result.interpretation}</p>
              <Sparkline label="Growth curve" values={result.growth_curve} />
            </div>
          )}
        </PanelState>
      )}

      {tab === "flux_source" && (
        <PanelState title="Flux versus topographic source" state="SUCCESS">
          <button type="button" className="rounded bg-sky-800 px-2 py-1" onClick={() => run("flux_source")}>
            Run
          </button>
          {result?.suite === "flux_source" && (
            <div className="mt-2 space-y-1">
              <p>Flux divergence L∞ {sci(result.flux_divergence_norms?.Linf)}</p>
              <p>Topographic source L∞ {sci(result.topographic_source_norms?.Linf)}</p>
              <p>Combined RHS L∞ {sci(result.combined_rhs_norms?.Linf)}</p>
              <p className="text-slate-500">{result.note}</p>
            </div>
          )}
        </PanelState>
      )}

      {tab === "interface_balance" && (
        <PanelState title="Interface balance" state="SUCCESS">
          <label>
            i
            <input aria-label="Interface i" className="ml-1 w-12 bg-slate-900" value={ifaceI} onChange={(e) => setIfaceI(e.target.value)} />
          </label>
          <label className="ml-2">
            j
            <input aria-label="Interface j" className="ml-1 w-12 bg-slate-900" value={ifaceJ} onChange={(e) => setIfaceJ(e.target.value)} />
          </label>
          <button
            type="button"
            className="ml-2 rounded bg-sky-800 px-2 py-1"
            onClick={() => run("interface_balance", { i: Number(ifaceI), j: Number(ifaceJ), direction: "x" })}
          >
            Inspect face
          </button>
          {result?.interface && (
            <div className="mt-2 space-y-1">
              <p>Left {result.interface.left_state?.map(sci).join(", ")}</p>
              <p>Right {result.interface.right_state?.map(sci).join(", ")}</p>
              <p>Reconstructed L {result.interface.reconstructed_left?.map(sci).join(", ")}</p>
              <p>Pressure flux {sci(result.interface.pressure_flux)}</p>
              <p>Topographic source {result.interface.topographic_source?.map(sci).join(", ")}</p>
              <p>Combined residual {result.interface.combined_residual?.map(sci).join(", ")}</p>
            </div>
          )}
        </PanelState>
      )}

      {tab === "jacobian" && (
        <PanelState title="Numerical Jacobian" state="SUCCESS">
          <button type="button" className="rounded bg-sky-800 px-2 py-1" onClick={() => run("jacobian")}>
            Run
          </button>
          <p className="mt-2 rounded border border-amber-700 bg-amber-950/40 p-2 text-[11px]" role="note">
            LOCAL JACOBIAN SPECTRAL RADIUS IS NOT BY ITSELF PROOF OF GLOBAL LONG-TERM STABILITY.
          </p>
          {result?.suite === "jacobian" && (
            <div className="mt-2 space-y-1">
              <p>Spectral radius {sci(result.spectral_radius)}</p>
              <p>Eigenvalues (real) {result.eigenvalues_real?.map(sci).join(", ")}</p>
              <p>Global stability proof: {String(result.global_stability_proof)}</p>
            </div>
          )}
        </PanelState>
      )}

      {tab === "long_term" && (
        <PanelState title="Long-term stability" state="SUCCESS">
          <label>
            Steps
            <select aria-label="Long-term steps" className="ml-2 bg-slate-900" value={steps} onChange={(e) => setSteps(Number(e.target.value))}>
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value={500}>500</option>
            </select>
          </label>
          <button type="button" className="ml-2 rounded bg-sky-800 px-2 py-1" onClick={() => run("long_term", { steps })}>
            Run
          </button>
          {result?.suite === "long_term_stability" && (
            <div className="mt-2 space-y-1">
              <StatusText status={result.status} />
              {result.failed_at_step != null && <p role="alert">FAILED AT STEP {result.failed_at_step}</p>}
              <p>Mass relative error {sci(result.mass_conservation?.relative_error)}</p>
              <p>Momentum drift {sci(result.momentum_drift)}</p>
              <p>Negative depth {String(result.negative_depth)}</p>
              <p>NaN/Inf {String(result.nan_inf)}</p>
              <p>Max velocity {sci(result.max_velocity)} m/s</p>
              <p>Max depth {sci(result.max_depth)} m</p>
              <Sparkline label="Nyquist energy ratio" values={result.nyquist_energy_ratio_series} />
            </div>
          )}
        </PanelState>
      )}

      {tab === "ai" && (
        <PanelState title="AI experiment center" state="SUCCESS">
          <p>Track A: {ai?.track_a?.status} — {ai?.track_a?.limitations}</p>
          <p>Target B: {ai?.target_b?.status} — NOT TRAINED</p>
          <p>Spatial AI: {ai?.spatial_ai?.status} · API {ai?.spatial_ai?.api}</p>
          <p>AOI GBDT: {ai?.aoi_gbdt?.status} — {ai?.aoi_gbdt?.limitations}</p>
          <p>Uncertainty: {ai?.uncertainty?.status}</p>
          <p className="mt-2 font-semibold">{ai?.physics_vs_ai?.label}</p>
          <ul>
            {(ai?.physics_vs_ai?.reasons || []).map((row) => (
              <li key={row}>{row}</li>
            ))}
          </ul>
          <p>Model training: {ai?.model_training}</p>
        </PanelState>
      )}

      {tab === "provenance" && (
        <PanelState title="Provenance and configuration" state="SUCCESS">
          <p>Source {provenance?.source || result?.provenance?.source || "UNAVAILABLE"}</p>
          <p>Solver {result?.solver_version || overview?.solver_version}</p>
          <p>Experiment {result?.experiment_id || "NOT_RUN"}</p>
          <p>Config hash {result?.config_hash || "UNAVAILABLE"}</p>
          <p>Timestamp {result?.timestamp || "NOT_RUN"}</p>
          <p>Dataset {(result?.provenance || {}).dataset_version || "synthetic-parabolic-bowl"}</p>
          {config && (
            <ul className="mt-2">
              {Object.entries(config).map(([key, value]) => (
                <li key={key}>
                  {key}: {String(value)}
                </li>
              ))}
            </ul>
          )}
          <p className="mt-2">Random seed: UNAVAILABLE (deterministic synthetic IC)</p>
          <p>Pause: UNAVAILABLE</p>
        </PanelState>
      )}

      <div className="rounded border border-slate-800 p-2">
        <p className="text-[10px] uppercase text-slate-500">Experiments</p>
        <ul>
          {experiments.map((row) => (
            <li key={row.experiment_id}>
              <button type="button" className="underline" onClick={() => reopen(row.experiment_id)}>
                Reopen {row.suite} {row.experiment_id}
              </button>{" "}
              <StatusText status={row.status} />
            </li>
          ))}
        </ul>
        <button type="button" className="mt-2 rounded bg-slate-700 px-2 py-1" onClick={generate} disabled={!result} aria-label="Generate research report">
          Generate research report
        </button>
        {report && (
          <p className="mt-1">
            Report {report.id} · {report.body?.pass_fail} · SNAPSHOT GENERATED AT {report.snapshot_time}
          </p>
        )}
        {role === "general" && <p>Experimental controls are restricted.</p>}
      </div>
      {inventory && (
        <p className="text-[10px] text-slate-600">{inventory.diagnostics?.length} diagnostics inventoried.</p>
      )}
    </section>
  );
}
