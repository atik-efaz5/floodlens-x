import { useEffect, useState } from "react";

import {
  acknowledgeAlert,
  evaluateAlerts,
  fetchAlertHistory,
  fetchAlertMetrics,
  fetchAlerts,
  postAlert,
} from "./api";
import PanelState from "./PanelState";

export default function AlertsPanel({ cityId, locationId, visible, role }) {
  const [metrics, setMetrics] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [evaluations, setEvaluations] = useState([]);
  const [history, setHistory] = useState(null);
  const [error, setError] = useState(null);
  const [metric, setMetric] = useState("flood_probability");
  const [threshold, setThreshold] = useState("0.7");
  const [operator, setOperator] = useState("gte");
  const [channel] = useState("in-app");
  const [status, setStatus] = useState("");

  const reload = () => {
    Promise.all([fetchAlertMetrics(cityId), fetchAlerts(), evaluateAlerts(cityId)])
      .then(([catalog, listed, evals]) => {
        setMetrics(catalog.metrics || []);
        setAlerts(listed.alerts || []);
        setEvaluations(evals.evaluations || []);
        setError(null);
      })
      .catch((err) => setError(err.message));
  };

  useEffect(() => {
    if (!visible || !cityId) return undefined;
    reload();
    return undefined;
  }, [visible, cityId]);

  if (!visible) return null;

  const selectedMeta = metrics.find((row) => row.metric === metric);
  const metricBlocked = selectedMeta?.supported === false || selectedMeta?.available === false;

  const create = async () => {
    setStatus("");
    setError(null);
    try {
      await postAlert({
        city_id: cityId,
        metric,
        condition: metric,
        operator,
        threshold: metric === "risk_level" ? threshold : Number(threshold),
        channel,
        location_id: locationId || undefined,
        kind: role === "admin" ? "system" : role === "emergency" ? "operational" : role === "researcher" ? "experiment" : "personal",
      });
      setStatus("Alert saved (in-app). Email/push are not implemented.");
      reload();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <PanelState title="Alerts" state={error ? "ERROR" : "SUCCESS"} message={error}>
      <form
        className="space-y-2 text-xs"
        aria-label="Create alert"
        onSubmit={(event) => {
          event.preventDefault();
          create();
        }}
      >
        <p className="text-[11px] text-slate-400">
          Alert me when a supported metric crosses a threshold. This is not a declaration that a flood is happening.
          Not an official evacuation order.
        </p>
        <p>Location: {cityId}</p>
        <label className="block">
          Metric
          <select
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1"
            value={metric}
            onChange={(event) => setMetric(event.target.value)}
            aria-label="Alert metric"
          >
            {metrics.map((row) => (
              <option key={row.metric} value={row.metric}>
                {row.metric}
                {row.supported === false ? " (UNAVAILABLE)" : ""}
              </option>
            ))}
          </select>
        </label>
        {metricBlocked && (
          <p className="rounded border border-amber-700 px-2 py-1 text-amber-200" aria-live="polite">
            METRIC UNAVAILABLE. {selectedMeta?.reason}
          </p>
        )}
        <label className="block">
          Operator
          <select
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1"
            value={operator}
            onChange={(event) => setOperator(event.target.value)}
            aria-label="Alert operator"
          >
            <option value="gt">&gt;</option>
            <option value="gte">&gt;=</option>
            <option value="lt">&lt;</option>
            <option value="lte">&lt;=</option>
            <option value="eq">=</option>
          </select>
        </label>
        <label className="block">
          Threshold
          <input
            className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1"
            value={threshold}
            onChange={(event) => setThreshold(event.target.value)}
            aria-label="Alert threshold"
            inputMode="decimal"
            disabled={metricBlocked}
          />
        </label>
        <p>Channel: in-app (email/push prepared, not delivered)</p>
        <button
          type="submit"
          className="rounded bg-sky-700 px-2 py-1 font-semibold"
          disabled={metricBlocked}
          aria-disabled={metricBlocked}
        >
          Save alert
        </button>
      </form>
      {status && (
        <p className="mt-2 text-emerald-200" aria-live="polite">
          {status}
        </p>
      )}
      <ul className="mt-3 space-y-2">
        {alerts.map((alert) => {
          const evalRow = evaluations.find((row) => row.id === alert.id);
          return (
            <li key={alert.id} className="rounded border border-slate-800 p-2">
              <p>
                {alert.metric} {alert.operator} {alert.threshold} · {alert.state}
              </p>
              <p className="text-slate-400">
                condition {evalRow?.condition_status || "not evaluated"} · actual{" "}
                {evalRow?.actual_value == null ? "UNAVAILABLE" : evalRow.actual_value}
              </p>
              <p className="text-[10px] text-slate-500">{evalRow?.message}</p>
              <button
                type="button"
                className="mr-2 text-sky-300 underline"
                aria-label={`Acknowledge alert ${alert.id}`}
                onClick={() => acknowledgeAlert(alert.id).then(reload)}
              >
                Acknowledge
              </button>
              <button
                type="button"
                className="text-slate-300 underline"
                aria-label={`Alert history ${alert.id}`}
                onClick={() => fetchAlertHistory(alert.id).then(setHistory)}
              >
                History
              </button>
            </li>
          );
        })}
      </ul>
      {history && (
        <div className="mt-2" aria-label="Alert history">
          {(history.history || []).map((row) => (
            <p key={row.id} className="text-[10px] text-slate-400">
              {row.trigger_time} {row.metric} threshold {row.threshold} actual{" "}
              {row.actual_value == null ? "UNAVAILABLE" : row.actual_value} {row.state}
            </p>
          ))}
        </div>
      )}
    </PanelState>
  );
}
