export default function ExploreMapControls({
  onFitRegion,
  onResetExtent,
  latitude,
  longitude,
  onOpenLayers,
  onOpenAnalysis,
  showMobileActions,
}) {
  return (
    <div className="pointer-events-auto absolute right-3 top-14 z-[1100] flex flex-col gap-1">
      <button
        type="button"
        onClick={onFitRegion}
        className="rounded-md border border-white/20 bg-slate-900/90 px-2 py-1 text-[11px] text-white"
      >
        Fit region
      </button>
      <button
        type="button"
        onClick={onResetExtent}
        className="rounded-md border border-white/20 bg-slate-900/90 px-2 py-1 text-[11px] text-white"
      >
        Reset extent
      </button>
      {Number.isFinite(latitude) && Number.isFinite(longitude) && (
        <p className="rounded-md border border-white/20 bg-slate-900/90 px-2 py-1 font-mono text-[10px] text-slate-200">
          {latitude.toFixed(5)}, {longitude.toFixed(5)}
        </p>
      )}
      {showMobileActions && (
        <>
          <button
            type="button"
            onClick={onOpenLayers}
            className="rounded-md border border-white/20 bg-slate-900/90 px-2 py-1 text-[11px] text-white lg:hidden"
          >
            Layers
          </button>
          <button
            type="button"
            onClick={onOpenAnalysis}
            className="rounded-md border border-white/20 bg-slate-900/90 px-2 py-1 text-[11px] text-white lg:hidden"
          >
            Analysis
          </button>
        </>
      )}
    </div>
  );
}
