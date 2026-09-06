import { useEffect, useState } from "react";
import { Polyline, Popup } from "react-leaflet";
import L from "leaflet";

import { fetchRivers } from "../platform/api";

export default function RiverNetworkLayer({
  cityId,
  visible,
  selectedRiverId,
  selectedSegmentId,
  topologyHighlights,
  onSelect,
}) {
  const [rivers, setRivers] = useState([]);
  const [status, setStatus] = useState("idle");

  useEffect(() => {
    if (!visible || !cityId) {
      return undefined;
    }
    let cancelled = false;
    setStatus("loading");
    fetchRivers(cityId)
      .then((data) => {
        if (cancelled) {
          return;
        }
        const rows = data.data || data.rivers || [];
        setRivers(rows);
        setStatus(
          rows.some((row) => (row.segments || []).some((seg) => (seg.coordinates || []).length >= 2))
            ? "ok"
            : "empty"
        );
      })
      .catch(() => {
        if (!cancelled) {
          setRivers([]);
          setStatus("error");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [cityId, visible]);

  if (!visible) {
    return null;
  }

  return (
    <>
      {status === "empty" && null}
      {rivers.flatMap((river) =>
        (river.segments || [])
          .filter((segment) => (segment.coordinates || []).length >= 2)
          .map((segment) => {
            const selected = selectedSegmentId && selectedSegmentId === segment.id;
            const isUpstream = (topologyHighlights?.upstream || []).includes(segment.id);
            const isDownstream = (topologyHighlights?.downstream || []).includes(segment.id);
            const reachable = (topologyHighlights?.reachable || []).includes(segment.id);
            const riverOn = selectedRiverId && selectedRiverId === river.id;
            let pathOptions = { color: "#0ea5e9", weight: 2, opacity: 0.55 };
            if (riverOn) {
              pathOptions = { color: "#38bdf8", weight: 3, opacity: 0.9 };
            }
            if (reachable) {
              pathOptions = { color: "#818cf8", weight: 3, opacity: 0.9, dashArray: "4 3" };
            }
            if (isUpstream) {
              pathOptions = { color: "#2dd4bf", weight: 4, opacity: 0.95 };
            }
            if (isDownstream) {
              pathOptions = { color: "#a78bfa", weight: 4, opacity: 0.95 };
            }
            if (selected) {
              pathOptions = { color: "#fbbf24", weight: 5, opacity: 1 };
            }
            const siblings = river.segments || [];
            const upstream = siblings.filter(
              (row) => row.to_node === segment.from_node && row.id !== segment.id
            );
            const downstream = siblings.filter(
              (row) => row.from_node === segment.to_node && row.id !== segment.id
            );
            return (
              <Polyline
                key={segment.id}
                positions={segment.coordinates.map(([lng, lat]) => [lat, lng])}
                eventHandlers={{
                  click: (event) => {
                    L.DomEvent.stopPropagation(event);
                    onSelect?.({
                      id: river.id,
                      river_id: river.id,
                      name: river.name || river.id,
                      segment_id: segment.id,
                      segment,
                      upstream: upstream.map((row) => ({
                        id: row.id,
                        from_node: row.from_node,
                        to_node: row.to_node,
                      })),
                      downstream: downstream.map((row) => ({
                        id: row.id,
                        from_node: row.from_node,
                        to_node: row.to_node,
                      })),
                      provenance: { provider: "osm-fixture", dataset: "rivers" },
                      data_status: "DEMO",
                    });
                  },
                }}
                pathOptions={pathOptions}
              >
                <Popup>
                  <div className="text-sm">
                    <p className="font-semibold">{river.name || river.id}</p>
                    <p>Segment {segment.id}</p>
                    <p>
                      {segment.from_node} → {segment.to_node}
                    </p>
                    <p className="text-xs">
                      Upstream: {upstream.length ? upstream.map((row) => row.id).join(", ") : "none listed"}
                    </p>
                    <p className="text-xs">
                      Downstream:{" "}
                      {downstream.length ? downstream.map((row) => row.id).join(", ") : "none listed"}
                    </p>
                    <p className="text-xs">Source: osm-fixture · DEMO</p>
                    <p className="text-xs">FLOW DIRECTION: UNAVAILABLE / TOPOLOGY ONLY</p>
                    <p className="text-xs">
                      {river.water_level_m == null
                        ? "WATER LEVEL: UNAVAILABLE"
                        : `WATER LEVEL: ${river.water_level_m} m`}
                    </p>
                    <p className="text-xs">
                      {river.discharge_m3s == null
                        ? "DISCHARGE: UNAVAILABLE"
                        : `DISCHARGE: ${river.discharge_m3s} m³/s`}
                    </p>
                  </div>
                </Popup>
              </Polyline>
            );
          })
      )}
    </>
  );
}
