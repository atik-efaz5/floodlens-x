import { useEffect, useState } from "react";

import { fetchCommand, fetchHealth } from "./api";
import PanelState from "./PanelState";
import ProvenanceBadge from "./ProvenanceBadge";

export default function DataHealthPanel({ cityId, visible }) {
  const [command, setCommand] = useState(null);
  const [health, setHealth] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!visible || !cityId) {
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    Promise.all([fetchCommand(cityId), fetchHealth()])
      .then(([cmd, hl]) => {
        if (!cancelled) {
          setCommand(cmd);
          setHealth(hl);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [cityId, visible]);

  if (!visible) {
    return null;
  }

  let state = "SUCCESS";
  if (loading) state = "LOADING";
  else if (error) state = "ERROR";

  return (
    <PanelState title="System vs data health" state={state} message={error}>
      {command && (
        <div className="space-y-1 text-xs text-slate-300">
          <p>
            Command snapshot risk {command.current_risk} · alerts {command.alerts_active ?? 0}
          </p>
          <p className="text-amber-200">{command.disclaimer}</p>
          <p>POPULATION EXPOSURE: {command.population_exposed == null ? "UNAVAILABLE" : command.population_exposed}</p>
          <p>expected depth: {command.expected_depth_m == null ? "UNAVAILABLE" : command.expected_depth_m}</p>
          <ul className="list-disc pl-4 text-[11px] text-slate-500">
            {(command.unavailable || []).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}
      {health && (
        <div className="mt-2 space-y-1 text-[11px] text-slate-400">
          <p>
            SYSTEM HEALTH {health.system?.status || health.status || "ok"} · queue{" "}
            {health.system?.queue || health.queue || "UNAVAILABLE"}
          </p>
          <p>
            DATA AVAILABILITY {health.data?.status || "UNAVAILABLE"} · process health is not catalog
            completeness
          </p>
          <ProvenanceBadge status="PARTIAL" />
        </div>
      )}
    </PanelState>
  );
}
