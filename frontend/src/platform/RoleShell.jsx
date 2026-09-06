import { useEffect, useMemo, useState } from "react";

const ROLES = [
  { id: "general", label: "General" },
  { id: "emergency", label: "Emergency" },
  { id: "researcher", label: "Researcher" },
  { id: "admin", label: "Admin" },
];

const NAV = [
  { id: "explore", label: "Explore", roles: ["general", "emergency", "researcher", "admin"] },
  { id: "river", label: "River", roles: ["general", "emergency", "researcher", "admin"] },
  { id: "forecast", label: "Forecast", roles: ["general", "emergency", "researcher", "admin"] },
  { id: "simulation", label: "Simulation", roles: ["emergency", "researcher", "admin"] },
  { id: "impact", label: "Impact", roles: ["general", "emergency", "researcher", "admin"] },
  { id: "history", label: "History", roles: ["general", "emergency", "researcher", "admin"] },
  { id: "research", label: "Research", roles: ["researcher", "admin"] },
  { id: "reports", label: "Reports", roles: ["general", "emergency", "researcher", "admin"] },
  { id: "locations", label: "Locations", roles: ["general", "emergency", "researcher", "admin"] },
  { id: "alerts", label: "Alerts", roles: ["general", "emergency", "researcher", "admin"] },
  { id: "admin", label: "Admin", roles: ["admin"] },
];

export default function RoleShell({
  children,
  activeView,
  onViewChange,
  cityName,
  freshness,
  searchSlot,
  onRoleChange,
}) {
  const [role, setRole] = useState(() => localStorage.getItem("floodlens_role") || "general");
  const [now, setNow] = useState(() => new Date().toISOString());

  useEffect(() => {
    localStorage.setItem("floodlens_role", role);
    onRoleChange?.(role);
  }, [role, onRoleChange]);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date().toISOString()), 30000);
    return () => window.clearInterval(timer);
  }, []);

  const items = useMemo(() => NAV.filter((item) => item.roles.includes(role)), [role]);

  useEffect(() => {
    if (!items.some((item) => item.id === activeView)) {
      onViewChange?.("explore");
    }
  }, [items, activeView, onViewChange]);

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-slate-950">
      <a
        href="#command-map"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-[2000] focus:rounded focus:bg-sky-600 focus:px-3 focus:py-2 focus:text-white"
      >
        Skip to map
      </a>
      <div className="z-[1200] border-b border-amber-500/40 bg-amber-500/15 px-4 py-2 text-center text-xs text-amber-100">
        DEMO / SIMULATED DATA is labeled per layer. Freshness never shows LIVE for simulated products.
        Role switcher is a demo IdP, not hidden admin access.
      </div>
      <header className="z-[1200] grid grid-cols-[auto_1fr_auto] items-center gap-3 border-b border-slate-800 bg-slate-950/90 px-4 py-2 text-slate-100">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.25em] text-flood-100">
            FloodLens-X
          </p>
          <p className="text-sm text-slate-300">
            Command Center · {cityName || "Select a city"}
          </p>
          <p className="text-[10px] text-slate-500">
            {now} · freshness {freshness || "see provenance"}
          </p>
        </div>
        <div className="flex min-w-0 flex-col items-center gap-2">
          {searchSlot}
          <nav className="flex max-w-full flex-wrap justify-center gap-1 overflow-x-auto sm:flex-nowrap" aria-label="Command center views">
            {items.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => onViewChange(item.id)}
                aria-current={activeView === item.id ? "page" : undefined}
                className={`rounded-full px-3 py-1 text-xs ${
                  activeView === item.id
                    ? "bg-flood-500 text-white"
                    : "bg-slate-800 text-slate-300 hover:bg-slate-700"
                }`}
              >
                {item.label}
              </button>
            ))}
          </nav>
        </div>
        <label className="flex items-center gap-2 text-xs text-slate-400">
          DEMO role
          <select
            value={role}
            onChange={(event) => setRole(event.target.value)}
            aria-label="Role"
            className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
          >
            {ROLES.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
      </header>
      <div className="flex min-h-0 flex-1">{children}</div>
    </div>
  );
}
