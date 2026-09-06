import { formatTime } from "../constants";

export default function TimePlaybackBar({
  enabled,
  currentTime,
  duration,
  timeIndex = 0,
  availableTimes = [],
  isPlaying,
  isCollapsed,
  onToggleCollapse,
  onPlayPause,
  onReset,
  onScrub,
}) {
  if (!enabled) {
    return null;
  }

  const discrete = availableTimes.length > 0;
  const maxIndex = Math.max(availableTimes.length - 1, 0);

  return (
    <div className="pointer-events-auto absolute bottom-6 left-1/2 z-[1000] w-[min(720px,calc(100%-2rem))] -translate-x-1/2">
      <div className="rounded-2xl border border-white/15 bg-slate-900/90 p-4 text-white shadow-2xl backdrop-blur">
        <div className="mb-3 flex items-center justify-between gap-3">
          <p className="text-sm font-semibold">Simulation Playback</p>
          <button
            type="button"
            onClick={onToggleCollapse}
            className="rounded-md px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
          >
            {isCollapsed ? "Expand" : "Collapse"}
          </button>
        </div>

        {!isCollapsed && (
          <>
            <div className="mb-3 flex items-center gap-3">
              <button
                type="button"
                onClick={onPlayPause}
                className="rounded-lg bg-flood-700 px-4 py-2 text-sm font-semibold hover:bg-flood-500"
              >
                {isPlaying ? "Pause" : "Play"}
              </button>
              <button
                type="button"
                onClick={onReset}
                className="rounded-lg border border-slate-600 px-4 py-2 text-sm hover:bg-slate-800"
              >
                Reset
              </button>
              <p className="ml-auto text-sm text-slate-200">
                Time: {formatTime(currentTime)} / {formatTime(duration)}
                {discrete ? ` · ${availableTimes.length} snapshots` : ""}
              </p>
            </div>

            <input
              type="range"
              min="0"
              max={discrete ? maxIndex : duration}
              step={discrete ? 1 : duration / 20}
              value={discrete ? timeIndex : currentTime}
              onChange={(event) => onScrub(event.target.value)}
              className="w-full accent-flood-500"
            />
          </>
        )}
      </div>
    </div>
  );
}
