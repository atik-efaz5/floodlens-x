import FloodMap from "./FloodMap";

export default function SwipeCompareMap({
  overlayA,
  overlayB,
  overlayBounds,
  mapCenter,
  metadata,
  studyBounds,
  studyCenter,
  infraLayers,
  cityId,
  swipePercent,
  onSwipeChange,
  viewport,
  onViewportChange,
  onZoomChange,
  zoomLevel,
  hasSimulation,
  onInspect,
  searchMarker,
  flyTarget,
}) {
  const clipRight = 100 - swipePercent;

  return (
    <div className="relative h-full w-full">
      <FloodMap
        mapCenter={mapCenter}
        metadata={metadata}
        studyBounds={studyBounds}
        studyCenter={studyCenter}
        overlayUrl={overlayA}
        overlayBounds={overlayBounds}
        showFloodOverlay
        infraLayers={infraLayers}
        cityId={cityId}
        inspectionPin={null}
        searchMarker={searchMarker}
        flyTarget={flyTarget}
        hasSimulation={hasSimulation}
        onInspect={onInspect}
        onZoomChange={onZoomChange}
        zoomLevel={zoomLevel}
        title="Scenario A"
        viewport={viewport}
        onViewportChange={onViewportChange}
      />
      <div
        className="absolute inset-0 overflow-hidden"
        style={{ clipPath: `inset(0 ${clipRight}% 0 0)` }}
      >
        <FloodMap
          mapCenter={mapCenter}
          metadata={metadata}
          studyBounds={studyBounds}
          studyCenter={studyCenter}
          overlayUrl={overlayB}
          overlayBounds={overlayBounds}
          showFloodOverlay
          infraLayers={infraLayers}
          cityId={cityId}
          inspectionPin={null}
          searchMarker={searchMarker}
          flyTarget={null}
          hasSimulation={false}
          onInspect={onInspect}
          onZoomChange={() => {}}
          zoomLevel={zoomLevel}
          title="Scenario B"
          viewport={viewport}
          onViewportChange={onViewportChange}
        />
      </div>
      <div className="pointer-events-auto absolute bottom-8 left-1/2 z-[1100] w-[min(420px,calc(100%-2rem))] -translate-x-1/2 rounded-xl border border-white/15 bg-slate-900/90 px-4 py-3 text-white">
        <p className="mb-2 text-xs uppercase tracking-wide text-slate-300">Swipe divider</p>
        <input
          type="range"
          min="0"
          max="100"
          value={swipePercent}
          onChange={(event) => onSwipeChange(Number(event.target.value))}
          className="w-full accent-flood-500"
        />
      </div>
    </div>
  );
}
