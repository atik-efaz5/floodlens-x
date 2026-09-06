import { useEffect, useState } from "react";

import {
  deleteLocation,
  fetchLocations,
  patchLocation,
  postLocation,
  restoreLocation,
} from "./api";

function Field({ label, value }) {
  return (
    <p className="text-[11px] text-slate-300">
      <span className="text-slate-500">{label}: </span>
      {value == null || value === "" ? "UNAVAILABLE" : String(value)}
    </p>
  );
}

export default function LocationsPanel({
  cityId,
  cityName,
  latitude,
  longitude,
  zoom,
  riverId,
  layers,
  onRestore,
  visible,
}) {
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState(null);
  const [name, setName] = useState(cityName || cityId || "Saved location");
  const [confirmId, setConfirmId] = useState(null);
  const [renameId, setRenameId] = useState(null);
  const [renameValue, setRenameValue] = useState("");
  const [status, setStatus] = useState("");

  const reload = () =>
    fetchLocations()
      .then((data) => {
        setPayload(data);
        setError(null);
      })
      .catch((err) => setError(err.message));

  useEffect(() => {
    if (!visible) return undefined;
    reload();
    return undefined;
  }, [visible]);

  if (!visible) return null;

  const save = async () => {
    setStatus("");
    try {
      await postLocation({
        name: name || cityId,
        location_type: "city",
        city_id: cityId,
        river_id: riverId || undefined,
        latitude: latitude ?? undefined,
        longitude: longitude ?? undefined,
        zoom: zoom ?? undefined,
        layers: layers || undefined,
      });
      setStatus("Location saved.");
      reload();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <section className="space-y-3 text-xs text-slate-200" aria-label="My locations">
      <h2 className="text-lg font-semibold">My locations</h2>
      <p className="text-[11px] text-slate-400">
        Restores map context only. Stale results are not treated as live data.
      </p>
      <label className="block">
        Name
        <input
          className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-2 py-1"
          value={name}
          onChange={(event) => setName(event.target.value)}
          aria-label="Saved location name"
        />
      </label>
      <button type="button" className="rounded bg-sky-700 px-2 py-1 text-[11px] font-semibold" onClick={save} aria-label="Save location">
        Save location
      </button>
      {status && (
        <p className="text-emerald-200" aria-live="polite">
          {status}
        </p>
      )}
      {error && <p className="text-amber-200">{error}</p>}
      <ul className="space-y-2" role="list">
        {(payload?.cards || []).map((card) => (
          <li key={card.location_id} className="rounded border border-slate-800 bg-slate-900/70 p-2">
            <p className="font-semibold">{card.name}</p>
            <Field label="status" value={card.current_status} />
            <Field label="risk" value={card.risk} />
            <Field label="24h forecast" value={card.latest_forecast} />
            <Field label="freshness" value={card.data_freshness} />
            <Field label="alert" value={card.alert_status} />
            <Field label="updated" value={card.last_updated} />
            <div className="mt-2 flex flex-wrap gap-2">
              <button
                type="button"
                className="text-sky-300 underline"
                aria-label={`Reopen ${card.name}`}
                onClick={() =>
                  restoreLocation(card.location_id).then((ctx) => onRestore?.(ctx, card))
                }
              >
                Reopen
              </button>
              <button
                type="button"
                className="text-slate-300 underline"
                aria-label={`Rename ${card.name}`}
                onClick={() => {
                  setRenameId(card.location_id);
                  setRenameValue(card.name);
                }}
              >
                Rename
              </button>
              <button
                type="button"
                className="text-amber-200 underline"
                aria-label={`Delete ${card.name}`}
                onClick={() => setConfirmId(card.location_id)}
              >
                Delete
              </button>
            </div>
            {renameId === card.location_id && (
              <div className="mt-2">
                <label>
                  New name
                  <input
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1"
                    value={renameValue}
                    onChange={(event) => setRenameValue(event.target.value)}
                  />
                </label>
                <button
                  type="button"
                  className="mt-1 rounded bg-slate-700 px-2 py-1"
                  onClick={() =>
                    patchLocation(card.location_id, { name: renameValue }).then(() => {
                      setRenameId(null);
                      reload();
                    })
                  }
                >
                  Update
                </button>
              </div>
            )}
            {confirmId === card.location_id && (
              <div className="mt-2 rounded border border-amber-700 p-2" role="alertdialog" aria-modal="true" aria-label="Confirm delete">
                <p>Delete {card.name}? This cannot be undone from this panel.</p>
                <button
                  type="button"
                  className="mr-2 mt-1 rounded bg-amber-800 px-2 py-1"
                  onClick={() =>
                    deleteLocation(card.location_id).then(() => {
                      setConfirmId(null);
                      reload();
                    })
                  }
                >
                  Confirm delete
                </button>
                <button type="button" className="rounded border border-slate-600 px-2 py-1" onClick={() => setConfirmId(null)}>
                  Cancel
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
