import { useEffect, useState } from "react";

import {
  artifactOverlayUrl,
  fetchArtifactSummary,
  postAiForecast,
  postAiSpatialForecast,
  postPhysicsForecast,
} from "./api";
import ProvenanceBadge from "./ProvenanceBadge";

const HORIZONS = [6, 12, 24, 48, 72];

export default function ForecastPanel({
  forecast,
  visible,
  cityId,
  onOverlayChange,
  onJobQueued,
  horizon: horizonProp,
  onHorizonChange,
  canWriteJobs = true,
}) {
  const [horizonLocal, setHorizonLocal] = useState(24);
  const [summary, setSummary] = useState(null);
  const [summaryError, setSummaryError] = useState(null);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [jobError, setJobError] = useState(null);
  const [localForecast, setLocalForecast] = useState(forecast);
  const horizon = horizonProp ?? horizonLocal;
  const setHorizon = (hours) => {
    setHorizonLocal(hours);
    onHorizonChange?.(hours);
  };

  useEffect(() => {
    setLocalForecast(forecast);
  }, [forecast]);

  const product = localForecast || forecast;
  const point = (product?.horizons || []).find((row) => row.horizon_hours === horizon);

  useEffect(() => {
    if (!visible) {
      return undefined;
    }
    const artifactId = point?.artifact_id || product?.artifact_id;
    if (!artifactId) {
      setSummary(null);
      setSummaryError(null);
      onOverlayChange?.(null, null);
      return undefined;
    }
    let cancelled = false;
    setLoadingSummary(true);
    fetchArtifactSummary(artifactId)
      .then((data) => {
        if (cancelled) {
          return;
        }
        setSummary(data);
        setSummaryError(null);
        onOverlayChange?.(artifactOverlayUrl(artifactId), { ...point, ...data });
      })
      .catch((err) => {
        if (!cancelled) {
          setSummary(null);
          setSummaryError(err.message);
          onOverlayChange?.(null, null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingSummary(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [visible, point?.artifact_id, product?.artifact_id, horizon, onOverlayChange]);

  if (!visible) {
    return null;
  }

  const risk = point?.risk || {};
  const runPhysics = async () => {
    setJobError(null);
    try {
      const job = await postPhysicsForecast(cityId);
      onJobQueued?.(job);
    } catch (err) {
      setJobError(err.message);
    }
  };

  const runAi = async () => {
    setJobError(null);
    try {
      const job = await postAiForecast(cityId);
      onJobQueued?.(job);
    } catch (err) {
      setJobError(err.message);
    }
  };

  const runSpatial = async () => {
    setJobError(null);
    try {
      const job = await postAiSpatialForecast(cityId);
      onJobQueued?.(job);
    } catch (err) {
      setJobError(err.message);
    }
  };

  return (
    <section className="glass-panel rounded-lg px-4 py-3 text-sm text-slate-200">
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
        Forecast (hours, not SWE time)
      </h2>
      {!product ? (
        <p className="text-slate-400">Forecast product uses meteorological hours, not solver seconds.</p>
      ) : (
        <>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <ProvenanceBadge
              status={product.provenance?.data_status || product.data_status}
              freshness={product.provenance?.freshness}
              fallbackUsed={product.provenance?.fallback_used}
            />
            <span className="text-[10px] uppercase text-slate-400">{product.model_kind || "HEURISTIC"}</span>
          </div>
          <div className="mb-2 flex flex-wrap gap-1">
            {HORIZONS.map((hours) => (
              <button
                key={hours}
                type="button"
                onClick={() => setHorizon(hours)}
                className={`rounded-full px-2 py-0.5 text-[10px] ${
                  horizon === hours ? "bg-sky-500 text-white" : "bg-slate-800 text-slate-300"
                }`}
              >
                {hours}h
              </button>
            ))}
          </div>
          {point ? (
            <div className="space-y-1 text-xs">
              <p>
                T+{horizon}h · {point.artifact_id ? "PARTIAL physics overlay" : "DEMO/heuristic hours"} · risk{" "}
                {point.risk_category || risk.category || "—"} · P {point.flood_probability ?? risk.probability ?? "—"}
              </p>
              <p>
                expected depth {point.expected_depth == null ? "UNAVAILABLE" : `${point.expected_depth} m`} ·
                flooded area {point.flooded_area_km2 == null ? "UNAVAILABLE" : `${Number(point.flooded_area_km2).toFixed(4)} km²`}
              </p>
              <p className="text-slate-400">
                model {point.model_id || product.model_id} · {point.data_status || product.data_status} · valid{" "}
                {point.valid_at || "—"}
                {point.confidence_kind ? ` · ${point.confidence_kind}` : ""}
                {point.interval
                  ? ` · interval ${point.interval[0]}–${point.interval[1]}`
                  : ""}
              </p>
              <p className="text-[11px] text-amber-200">
                6h/12h/24h/48h/72h spatial AI flood maps are UNAVAILABLE (NOT_VALIDATED). These hours are a
                meteorological product clock, not SWE, and not a validated inundation map.
              </p>
            </div>
          ) : (
            <p className="text-xs text-slate-400">No horizon point for {horizon}h.</p>
          )}
          {loadingSummary && <p className="mt-1 text-xs text-slate-400">Loading overlay summary…</p>}
          {summaryError && <p className="mt-1 text-xs text-amber-200">{summaryError}</p>}
          {summary && (
            <p className="mt-1 text-xs text-slate-400">
              Overlay max depth {summary.max_depth_m ?? "—"} m · validation {summary.validation_status || "—"}
            </p>
          )}
          <p className="mt-2 text-xs text-slate-400">{product.disclaimer}</p>
          {canWriteJobs && (
            <>
          <button
            type="button"
            onClick={runPhysics}
            className="mt-2 rounded-md bg-sky-600 px-2 py-1 text-[10px] font-semibold uppercase text-white"
          >
            Run physics forecast
          </button>
          <button
            type="button"
            onClick={runAi}
            className="ml-2 mt-2 rounded-md bg-slate-700 px-2 py-1 text-[10px] font-semibold uppercase text-white"
          >
            Request AI forecast
          </button>
          <button
            type="button"
            onClick={runSpatial}
            className="ml-2 mt-2 rounded-md bg-slate-700 px-2 py-1 text-[10px] font-semibold uppercase text-white"
          >
            Request spatial AI
          </button>
            </>
          )}
          {!canWriteJobs && (
            <p className="mt-2 text-[10px] text-slate-500">Simulation jobs: UNAVAILABLE for General role (jobs.write).</p>
          )}
            <p className="mt-1 text-[10px] text-slate-500">
            Physics is a short SWE burst, not 24h inundation. AI stays NOT_TRAINED
            until validated. After validation, 6h/12h remain UNAVAILABLE (daily GloFAS
            labels). Labels are MODELLED hydrology, not flood maps. No AI depth overlay.
            Spatial maps (8-day GFM) stay NOT_TRAINED until held-out rasters are validated;
            COMPARISON NOT YET COMPARABLE to physics.
          </p>
          {jobError && <p className="mt-1 text-xs text-amber-200">{jobError}</p>}
        </>
      )}
    </section>
  );
}
