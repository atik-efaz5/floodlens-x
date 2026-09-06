import { useCallback, useEffect, useMemo, useState } from "react";

import { fetchScenarioMetadata, inspectCell, runScenario, compareScenarios, fetchScenarioSnapshot } from "./api";
import ComparisonPanel from "./components/ComparisonPanel";
import CitySelector from "./components/CitySelector";
import FloodMap from "./components/FloodMap";
import InspectionCard from "./components/InspectionCard";
import LocationSearchBar from "./components/LocationSearchBar";
import ScenarioPresets from "./components/ScenarioPresets";
import SwipeCompareMap from "./components/SwipeCompareMap";
import TimePlaybackBar from "./components/TimePlaybackBar";
import {
  DEFAULT_PARAMS,
  FLOOD_LAYER_OPTIONS,
  INFRA_LAYER_OPTIONS,
} from "./constants";
import { useScenarioComparison } from "./hooks/useScenarioComparison";
import { useTimeAnimation } from "./hooks/useTimeAnimation";
import { buildOverlayFromSamples, sampleRasterGrid, buildArrayOverlay } from "./utils/raster";
import { isWithinCityBounds, selectSearchZoom } from "./utils/locationSearch";
import { fetchCities, fetchCity } from "./services/cityRegistry";
import RoleShell from "./platform/RoleShell";
import StatusPanel from "./platform/StatusPanel";
import ForecastPanel from "./platform/ForecastPanel";
import DataSourcesPanel from "./platform/DataSourcesPanel";
import AssistantDock from "./platform/AssistantDock";
import JobProgressPanel from "./platform/JobProgressPanel";
import RiverForecastPanel from "./platform/RiverForecastPanel";
import ModelStatusPanel from "./platform/ModelStatusPanel";
import ScenarioJobsPanel from "./platform/ScenarioJobsPanel";
import AlertsPanel from "./platform/AlertsPanel";
import LocationsPanel from "./platform/LocationsPanel";
import ImpactPanel from "./platform/ImpactPanel";
import JobsListPanel from "./platform/JobsListPanel";
import ForecastTimeline from "./platform/ForecastTimeline";
import DataHealthPanel from "./platform/DataHealthPanel";
import ResearchCenter from "./platform/ResearchCenter";
import AdminCenter from "./platform/AdminCenter";
import CapabilityMatrix from "./platform/CapabilityMatrix";
import ReportsPanel from "./platform/ReportsPanel";
import { compareJobs, fetchHistoryEvent, fetchHistoryEvents, fetchHistoryCompare, fetchImpact, fetchImpactEvacuation, fetchImpactInfrastructure, fetchImpactResources, fetchImpactShelters, fetchInfrastructure, fetchJob, fetchModelPerformance, fetchRainfall, fetchTerrain, fetchRiverNeighbors, fetchRiverObservations, fetchRiverOverview, fetchRivers, fetchRiverSegment, fetchScenarioBaseline, fetchScenarioCapabilities, fetchScenarioDifference, fetchScenarioHistory, fetchScenarioWorkspace, fetchStatus, postHistoryReport, postReport, postScenarioJob, artifactOverlayUrl } from "./platform/api";
import ExploreLayerManager from "./explore/ExploreLayerManager";
import ExploreMapControls from "./explore/ExploreMapControls";
import ExploreTimeline from "./explore/ExploreTimeline";
import FreshnessBar from "./explore/FreshnessBar";
import InfraFilterBar from "./explore/InfraFilterBar";
import SelectedAreaPanel from "./explore/SelectedAreaPanel";
import RiverSearch from "./river/RiverSearch";
import RiverSegmentList from "./river/RiverSegmentList";
import RiverTopologyGraph from "./river/RiverTopologyGraph";
import RiverIntelligencePanel from "./river/RiverIntelligencePanel";
import RiverTimeSeries from "./river/RiverTimeSeries";
import RiverLegend from "./river/RiverLegend";
import ImpactCategoryList from "./impact/ImpactCategoryList";
import ImpactSummaryPanel from "./impact/ImpactSummaryPanel";
import ShelterPanel from "./impact/ShelterPanel";
import EvacuationPanel from "./impact/EvacuationPanel";
import ResourcePlanningPanel from "./impact/ResourcePlanningPanel";
import ImpactEvidence from "./impact/ImpactEvidence";
import ImpactLegend from "./impact/ImpactLegend";
import ScenarioControls from "./scenario/ScenarioControls";
import ScenarioSummary from "./scenario/ScenarioSummary";
import ScenarioCompareBar from "./scenario/ScenarioCompareBar";
import ScenarioHistory from "./scenario/ScenarioHistory";
import HistoryCatalog from "./history/HistoryCatalog";
import HistoryTimeline from "./history/HistoryTimeline";
import HistorySummary from "./history/HistorySummary";
import HistoryCompareBar from "./history/HistoryCompareBar";
import ModelPerformanceCenter from "./history/ModelPerformanceCenter";
import {
  DEFAULT_LAYERS,
  layersFromQuickFilter,
  parseExploreHash,
  serializeExploreHash,
  typeFilterFromLayers,
} from "./explore/urlState";

function createScenarioLabel(params, slot) {
  const rainfallMmHr = (Number(params.rainfall_rate) * 3600 * 1000).toFixed(1);
  return `Scenario ${slot}: ${rainfallMmHr} mm/hr · ${params.duration_seconds}s`;
}

export default function App() {
  const [selectedCityId, setSelectedCityId] = useState("sunamganj");
  const [cityMetadata, setCityMetadata] = useState(null);
  const [metadata, setMetadata] = useState(null);
  const [params, setParams] = useState(DEFAULT_PARAMS);
  const [activeLayerId, setActiveLayerId] = useState("depth");
  const [infraLayers, setInfraLayers] = useState({
    future_roads: false,
    critical_facilities: false,
    risk_zones: false,
  });
  const [zoomLevel, setZoomLevel] = useState(11);
  const [activeScenario, setActiveScenario] = useState(null);
  const [inspection, setInspection] = useState(null);
  const [searchMarker, setSearchMarker] = useState(null);
  const [searchNotice, setSearchNotice] = useState(null);
  const [flyTarget, setFlyTarget] = useState(null);
  const [loading, setLoading] = useState(false);
  const [overlayLoading, setOverlayLoading] = useState(false);
  const [error, setError] = useState(null);
  const [cityScenarios, setCityScenarios] = useState([]);
  const [scenarioAId, setScenarioAId] = useState("moderate_rain");
  const [scenarioBId, setScenarioBId] = useState("heavy_rain");
  const [comparisonMode, setComparisonMode] = useState("SIDE_BY_SIDE");
  const [comparisonLayer, setComparisonLayer] = useState("depth");
  const [comparisonResult, setComparisonResult] = useState(null);
  const [comparisonError, setComparisonError] = useState(null);
  const [syncedViewport, setSyncedViewport] = useState(null);
  const [swipePercent, setSwipePercent] = useState(50);
  const [playbackSnapshot, setPlaybackSnapshot] = useState(null);
  const [platformView, setPlatformView] = useState("explore");
  const [role, setRole] = useState(() => localStorage.getItem("floodlens_role") || "general");
  const [regionStatus, setRegionStatus] = useState(null);
  const [statusError, setStatusError] = useState(null);
  const [physicsJobId, setPhysicsJobId] = useState(null);
  const [forecastOverlayUrl, setForecastOverlayUrl] = useState(null);
  const [floodSummary, setFloodSummary] = useState(null);
  const [osmInspect, setOsmInspect] = useState(null);
  const [jobAId, setJobAId] = useState("");
  const [jobBId, setJobBId] = useState("");
  const [jobCompareResult, setJobCompareResult] = useState(null);
  const [jobCompareError, setJobCompareError] = useState(null);
  const [jobCompareLoading, setJobCompareLoading] = useState(false);
  const [showForecastOverlay, setShowForecastOverlay] = useState(true);
  const [showRainfall, setShowRainfall] = useState(false);
  const [showTerrain, setShowTerrain] = useState(false);
  const [rainfallStatus, setRainfallStatus] = useState("UNAVAILABLE");
  const [rainfallSummary, setRainfallSummary] = useState(null);
  const [rainfallOverlayId, setRainfallOverlayId] = useState(null);
  const [terrainOverlayId, setTerrainOverlayId] = useState(null);
  const [timelineHorizon, setTimelineHorizon] = useState(24);
  const [showRivers, setShowRivers] = useState(true);
  const [exploreLayers, setExploreLayers] = useState(() => parseExploreHash()?.layers || DEFAULT_LAYERS);
  const [infraFilter, setInfraFilter] = useState(() => parseExploreHash()?.filter || "all");
  const [selectedRiver, setSelectedRiver] = useState(null);
  const [selectedRegion, setSelectedRegion] = useState(false);
  const [nearbyInfra, setNearbyInfra] = useState([]);
  const [fitToken, setFitToken] = useState(0);
  const [resetToken, setResetToken] = useState(0);
  const [mobileExplorePanel, setMobileExplorePanel] = useState(null);
  const [selectionMode, setSelectionMode] = useState("none");
  const [selectionRect, setSelectionRect] = useState(null);
  const [exploreTime, setExploreTime] = useState(null);
  const [riverCatalog, setRiverCatalog] = useState([]);
  const [riverOverview, setRiverOverview] = useState(null);
  const [riverObservations, setRiverObservations] = useState(null);
  const [riverNeighbors, setRiverNeighbors] = useState(null);
  const [riverSegmentDetail, setRiverSegmentDetail] = useState(null);
  const [impactSummary, setImpactSummary] = useState(null);
  const [impactAssets, setImpactAssets] = useState([]);
  const [impactShelters, setImpactShelters] = useState(null);
  const [impactEvacuation, setImpactEvacuation] = useState(null);
  const [impactResources, setImpactResources] = useState(null);
  const [impactCategory, setImpactCategory] = useState("");
  const [selectedImpactAsset, setSelectedImpactAsset] = useState(null);
  const [twinBaselineId, setTwinBaselineId] = useState("");
  const [twinScenarioId, setTwinScenarioId] = useState("");
  const [twinBaselineJob, setTwinBaselineJob] = useState(null);
  const [twinScenarioJob, setTwinScenarioJob] = useState(null);
  const [twinWorkspace, setTwinWorkspace] = useState(null);
  const [twinDifference, setTwinDifference] = useState(null);
  const [twinImpact, setTwinImpact] = useState(null);
  const [twinMapMode, setTwinMapMode] = useState("scenario");
  const [twinCapabilities, setTwinCapabilities] = useState([]);
  const [twinHistory, setTwinHistory] = useState([]);
  const [twinBaselineMeta, setTwinBaselineMeta] = useState(null);
  const [rainfallMultiplier, setRainfallMultiplier] = useState(1.3);
  const [riverDeltaM, setRiverDeltaM] = useState(0);
  const [scenarioName, setScenarioName] = useState("Rainfall +30%");
  const [scenarioPending, setScenarioPending] = useState(false);
  const [scenarioError, setScenarioError] = useState(null);
  const [twinSelectedTime, setTwinSelectedTime] = useState(null);
  const [twinReport, setTwinReport] = useState(null);
  const [twinRefresh, setTwinRefresh] = useState(0);
  const [historyTab, setHistoryTab] = useState("events");
  const [historyFilters, setHistoryFilters] = useState({
    year: "",
    region: "",
    flood_mechanism: "",
    source: "",
    model: "",
    status: "",
  });
  const [historyEvents, setHistoryEvents] = useState([]);
  const [historyCatalogStatus, setHistoryCatalogStatus] = useState("idle");
  const [selectedHistoryEventId, setSelectedHistoryEventId] = useState("");
  const [historyDetail, setHistoryDetail] = useState(null);
  const [historyObservation, setHistoryObservation] = useState(null);
  const [historyCompare, setHistoryCompare] = useState(null);
  const [historyPredictionId, setHistoryPredictionId] = useState("");
  const [historyReport, setHistoryReport] = useState(null);
  const [historyReportPending, setHistoryReportPending] = useState(false);
  const [modelPerformance, setModelPerformance] = useState(null);
  const [selectedModelId, setSelectedModelId] = useState("");

  const {
    compareMode,
    setCompareMode,
    scenarioA,
    scenarioB,
    activeSlot,
    setActiveSlot,
    comparisonStats,
    saveScenario,
  } = useScenarioComparison();

  const availableTimes = activeScenario?.runResult?.available_times || [];

  const {
    currentTime,
    duration,
    timeIndex,
    isPlaying,
    isCollapsed,
    setIsCollapsed,
    handlePlayPause,
    handleReset,
    handleScrub,
    formattedCurrent,
    formattedDuration,
  } = useTimeAnimation(availableTimes, Boolean(activeScenario));

  const loadRegionStatus = useCallback(async (cityId) => {
    try {
      const data = await fetchStatus(cityId);
      setRegionStatus(data);
      setStatusError(null);
      const rainLayer = (data.layers?.layers || []).find((row) => row.id === "rainfall");
      setRainfallStatus(rainLayer?.data_status || "UNAVAILABLE");
    } catch (err) {
      setRegionStatus(null);
      setStatusError(err.message);
    }
  }, []);

  const handleForecastOverlay = useCallback((url, meta) => {
    setForecastOverlayUrl(url);
    setFloodSummary(meta);
  }, []);

  const handlePhysicsJobComplete = useCallback(
    (job) => {
      if (job?.status === "completed" || job?.status === "failed") {
        loadRegionStatus(selectedCityId);
        setTwinRefresh((value) => value + 1);
        if (job?.status === "completed" && job.result_reference) {
          setJobAId((current) => current || job.job_id || job.id);
        }
        if (job?.status === "failed") {
          setScenarioError(job.error || "SIMULATION FAILED");
        }
      }
    },
    [loadRegionStatus, selectedCityId]
  );

  const handleJobCompare = useCallback(async () => {
    if (!jobAId || !jobBId) {
      setJobCompareError("Enter two job ids.");
      return;
    }
    setJobCompareLoading(true);
    try {
      const data = await compareJobs([jobAId, jobBId]);
      setJobCompareResult(data);
      setJobCompareError(null);
    } catch (err) {
      setJobCompareError(err.message);
      setJobCompareResult(null);
    } finally {
      setJobCompareLoading(false);
    }
  }, [jobAId, jobBId]);

  const handleTwinRun = useCallback(
    async ({ name, rainfall_multiplier, river_level_delta_m, baseline_id }) => {
      setScenarioPending(true);
      setScenarioError(null);
      setTwinReport(null);
      try {
        let baseline = baseline_id;
        if (!baseline) {
          const baseJob = await postScenarioJob(selectedCityId, {
            name: "Baseline ×1.0",
            rainfall_multiplier: 1.0,
            river_level_delta_m: 0,
          });
          baseline = baseJob.job_id || baseJob.id;
          setTwinBaselineJob(baseJob);
        }
        setTwinBaselineId(baseline);
        const scen = await postScenarioJob(selectedCityId, {
          name,
          rainfall_multiplier,
          river_level_delta_m,
          baseline_id: baseline,
        });
        const sid = scen.job_id || scen.id;
        setTwinScenarioId(sid);
        setTwinScenarioJob(scen);
        setPhysicsJobId(sid);
        setJobAId(baseline);
        setJobBId(sid);
        setTwinMapMode(Number(river_level_delta_m) ? "scenario" : "split");
      } catch (err) {
        setScenarioError(err.message);
      } finally {
        setScenarioPending(false);
      }
    },
    [selectedCityId]
  );

  const handleTwinReport = useCallback(async () => {
    try {
      const report = await postReport(selectedCityId, {
        baselineJob: twinBaselineId || undefined,
        scenarioJob: twinScenarioId || undefined,
      });
      setTwinReport(report);
    } catch (err) {
      setScenarioError(err.message);
    }
  }, [selectedCityId, twinBaselineId, twinScenarioId]);

  const handleCityChange = (city, scenarios) => {
    setSelectedCityId(city.city_id);
    setCityMetadata(city);
    setZoomLevel(city.default_zoom || 11);
    setInspection(null);
    setCityScenarios(scenarios || []);
    setComparisonResult(null);
    setTwinBaselineId("");
    setTwinScenarioId("");
    setTwinWorkspace(null);
    setTwinDifference(null);
    setTwinImpact(null);
    setTwinReport(null);
    loadRegionStatus(city.city_id);
  };

  const handleRestoreLocation = (ctx) => {
    if (ctx?.city_id && ctx.city_id !== selectedCityId) {
      fetchCity(ctx.city_id)
        .then((cityData) => handleCityChange(cityData.city || cityData, cityData.scenarios || []))
        .catch(() => undefined);
    }
    if (ctx?.latitude != null && ctx?.longitude != null) {
      setSearchMarker({
        latitude: ctx.latitude,
        longitude: ctx.longitude,
        display_name: ctx.city_id,
      });
      setFlyTarget({
        latitude: ctx.latitude,
        longitude: ctx.longitude,
        zoom: ctx.zoom || 12,
      });
    }
    if (ctx?.zoom) {
      setZoomLevel(ctx.zoom);
    }
    if (Array.isArray(ctx?.layers)) {
      setExploreLayers((current) => {
        const next = { ...current };
        Object.keys(next).forEach((key) => {
          next[key] = ctx.layers.includes(key);
        });
        return next;
      });
    }
    if (ctx?.river_id) {
      setSelectedRiver({ id: ctx.river_id, river_id: ctx.river_id });
    }
    setPlatformView("explore");
  };

  const inspectionScenarioId = compareMode
    ? activeSlot === "A"
      ? scenarioAId
      : scenarioBId
    : activeScenario?.scenarioId || scenarioAId;

  const inspectionContext = useMemo(
    () => ({
      cityId: selectedCityId,
      scenarioId: inspectionScenarioId,
      time: currentTime,
    }),
    [selectedCityId, inspectionScenarioId, currentTime]
  );

  useEffect(() => {
    setInspection(null);
  }, [selectedCityId, inspectionScenarioId, currentTime, compareMode, activeSlot]);

  const studyBounds = cityMetadata?.bounds || metadata?.bounds || null;
  const studyCenter = useMemo(() => {
    if (cityMetadata?.center_lat != null && cityMetadata?.center_lon != null) {
      return {
        latitude: cityMetadata.center_lat,
        longitude: cityMetadata.center_lon,
      };
    }
    return metadata?.center || null;
  }, [cityMetadata, metadata]);

  const overlayBounds = useMemo(() => {
    if (!studyBounds) {
      return null;
    }
    return [
      [studyBounds.south, studyBounds.west],
      [studyBounds.north, studyBounds.east],
    ];
  }, [studyBounds]);

  const mapCenter = useMemo(() => {
    if (cityMetadata?.center_lat && cityMetadata?.center_lon) {
      return [cityMetadata.center_lat, cityMetadata.center_lon];
    }
    if (metadata?.center) {
      return [metadata.center.latitude, metadata.center.longitude];
    }
    return [24.95, 91.35];
  }, [cityMetadata, metadata]);

  const buildScenarioOverlay = useCallback(
    (scenario, layerId, fraction) => {
      if (!scenario?.samples) {
        return null;
      }
      return buildOverlayFromSamples(
        scenario.samples,
        scenario.samplesX,
        scenario.samplesY,
        layerId,
        fraction
      );
    },
    []
  );

  const overlayFromSnapshot = useCallback((snapshot, layerId) => {
    if (!snapshot) {
      return null;
    }
    if (layerId === "velocity") {
      return buildArrayOverlay(snapshot.velocity, "velocity");
    }
    if (layerId === "max_depth") {
      return buildArrayOverlay(snapshot.maximum_depth, "max_depth");
    }
    if (layerId === "flood_extent") {
      const depth = snapshot.depth || [];
      const extent = depth.map((row) => row.map((value) => (value > 0.001 ? 1 : 0)));
      return buildArrayOverlay(extent, "flood_extent");
    }
    return buildArrayOverlay(snapshot.depth, "depth");
  }, []);

  const activeOverlayUrl = useMemo(
    () => overlayFromSnapshot(playbackSnapshot, activeLayerId)
      || buildScenarioOverlay(activeScenario, activeLayerId, 1),
    [playbackSnapshot, activeLayerId, overlayFromSnapshot, activeScenario, buildScenarioOverlay]
  );

  const [compareSnapshots, setCompareSnapshots] = useState({ A: null, B: null });

  const scenarioAOverlay = useMemo(
    () => overlayFromSnapshot(compareSnapshots.A, activeLayerId)
      || buildScenarioOverlay(scenarioA, activeLayerId, 1),
    [compareSnapshots.A, activeLayerId, overlayFromSnapshot, scenarioA, buildScenarioOverlay]
  );

  const scenarioBOverlay = useMemo(
    () => overlayFromSnapshot(compareSnapshots.B, activeLayerId)
      || buildScenarioOverlay(scenarioB, activeLayerId, 1),
    [compareSnapshots.B, activeLayerId, overlayFromSnapshot, scenarioB, buildScenarioOverlay]
  );

  const differenceOverlay = useMemo(() => {
    const array = comparisonResult?.comparison?.difference_array;
    if (!array) {
      return null;
    }
    return buildArrayOverlay(array, comparisonLayer);
  }, [comparisonResult, comparisonLayer]);

  useEffect(() => {
    if (!compareMode || !scenarioAId || !scenarioBId || scenarioAId === scenarioBId) {
      return undefined;
    }
    if (!scenarioA || !scenarioB) {
      return undefined;
    }
    if (availableTimes.length === 0) {
      return undefined;
    }

    let cancelled = false;
    const runCompare = async () => {
      setComparisonError(null);
      try {
        const result = await compareScenarios({
          city_id: selectedCityId,
          scenario_a_id: scenarioAId,
          scenario_b_id: scenarioBId,
          layer: comparisonLayer,
          comparison_mode: comparisonMode,
          time: currentTime,
        });
        if (!cancelled) {
          setComparisonResult(result);
        }
      } catch (compareError) {
        if (!cancelled) {
          setComparisonResult(null);
          setComparisonError(compareError.message);
        }
      }
    };

    runCompare();
    return () => {
      cancelled = true;
    };
  }, [
    compareMode,
    selectedCityId,
    scenarioAId,
    scenarioBId,
    comparisonLayer,
    comparisonMode,
    scenarioA,
    scenarioB,
    currentTime,
  ]);

  useEffect(() => {
    if (!activeScenario || availableTimes.length === 0) {
      setPlaybackSnapshot(null);
      return undefined;
    }
    let cancelled = false;
    const loadSnapshot = async () => {
      try {
        const snapshot = await fetchScenarioSnapshot(
          selectedCityId,
          inspectionScenarioId,
          currentTime
        );
        if (!cancelled) {
          setPlaybackSnapshot(snapshot);
        }
      } catch (snapshotError) {
        if (!cancelled) {
          setPlaybackSnapshot(null);
          setError(snapshotError.message);
        }
      }
    };
    loadSnapshot();
    return () => {
      cancelled = true;
    };
  }, [activeScenario, availableTimes.length, selectedCityId, inspectionScenarioId, currentTime]);

  useEffect(() => {
    if (!compareMode || !scenarioA || !scenarioB || availableTimes.length === 0) {
      return undefined;
    }
    let cancelled = false;
    const loadCompareSnapshots = async () => {
      try {
        const [snapA, snapB] = await Promise.all([
          fetchScenarioSnapshot(selectedCityId, scenarioAId, currentTime),
          fetchScenarioSnapshot(selectedCityId, scenarioBId, currentTime),
        ]);
        if (!cancelled) {
          setCompareSnapshots({ A: snapA, B: snapB });
        }
      } catch (snapshotError) {
        if (!cancelled) {
          setCompareSnapshots({ A: null, B: null });
        }
      }
    };
    loadCompareSnapshots();
    return () => {
      cancelled = true;
    };
  }, [compareMode, scenarioA, scenarioB, selectedCityId, scenarioAId, scenarioBId, currentTime, availableTimes.length]);

  useEffect(() => {
    const loadInitialData = async () => {
      try {
        const cities = await fetchCities();
        const hash = parseExploreHash();
        const defaultCity =
          cities.find((city) => city.city_id === hash?.cityId) ||
          cities.find((city) => city.is_default_city) ||
          cities[0];
        if (defaultCity) {
          setSelectedCityId(defaultCity.city_id);
          setCityMetadata(defaultCity);
          try {
            const cityData = await fetchCity(defaultCity.city_id);
            setCityScenarios(cityData.scenarios || []);
          } catch (cityError) {
            setCityScenarios([]);
          }
          loadRegionStatus(defaultCity.city_id);
        }
        if (hash?.latitude != null && hash?.longitude != null && Number.isFinite(hash.latitude)) {
          setSearchMarker({
            display_name: "Restored from URL",
            latitude: hash.latitude,
            longitude: hash.longitude,
            place_type: "coordinates",
            region_id: hash.cityId,
          });
          setFlyTarget({
            latitude: hash.latitude,
            longitude: hash.longitude,
            zoom: hash.zoom || 12,
          });
        }
        if (hash?.riverId) {
          setSelectedRiver({ id: hash.riverId, river_id: hash.riverId, name: hash.riverId });
        }
        if (hash?.view) {
          setPlatformView(hash.view);
        }
        if (hash?.jobId) {
          setPhysicsJobId(hash.jobId);
        }

        const scenarioMeta = await fetchScenarioMetadata();
        setMetadata(scenarioMeta);
      } catch (err) {
        setError(err.message);
      }
    };

    loadInitialData();
  }, []);

  const handleParamChange = (field, value) => {
    setParams((current) => ({ ...current, [field]: value }));
  };

  const handleSelectPreset = (preset) => {
    setParams((current) => ({
      ...current,
      rainfall_rate: preset.rainfall_rate,
      duration_seconds: preset.duration_seconds,
      nx: preset.nx,
      ny: preset.ny,
    }));
  };

  const handleInfraToggle = (layerId) => {
    setInfraLayers((current) => ({
      ...current,
      [layerId]: !current[layerId],
    }));
  };

  const handleRunScenario = async () => {
    setLoading(true);
    setError(null);
    setInspection(null);
    handleReset();

    try {
      const selectedScenarioId = compareMode
        ? activeSlot === "A"
          ? scenarioAId
          : scenarioBId
        : scenarioAId;
      const result = await runScenario({
        nx: Number(params.nx),
        ny: Number(params.ny),
        rainfall_rate: Number(params.rainfall_rate),
        duration_seconds: Number(params.duration_seconds),
        scenario: selectedCityId,
        city_id: selectedCityId,
        scenario_id: selectedScenarioId,
      });

      if (!result.success) {
        throw new Error("Simulation failed to complete.");
      }

      const updatedMetadata = await fetchScenarioMetadata();
      setMetadata(updatedMetadata);

      setOverlayLoading(true);
      const sampleBounds = cityMetadata?.bounds || updatedMetadata.bounds;
      const { samples, samplesX, samplesY } = await sampleRasterGrid(
        sampleBounds,
        result.nx,
        result.ny,
        {
          cityId: selectedCityId,
          scenarioId: selectedScenarioId,
          time: result.simulation_time_s,
        }
      );

      const snapshot = {
        label: createScenarioLabel(params, activeSlot),
        params: { ...params },
        runResult: result,
        samples,
        samplesX,
        samplesY,
        cityId: selectedCityId,
        scenarioId: selectedScenarioId,
      };

      setActiveScenario(snapshot);
      saveScenario(snapshot);
    } catch (runError) {
      setError(runError.message);
    } finally {
      setLoading(false);
      setOverlayLoading(false);
    }
  };

  const handleInspect = async (latitude, longitude) => {
    if (!activeScenario) {
      setError("Run a scenario before inspecting cells.");
      return;
    }

    try {
      const cell = await inspectCell(latitude, longitude, inspectionContext);
      setInspection(cell);
      setError(null);
    } catch (inspectError) {
      setInspection(null);
      if (inspectError.errorCode === "OUTSIDE_SIMULATION_DOMAIN") {
        const cityName = cityMetadata?.name || selectedCityId;
        setError(`Click is outside the ${cityName} study region.`);
      } else {
        setError(inspectError.message);
      }
    }
  };

  const handleSelectLocation = async (location) => {
    if (location?.cleared) {
      setSearchMarker(null);
      setFlyTarget(null);
      setSearchNotice(null);
      setSelectedRiver(null);
      setOsmInspect(null);
      return;
    }
    const cities = await fetchCities().catch(() => []);
    const match = cities.find((city) => {
      const name = (city.name || city.city_id || "").toLowerCase();
      const queryName = (location.display_name || "").toLowerCase();
      if (name && queryName.includes(name)) {
        return true;
      }
      return isWithinCityBounds(location.latitude, location.longitude, city.bounds);
    });
    const bounds = (match || cityMetadata)?.bounds || metadata?.bounds;
    const withinCity = isWithinCityBounds(
      location.latitude,
      location.longitude,
      bounds
    );
    const zoom = selectSearchZoom(location.place_type, (match || cityMetadata)?.default_zoom || 12);

    setSearchMarker(location);
    setFlyTarget({
      latitude: location.latitude,
      longitude: location.longitude,
      zoom,
      label: location.display_name,
    });
    setSelectedRegion(Boolean(location.region_id || location.place_type === "city"));
    const riverId = location.administrative?.river_id || (location.place_type === "river" ? location.region_id : null);
    if (riverId || location.place_type === "river") {
      setSelectedRiver({
        id: riverId || "buriganga",
        river_id: riverId || "buriganga",
        name: location.display_name,
        data_status: "REAL",
      });
    } else {
      setSelectedRiver(null);
    }
    setSearchNotice(
      withinCity
        ? null
        : `“${location.display_name}” is outside the current study region (${cityMetadata?.name || selectedCityId}). City selection was not changed.`
    );
    setError(null);
    loadRegionStatus(match?.city_id || selectedCityId);
    if (match && match.city_id !== selectedCityId) {
      try {
        const cityData = await fetchCity(match.city_id);
        handleCityChange(match, cityData.scenarios || []);
      } catch (cityError) {
        handleCityChange(match, []);
      }
    }
  };

  const handleCoordinateSelect = (latitude, longitude) => {
    setSearchMarker({
      display_name: `${latitude.toFixed(5)}, ${longitude.toFixed(5)}`,
      latitude,
      longitude,
      place_type: "coordinates",
    });
    setSelectedRiver(null);
    setSelectedRegion(false);
    setOsmInspect(null);
    const pad = 0.02;
    const bbox = `${longitude - pad},${latitude - pad},${longitude + pad},${latitude + pad}`;
    fetchInfrastructure(selectedCityId, { bbox, limit: 50 })
      .then((data) => setNearbyInfra(data.features || []))
      .catch(() => setNearbyInfra([]));
  };

  const handleRiverSelect = (river) => {
    setSelectedRiver(river);
    setOsmInspect(null);
    const riverId = river?.id || river?.river_id;
    if (riverId && river?.segment_id) {
      fetchRiverSegment(riverId, river.segment_id)
        .then((data) => {
          setRiverSegmentDetail(data);
          setSelectedRiver((current) => ({
            ...(current || river),
            ...data,
            name: data.river?.name || current?.name || river.name,
            segment_id: data.segment?.id || river.segment_id,
          }));
        })
        .catch(() => setRiverSegmentDetail(null));
      fetchRiverNeighbors(riverId, river.segment_id)
        .then(setRiverNeighbors)
        .catch(() => setRiverNeighbors(null));
    }
  };

  const handleRiverSearchSelect = (hit) => {
    if (hit.kind === "study_region" && hit.city_id) {
      fetchCity(hit.city_id)
        .then((cityData) => handleCityChange(cityData.city || cityData, cityData.scenarios || []))
        .catch(() => {});
      return;
    }
    const applyRiver = (catalog) => {
      const listed = (catalog || riverCatalog).find((row) => row.id === (hit.river_id || hit.id));
      const next = {
        id: hit.river_id || hit.id,
        river_id: hit.river_id || hit.id,
        name: hit.name,
        segment_id: hit.segment_id || listed?.segments?.[0]?.id,
        city_id: hit.city_id,
        data_status: hit.data_status || "DEMO",
      };
      handleRiverSelect(next);
      const coords = (listed?.segments || []).flatMap((segment) => segment.coordinates || []);
      if (coords.length) {
        const lon = coords.reduce((sum, pt) => sum + pt[0], 0) / coords.length;
        const lat = coords.reduce((sum, pt) => sum + pt[1], 0) / coords.length;
        setFlyTarget({ latitude: lat, longitude: lon, zoom: 13 });
      }
    };
    if (hit.city_id && hit.city_id !== selectedCityId) {
      fetchCity(hit.city_id)
        .then((cityData) => {
          handleCityChange(cityData.city || cityData, cityData.scenarios || []);
          return fetchRivers(hit.city_id);
        })
        .then((data) => applyRiver(data.data || []))
        .catch(() => applyRiver());
      return;
    }
    applyRiver();
  };

  const handleInfraFilterChange = (filterId) => {
    setInfraFilter(filterId);
    setExploreLayers((current) => ({
      ...layersFromQuickFilter(filterId),
      floodExtent: current.floodExtent,
      forecast: current.forecast,
      rivers: current.rivers,
    }));
  };

  useEffect(() => {
    const rainfallOn = platformView === "explore" ? Boolean(exploreLayers.rainfall) : showRainfall;
    if (!rainfallOn || !selectedCityId) {
      return undefined;
    }
    let cancelled = false;
    fetchRainfall(selectedCityId)
      .then((data) => {
        if (cancelled) {
          return;
        }
        const rows = data.data || data.observations || [];
        const latest = rows[rows.length - 1];
        setRainfallStatus(rows.length ? data.provenance?.data_status || "PARTIAL" : "UNAVAILABLE");
        setRainfallOverlayId(data.overlay_artifact_id || null);
        setRainfallSummary(
          latest
            ? {
                value_mm: latest.value_mm ?? latest.value ?? latest.precipitation_mm ?? latest.amount_mm ?? null,
                observed_at: latest.observed_at || latest.t,
              }
            : null
        );
      })
      .catch(() => {
        if (!cancelled) {
          setRainfallStatus("UNAVAILABLE");
          setRainfallSummary(null);
          setRainfallOverlayId(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [showRainfall, selectedCityId, platformView, exploreLayers.rainfall]);

  useEffect(() => {
    if (!selectedCityId) {
      return undefined;
    }
    let cancelled = false;
    fetchTerrain(selectedCityId)
      .then((data) => {
        if (cancelled) {
          return;
        }
        setTerrainOverlayId(data.overlay_artifact_id || null);
      })
      .catch(() => {
        if (!cancelled) {
          setTerrainOverlayId(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selectedCityId]);

  const isExplore = platformView === "explore";
  const isRiver = platformView === "river";
  const isImpact = platformView === "impact";
  const isSimulation = platformView === "simulation";
  const isHistory = platformView === "history";
  const dedicatedWorkspace = isExplore || isRiver || isImpact || isSimulation || isHistory;
  const showSimControls = role !== "general" && platformView === "simulation";
  const freshness =
    regionStatus?.risk?.provenance?.freshness ||
    regionStatus?.forecast?.provenance?.freshness ||
    "see provenance";

  const osmEnabledTypes = useMemo(() => {
    const types = [];
    if (exploreLayers.hospitals) types.push("hospital");
    if (exploreLayers.schools) types.push("school");
    if (exploreLayers.bridges) types.push("bridge");
    if (exploreLayers.roads) types.push("road");
    if (exploreLayers.critical) types.push("emergency");
    if (exploreLayers.shelters) types.push("shelter");
    return types;
  }, [exploreLayers]);

  useEffect(() => {
    const next = serializeExploreHash({
      cityId: selectedCityId,
      view: platformView,
      jobId: physicsJobId,
      latitude: searchMarker?.latitude ?? studyCenter?.latitude,
      longitude: searchMarker?.longitude ?? studyCenter?.longitude,
      zoom: zoomLevel,
      layers: exploreLayers,
      filter: infraFilter,
      riverId: selectedRiver?.river_id || selectedRiver?.id,
    });
    if (window.location.hash !== next) {
      window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${next}`);
    }
  }, [
    platformView,
    selectedCityId,
    physicsJobId,
    searchMarker,
    studyCenter,
    zoomLevel,
    exploreLayers,
    infraFilter,
    selectedRiver,
  ]);

  useEffect(() => {
    if (platformView !== "river") {
      return undefined;
    }
    let cancelled = false;
    fetchRivers(selectedCityId)
      .then((data) => {
        if (!cancelled) {
          setRiverCatalog(data.data || []);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setRiverCatalog([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [platformView, selectedCityId]);

  const selectedRiverId = selectedRiver?.id || selectedRiver?.river_id;

  useEffect(() => {
    if (platformView !== "river" || !selectedRiverId) {
      return undefined;
    }
    let cancelled = false;
    fetchRiverOverview(selectedRiverId)
      .then((data) => {
        if (!cancelled) {
          setRiverOverview(data);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setRiverOverview(null);
        }
      });
    fetchRiverObservations(selectedRiverId)
      .then((data) => {
        if (!cancelled) {
          setRiverObservations(data);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setRiverObservations(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [platformView, selectedRiverId]);

  const topologyHighlights = useMemo(
    () => ({
      riverId: selectedRiverId,
      upstream: (riverNeighbors?.upstream || selectedRiver?.upstream || []).map((row) => row.id),
      downstream: (riverNeighbors?.downstream || selectedRiver?.downstream || []).map((row) => row.id),
      reachable: (riverNeighbors?.reachable_downstream || []).map((row) => row.id),
    }),
    [selectedRiverId, riverNeighbors, selectedRiver]
  );

  const activeRiverRecord = riverCatalog.find((row) => row.id === selectedRiverId) || null;

  useEffect(() => {
    if (platformView !== "impact") {
      return undefined;
    }
    let cancelled = false;
    const opts = { jobId: physicsJobId || undefined, category: impactCategory || undefined, limit: 200 };
    fetchImpact(selectedCityId, opts)
      .then((data) => {
        if (!cancelled) setImpactSummary(data);
      })
      .catch(() => {
        if (!cancelled) setImpactSummary(null);
      });
    fetchImpactInfrastructure(selectedCityId, opts)
      .then((data) => {
        if (!cancelled) setImpactAssets(data.assets || []);
      })
      .catch(() => {
        if (!cancelled) setImpactAssets([]);
      });
    fetchImpactShelters(selectedCityId, opts)
      .then((data) => {
        if (!cancelled) setImpactShelters(data);
      })
      .catch(() => {
        if (!cancelled) setImpactShelters(null);
      });
    fetchImpactEvacuation(selectedCityId, { jobId: physicsJobId || undefined })
      .then((data) => {
        if (!cancelled) setImpactEvacuation(data);
      })
      .catch(() => {
        if (!cancelled) setImpactEvacuation(null);
      });
    fetchImpactResources(selectedCityId, { jobId: physicsJobId || undefined })
      .then((data) => {
        if (!cancelled) setImpactResources(data);
      })
      .catch(() => {
        if (!cancelled) setImpactResources(null);
      });
    return () => {
      cancelled = true;
    };
  }, [platformView, selectedCityId, physicsJobId, impactCategory]);

  useEffect(() => {
    if (!isSimulation) {
      return undefined;
    }
    let cancelled = false;
    fetchScenarioCapabilities()
      .then((data) => {
        if (!cancelled) setTwinCapabilities(data.parameters || []);
      })
      .catch(() => {
        if (!cancelled) setTwinCapabilities([]);
      });
    fetchScenarioBaseline(selectedCityId)
      .then((data) => {
        if (!cancelled) {
          setTwinBaselineMeta(data);
          if (!twinBaselineId && data.job_id) {
            setTwinBaselineId(data.job_id);
          }
        }
      })
      .catch(() => {
        if (!cancelled) setTwinBaselineMeta(null);
      });
    fetchScenarioHistory(selectedCityId)
      .then((data) => {
        if (!cancelled) setTwinHistory(data.scenarios || []);
      })
      .catch(() => {
        if (!cancelled) setTwinHistory([]);
      });
    fetchScenarioWorkspace(selectedCityId, {
      baselineJob: twinBaselineId || undefined,
      scenarioJob: twinScenarioId || undefined,
    })
      .then((data) => {
        if (!cancelled) setTwinWorkspace(data);
      })
      .catch(() => {
        if (!cancelled) setTwinWorkspace(null);
      });
    if (twinBaselineId && twinScenarioId) {
      fetchScenarioDifference(twinBaselineId, twinScenarioId)
        .then((data) => {
          if (!cancelled) setTwinDifference(data);
        })
        .catch(() => {
          if (!cancelled) setTwinDifference(null);
        });
      fetchImpact(selectedCityId, { jobId: twinScenarioId, limit: 200 })
        .then((data) => {
          if (!cancelled) setTwinImpact(data);
        })
        .catch(() => {
          if (!cancelled) setTwinImpact(null);
        });
    }
    if (twinBaselineId) {
      fetchJob(twinBaselineId)
        .then((data) => {
          if (!cancelled) setTwinBaselineJob(data);
        })
        .catch(() => undefined);
    }
    if (twinScenarioId) {
      fetchJob(twinScenarioId)
        .then((data) => {
          if (!cancelled) setTwinScenarioJob(data);
        })
        .catch(() => undefined);
    }
    return () => {
      cancelled = true;
    };
  }, [isSimulation, selectedCityId, twinBaselineId, twinScenarioId, twinRefresh]);

  useEffect(() => {
    if (!isHistory || historyTab !== "events") {
      return undefined;
    }
    let cancelled = false;
    setHistoryCatalogStatus("loading");
    const filters = {};
    Object.entries(historyFilters).forEach(([key, value]) => {
      if (value) filters[key] = value;
    });
    fetchHistoryEvents(filters)
      .then((data) => {
        if (cancelled) return;
        const rows = data.data || [];
        setHistoryEvents(rows);
        setHistoryCatalogStatus("ok");
        setSelectedHistoryEventId((current) => current || rows[0]?.event_id || "");
      })
      .catch(() => {
        if (!cancelled) {
          setHistoryEvents([]);
          setHistoryCatalogStatus("error");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [isHistory, historyTab, historyFilters]);

  useEffect(() => {
    if (!isHistory || !selectedHistoryEventId || historyTab !== "events") {
      return undefined;
    }
    let cancelled = false;
    fetchHistoryEvent(selectedHistoryEventId)
      .then((data) => {
        if (cancelled) return;
        setHistoryDetail(data);
        const first = (data.timeline || [])[0] || null;
        setHistoryObservation(first);
        setHistoryCompare(data.compare || null);
      })
      .catch(() => {
        if (!cancelled) {
          setHistoryDetail(null);
          setHistoryObservation(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [isHistory, selectedHistoryEventId, historyTab]);

  useEffect(() => {
    if (!isHistory || !selectedHistoryEventId || !historyPredictionId) {
      return undefined;
    }
    let cancelled = false;
    fetchHistoryCompare(selectedHistoryEventId, historyPredictionId)
      .then((data) => {
        if (!cancelled) setHistoryCompare(data);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [isHistory, selectedHistoryEventId, historyPredictionId]);

  useEffect(() => {
    if (!isHistory && platformView !== "research") {
      return undefined;
    }
    let cancelled = false;
    fetchModelPerformance()
      .then((data) => {
        if (!cancelled) setModelPerformance(data);
      })
      .catch(() => {
        if (!cancelled) setModelPerformance(null);
      });
    return () => {
      cancelled = true;
    };
  }, [isHistory, platformView]);

  const handleHistoryReport = useCallback(() => {
    if (!selectedHistoryEventId) return;
    setHistoryReportPending(true);
    postHistoryReport(selectedHistoryEventId, selectedCityId)
      .then((data) => setHistoryReport(data))
      .catch(() => setHistoryReport(null))
      .finally(() => setHistoryReportPending(false));
  }, [selectedHistoryEventId, selectedCityId]);

  const impactById = useMemo(() => {
    const next = {};
    impactAssets.forEach((row) => {
      if (row.id) next[row.id] = row;
    });
    return next;
  }, [impactAssets]);

  const impactEnabledTypes = useMemo(() => {
    if (!isImpact) return undefined;
    if (impactCategory === "critical") return ["emergency", "clinic"];
    if (impactCategory) return [impactCategory];
    return ["hospital", "school", "bridge", "road", "shelter", "emergency", "clinic"];
  }, [isImpact, impactCategory]);

  const twinBaselineOverlay = useMemo(() => {
    const id =
      (twinWorkspace?.compare?.comparisons || [])[0]?.artifact_id ||
      twinBaselineJob?.result?.artifact_id ||
      twinBaselineJob?.result_reference;
    return id ? artifactOverlayUrl(id) : null;
  }, [twinWorkspace, twinBaselineJob]);

  const twinScenarioOverlay = useMemo(() => {
    const id =
      (twinWorkspace?.compare?.comparisons || [])[1]?.artifact_id ||
      twinScenarioJob?.result?.artifact_id ||
      twinScenarioJob?.result_reference;
    return id ? artifactOverlayUrl(id) : null;
  }, [twinWorkspace, twinScenarioJob]);

  const twinDiffOverlay = useMemo(() => {
    if (!twinDifference?.available || !twinDifference.artifact_id) {
      return null;
    }
    return artifactOverlayUrl(twinDifference.artifact_id);
  }, [twinDifference]);

  const twinTimes = twinScenarioJob?.result?.available_times || twinBaselineJob?.result?.available_times || [];

  useEffect(() => {
    if (platformView !== "river" || !riverCatalog.length) {
      return;
    }
    if (selectedRiverId && riverCatalog.some((row) => row.id === selectedRiverId)) {
      return;
    }
    const first = riverCatalog[0];
    const firstSeg = (first.segments || [])[0];
    handleRiverSelect({
      id: first.id,
      river_id: first.id,
      name: first.name,
      segment_id: firstSeg?.id,
      segment: firstSeg,
      data_status: "DEMO",
    });
    const coords = (first.segments || []).flatMap((segment) => segment.coordinates || []);
    if (coords.length) {
      const lon = coords.reduce((sum, pt) => sum + pt[0], 0) / coords.length;
      const lat = coords.reduce((sum, pt) => sum + pt[1], 0) / coords.length;
      setFlyTarget({ latitude: lat, longitude: lon, zoom: 13 });
    }
  }, [platformView, riverCatalog, selectedRiverId]);

  const renderStatistics = (result) => (
    <div className="grid grid-cols-2 gap-3">
      <div className="rounded-xl border border-slate-800 bg-slate-800/70 p-3">
        <p className="text-xs uppercase tracking-wide text-slate-400">Max Depth</p>
        <p className="mt-1 text-2xl font-semibold text-white">
          {result ? `${result.max_depth_m.toFixed(3)} m` : "UNAVAILABLE"}
        </p>
      </div>
      <div className="rounded-xl border border-slate-800 bg-slate-800/70 p-3">
        <p className="text-xs uppercase tracking-wide text-slate-400">Flooded Area</p>
        <p className="mt-1 text-2xl font-semibold text-white">
          {result ? `${result.flooded_area_km2.toFixed(3)} km²` : "UNAVAILABLE"}
        </p>
      </div>
    </div>
  );

  return (
    <RoleShell
      activeView={platformView}
      onViewChange={setPlatformView}
      cityName={cityMetadata?.name}
      freshness={freshness}
      onRoleChange={setRole}
      searchSlot={<LocationSearchBar onSelectLocation={handleSelectLocation} variant="header" />}
    >
    <div className="flex min-h-0 flex-1 overflow-hidden bg-slate-950 text-slate-100">
      <aside
        className={`glass-panel z-[1100] shrink-0 flex-col overflow-y-auto border-r border-slate-800 text-slate-100 ${
          dedicatedWorkspace
            ? `explore-left w-72 ${mobileExplorePanel === "layers" ? "explore-sheet-open" : "max-lg:hidden"} lg:flex`
            : "flex w-80"
        }`}
      >
        {isExplore && (
          <div className="space-y-3 border-b border-slate-800 px-4 py-3">
            <h1 className="text-lg font-semibold">Explore</h1>
            <CitySelector selectedCityId={selectedCityId} onCityChange={handleCityChange} />
            <InfraFilterBar value={infraFilter} onChange={handleInfraFilterChange} />
            <FreshnessBar
              label="Region freshness"
              provenance={regionStatus?.risk?.provenance || regionStatus?.forecast?.provenance}
            />
            <label className="flex items-center justify-between text-[11px] text-slate-300">
              Polygon selection
              <input
                type="checkbox"
                checked={selectionMode === "bbox"}
                onChange={() =>
                  setSelectionMode((current) => (current === "bbox" ? "none" : "bbox"))
                }
                aria-label="Toggle optional rectangle selection"
              />
            </label>
            <ExploreLayerManager
              cityId={selectedCityId}
              layers={exploreLayers}
              onChange={setExploreLayers}
              floodAvailable={Boolean(activeOverlayUrl)}
              forecastAvailable={Boolean(forecastOverlayUrl)}
            />
          </div>
        )}
        {isRiver && (
          <div className="space-y-3 border-b border-slate-800 px-4 py-3">
            <h1 className="text-lg font-semibold">River intelligence</h1>
            <CitySelector selectedCityId={selectedCityId} onCityChange={handleCityChange} />
            <RiverSearch onSelect={handleRiverSearchSelect} />
            <RiverSegmentList
              river={activeRiverRecord}
              selectedSegmentId={selectedRiver?.segment_id}
              onSelectSegment={(segment) =>
                handleRiverSelect({
                  id: selectedRiverId || activeRiverRecord?.id,
                  river_id: selectedRiverId || activeRiverRecord?.id,
                  name: activeRiverRecord?.name,
                  segment_id: segment.id,
                  segment,
                })
              }
            />
            <RiverTopologyGraph
              segments={activeRiverRecord?.segments || []}
              selectedSegmentId={selectedRiver?.segment_id}
              onSelectSegment={(segment) =>
                handleRiverSelect({
                  id: selectedRiverId || activeRiverRecord?.id,
                  river_id: selectedRiverId || activeRiverRecord?.id,
                  name: activeRiverRecord?.name,
                  segment_id: segment.id,
                  segment,
                })
              }
            />
            <RiverLegend />
            <p className="text-[10px] text-amber-200">DEMO fixture topology. Not live river monitoring.</p>
          </div>
        )}
        {isImpact && (
          <div className="space-y-3 border-b border-slate-800 px-4 py-3">
            <h1 className="text-lg font-semibold">Impact workspace</h1>
            <CitySelector selectedCityId={selectedCityId} onCityChange={handleCityChange} />
            <p className="text-[11px] text-slate-400">
              {cityMetadata?.name || selectedCityId} · {impactSummary?.scenario?.label || "BASELINE"}
              {impactSummary?.scenario?.job_id ? ` · ${impactSummary.scenario.job_id}` : ""}
            </p>
            <ImpactCategoryList value={impactCategory} onChange={setImpactCategory} summary={impactSummary} />
            <ImpactLegend />
            <p className="text-[10px] text-amber-200">
              Potential evacuation-risk analysis. Planning support. Not an official evacuation order.
            </p>
            {role !== "general" && (
              <ImpactPanel cityId={selectedCityId} visible preferredJobId={physicsJobId} />
            )}
          </div>
        )}
        {isSimulation && (
          <div className="space-y-3 border-b border-slate-800 px-4 py-3">
            <h1 className="text-lg font-semibold">{scenarioName || "Scenario simulation"}</h1>
            <p className="text-[11px] text-slate-400">
              {cityMetadata?.name || selectedCityId} · baseline {twinBaselineId || "UNAVAILABLE"} ·{" "}
              {String(twinScenarioJob?.status || twinBaselineMeta?.forcing?.status || "UNAVAILABLE").toUpperCase()}
            </p>
            <CitySelector selectedCityId={selectedCityId} onCityChange={handleCityChange} />
            <ScenarioControls
              cityId={selectedCityId}
              cityName={cityMetadata?.name}
              baseline={twinBaselineMeta}
              capabilities={twinCapabilities}
              history={twinHistory}
              rainfallMultiplier={rainfallMultiplier}
              onRainfallMultiplier={setRainfallMultiplier}
              riverDeltaM={riverDeltaM}
              onRiverDeltaM={setRiverDeltaM}
              scenarioName={scenarioName}
              onScenarioName={setScenarioName}
              selectedBaselineId={twinBaselineId}
              onSelectBaseline={setTwinBaselineId}
              pending={scenarioPending}
              error={scenarioError}
              onRun={handleTwinRun}
              onOpenHistory={() => setMobileExplorePanel("analysis")}
            />
            <JobProgressPanel
              jobId={physicsJobId}
              visible
              onComplete={handlePhysicsJobComplete}
            />
            <p className="text-[10px] text-amber-200">
              Rainfall multiplier is applied by the existing physics adapter. River-level change is stored only.
            </p>
          </div>
        )}
        {isHistory && (
          <div className="space-y-3 border-b border-slate-800 px-4 py-3">
            <div className="flex gap-2">
              <button
                type="button"
                className={`rounded px-2 py-1 text-[11px] ${historyTab === "events" ? "bg-sky-500/20 text-sky-100" : "text-slate-400"}`}
                onClick={() => setHistoryTab("events")}
              >
                Events
              </button>
              <button
                type="button"
                className={`rounded px-2 py-1 text-[11px] ${historyTab === "performance" ? "bg-sky-500/20 text-sky-100" : "text-slate-400"}`}
                onClick={() => setHistoryTab("performance")}
              >
                Model performance
              </button>
            </div>
            {historyTab === "events" ? (
              <HistoryCatalog
                events={historyEvents}
                selectedId={selectedHistoryEventId}
                onSelect={(row) => {
                  setSelectedHistoryEventId(row.event_id);
                  setHistoryPredictionId("");
                  setHistoryReport(null);
                }}
                filters={historyFilters}
                onFilterChange={setHistoryFilters}
                status={historyCatalogStatus}
              />
            ) : (
              <ModelPerformanceCenter
                payload={modelPerformance}
                selectedId={selectedModelId}
                onSelect={(row) => setSelectedModelId(row.id)}
              />
            )}
          </div>
        )}
        <div className={dedicatedWorkspace ? "hidden" : undefined} hidden={dedicatedWorkspace} aria-hidden={dedicatedWorkspace}>
        <div className="border-b border-slate-800 px-4 py-3">
          <div className="flex items-center justify-between gap-2">
            <div className="flex-1">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-flood-100">
                Observe → Decide
              </p>
              <h1 className="mt-1 text-lg font-semibold">Risk summary</h1>
              <p className="mt-1 text-sm text-slate-400">
                {cityMetadata?.name || metadata?.center?.label || "Sunamganj"}
              </p>
            </div>
            {activeScenario && <div className="status-active">Modeled</div>}
          </div>
        </div>

        <div className="border-b border-slate-800 px-5 py-3">
          <CitySelector
            selectedCityId={selectedCityId}
            onCityChange={handleCityChange}
          />
        </div>
        <div className="border-b border-slate-800 px-5 py-3">
          <StatusPanel status={regionStatus} error={statusError} />
          <div className="mt-3">
            <ForecastPanel
              forecast={regionStatus?.forecast}
              visible={platformView === "forecast" || platformView === "explore"}
              cityId={selectedCityId}
              onOverlayChange={handleForecastOverlay}
              onJobQueued={(job) => setPhysicsJobId(job.job_id || job.id)}
              horizon={timelineHorizon}
              onHorizonChange={setTimelineHorizon}
              canWriteJobs={role !== "general"}
            />
            <JobProgressPanel
              jobId={physicsJobId}
              visible={platformView === "forecast" || platformView === "simulation"}
              onComplete={handlePhysicsJobComplete}
            />
            <RiverForecastPanel
              riverId={selectedRiver?.id || selectedRiver?.river_id || "buriganga"}
              cityId={selectedCityId}
              visible={platformView === "forecast" || platformView === "explore"}
            />
            <ImpactPanel
              cityId={selectedCityId}
              visible={platformView === "impact"}
              preferredJobId={physicsJobId}
            />
            <AlertsPanel cityId={selectedCityId} visible={platformView === "alerts"} role={role} />
            <LocationsPanel
              cityId={selectedCityId}
              cityName={cityMetadata?.name}
              latitude={searchMarker?.latitude ?? cityMetadata?.center_lat}
              longitude={searchMarker?.longitude ?? cityMetadata?.center_lon}
              zoom={zoomLevel}
              riverId={selectedRiver?.id || selectedRiver?.river_id}
              layers={Object.keys(exploreLayers).filter((key) => exploreLayers[key])}
              onRestore={handleRestoreLocation}
              visible={platformView === "locations"}
            />
            <ReportsPanel
              cityId={selectedCityId}
              visible={platformView === "reports"}
              baselineJob={twinBaselineId || jobAId}
              scenarioJob={twinScenarioId || jobBId}
              eventId={selectedHistoryEventId}
              mapState={{
                city_id: selectedCityId,
                zoom: zoomLevel,
                latitude: searchMarker?.latitude ?? cityMetadata?.center_lat,
                longitude: searchMarker?.longitude ?? cityMetadata?.center_lon,
                layers: Object.keys(exploreLayers).filter((key) => exploreLayers[key]),
                river_id: selectedRiver?.id || selectedRiver?.river_id,
              }}
            />
            <AdminCenter
              cityId={selectedCityId}
              visible={platformView === "admin"}
              onSelectJob={(job) => setPhysicsJobId(job.job_id || job.id)}
            />
            <ModelStatusPanel visible={platformView === "forecast" || platformView === "research"} />
            <ResearchCenter visible={platformView === "research"} role={role} />
            {platformView === "research" && (
              <ModelPerformanceCenter
                payload={modelPerformance}
                selectedId={selectedModelId}
                onSelect={(row) => setSelectedModelId(row.id)}
              />
            )}
            <CapabilityMatrix visible={platformView === "research"} />
            <ScenarioJobsPanel
              cityId={selectedCityId}
              visible={(platformView === "forecast" || platformView === "simulation") && role !== "general"}
              onJobQueued={(job) => {
                setPhysicsJobId(job.job_id || job.id);
                if (job.job_id || job.id) {
                  setJobBId(job.job_id || job.id);
                }
              }}
            />
            <DataSourcesPanel
              cityId={selectedCityId}
              visible={platformView === "explore" || platformView === "reports"}
            />
          </div>
        </div>

        {showSimControls && (
        <ComparisonPanel
          compareMode={compareMode}
          onToggle={setCompareMode}
          cityId={selectedCityId}
          cityName={cityMetadata?.name}
          scenarioOptions={cityScenarios}
          scenarioAId={scenarioAId}
          scenarioBId={scenarioBId}
          onScenarioAChange={(value) => {
            setScenarioAId(value);
            setActiveSlot("A");
          }}
          onScenarioBChange={(value) => {
            setScenarioBId(value);
            setActiveSlot("B");
          }}
          comparisonMode={comparisonMode}
          onComparisonModeChange={setComparisonMode}
          comparisonLayer={comparisonLayer}
          onComparisonLayerChange={setComparisonLayer}
          comparisonResult={comparisonResult}
          comparisonError={comparisonError}
          scenarioA={scenarioA}
          scenarioB={scenarioB}
          jobCompare={{
            jobA: jobAId,
            jobB: jobBId,
            onJobAChange: setJobAId,
            onJobBChange: setJobBId,
            onCompare: handleJobCompare,
            result: jobCompareResult,
            error: jobCompareError,
            loading: jobCompareLoading,
          }}
        />
        )}

        <div className="flex-1 space-y-6 overflow-y-auto px-4 py-4">
          {(showSimControls || platformView === "simulation") && (
            <>
          <ScenarioPresets onSelectPreset={handleSelectPreset} />

          <section className="glass-panel rounded-lg px-4 py-3">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
              Scenario Parameters
            </h2>
            <div className="grid grid-cols-2 gap-3">
              <label className="text-sm">
                <span className="mb-1 block text-slate-400">Grid Nx</span>
                <input
                  type="number"
                  min="5"
                  max="300"
                  value={params.nx}
                  onChange={(event) => handleParamChange("nx", event.target.value)}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2"
                />
              </label>
              <label className="text-sm">
                <span className="mb-1 block text-slate-400">Grid Ny</span>
                <input
                  type="number"
                  min="5"
                  max="300"
                  value={params.ny}
                  onChange={(event) => handleParamChange("ny", event.target.value)}
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2"
                />
              </label>
              <label className="col-span-2 text-sm">
                <span className="mb-1 block text-slate-400">Rainfall Rate (m/s)</span>
                <input
                  type="number"
                  step="0.000001"
                  min="0"
                  value={params.rainfall_rate}
                  onChange={(event) =>
                    handleParamChange("rainfall_rate", event.target.value)
                  }
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2"
                />
              </label>
              <label className="col-span-2 text-sm">
                <span className="mb-1 block text-slate-400">Duration (s)</span>
                <input
                  type="number"
                  step="0.5"
                  min="0.5"
                  value={params.duration_seconds}
                  onChange={(event) =>
                    handleParamChange("duration_seconds", event.target.value)
                  }
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2"
                />
              </label>
            </div>
            <button
              type="button"
              onClick={handleRunScenario}
              disabled={loading}
              className="mt-4 w-full rounded-lg bg-flood-700 px-4 py-3 text-sm font-semibold text-white transition hover:bg-flood-500 disabled:cursor-not-allowed disabled:bg-slate-700"
            >
              {loading
                ? "Running Scenario..."
                : compareMode
                  ? `Run Scenario ${activeSlot}`
                  : "Run Scenario"}
            </button>
          </section>
            </>
          )}

          <section className="glass-panel rounded-lg px-4 py-3">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
              City-Wide Statistics
            </h2>
            {renderStatistics(activeScenario?.runResult)}
          </section>

          <section className="glass-panel rounded-lg px-4 py-3">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
              Visualization Layers
            </h2>
            <div className="space-y-2">
              {FLOOD_LAYER_OPTIONS.map((layer) => (
                <label
                  key={layer.id}
                  className="flex items-center justify-between rounded-lg border border-slate-700/50 bg-slate-800/30 px-3 py-2 text-sm transition hover:border-slate-600 hover:bg-slate-800/50"
                >
                  <span>{layer.label}</span>
                  <input
                    type="radio"
                    name="visual-layer"
                    checked={activeLayerId === layer.id}
                    onChange={() => setActiveLayerId(layer.id)}
                    className="accent-flood-500"
                  />
                </label>
              ))}
            </div>
            <h3 className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Infrastructure Layers
            </h3>
            <div className="space-y-2">
              {INFRA_LAYER_OPTIONS.map((layer) => (
                <label
                  key={layer.id}
                  className="flex items-center justify-between rounded-lg border border-slate-700/50 bg-slate-800/30 px-3 py-2 text-sm transition hover:border-slate-600 hover:bg-slate-800/50"
                >
                  <div className="flex items-center gap-2">
                    <span>{layer.label}</span>
                    {infraLayers[layer.id] && (
                      <span className="status-active">enabled</span>
                    )}
                  </div>
                  <input
                    type="checkbox"
                    checked={infraLayers[layer.id]}
                    onChange={() => handleInfraToggle(layer.id)}
                    className="accent-flood-500"
                  />
                </label>
              ))}
            </div>
            {overlayLoading && (
              <p className="mt-2 text-xs text-slate-400">Refreshing overlay...</p>
            )}
          </section>

          {metadata && (
            <section className="glass-panel rounded-lg px-4 py-3 text-sm text-slate-300">
              <p>
                <span className="text-slate-400">CRS:</span> {metadata.crs}
              </p>
              <p className="mt-1">
                <span className="text-slate-400">Playback:</span> {formattedCurrent} /{" "}
                {formattedDuration}
              </p>
            </section>
          )}

          {error && (
            <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200">
              {error}
            </div>
          )}
        </div>
        </div>
      </aside>

      <main id="command-map" className="relative flex min-h-0 flex-1 flex-col" tabIndex={-1}>
        <div className="relative min-h-0 flex-1">
        {isSimulation && twinMapMode === "split" && twinBaselineOverlay && twinScenarioOverlay ? (
          <div className="grid h-full grid-cols-2 gap-1">
            <FloodMap
              mapCenter={mapCenter}
              metadata={metadata}
              studyBounds={studyBounds}
              studyCenter={studyCenter}
              overlayUrl={twinBaselineOverlay}
              overlayBounds={overlayBounds}
              showFloodOverlay
              infraLayers={infraLayers}
              cityId={selectedCityId}
              inspectionPin={null}
              searchMarker={searchMarker}
              flyTarget={flyTarget}
              hasSimulation
              onInspect={handleInspect}
              onZoomChange={setZoomLevel}
              zoomLevel={zoomLevel}
              title="Baseline"
              viewport={syncedViewport}
              onViewportChange={setSyncedViewport}
            />
            <FloodMap
              mapCenter={mapCenter}
              metadata={metadata}
              studyBounds={studyBounds}
              studyCenter={studyCenter}
              overlayUrl={twinScenarioOverlay}
              overlayBounds={overlayBounds}
              showFloodOverlay
              infraLayers={infraLayers}
              cityId={selectedCityId}
              inspectionPin={inspection}
              searchMarker={searchMarker}
              flyTarget={flyTarget}
              hasSimulation
              onInspect={handleInspect}
              onZoomChange={setZoomLevel}
              zoomLevel={zoomLevel}
              title="Scenario"
              viewport={syncedViewport}
              onViewportChange={setSyncedViewport}
            />
          </div>
        ) : isSimulation && twinMapMode === "difference" && twinDiffOverlay ? (
          <FloodMap
            mapCenter={mapCenter}
            metadata={metadata}
            studyBounds={studyBounds}
            studyCenter={studyCenter}
            overlayUrl={twinDiffOverlay}
            overlayBounds={overlayBounds}
            showFloodOverlay
            infraLayers={infraLayers}
            cityId={selectedCityId}
            inspectionPin={inspection}
            searchMarker={searchMarker}
            flyTarget={flyTarget}
            hasSimulation
            onInspect={handleInspect}
            onZoomChange={setZoomLevel}
            zoomLevel={zoomLevel}
            title="SCENARIO − BASELINE (absolute difference)"
          />
        ) : compareMode && scenarioA && scenarioB && comparisonMode === "SWIPE" ? (
          <SwipeCompareMap
            overlayA={scenarioAOverlay}
            overlayB={scenarioBOverlay}
            overlayBounds={overlayBounds}
            mapCenter={mapCenter}
            metadata={metadata}
            studyBounds={studyBounds}
            studyCenter={studyCenter}
            infraLayers={infraLayers}
            cityId={selectedCityId}
            swipePercent={swipePercent}
            onSwipeChange={setSwipePercent}
            viewport={syncedViewport}
            onViewportChange={setSyncedViewport}
            onZoomChange={setZoomLevel}
            zoomLevel={zoomLevel}
            hasSimulation
            onInspect={handleInspect}
            searchMarker={searchMarker}
            flyTarget={flyTarget}
          />
        ) : compareMode && scenarioA && scenarioB && comparisonMode === "DIFFERENCE" ? (
          <FloodMap
            mapCenter={mapCenter}
            metadata={metadata}
            studyBounds={studyBounds}
            studyCenter={studyCenter}
            overlayUrl={differenceOverlay}
            overlayBounds={overlayBounds}
            showFloodOverlay
            infraLayers={infraLayers}
            cityId={selectedCityId}
            inspectionPin={inspection}
            searchMarker={searchMarker}
            flyTarget={flyTarget}
            hasSimulation
            onInspect={handleInspect}
            onZoomChange={setZoomLevel}
            zoomLevel={zoomLevel}
            title="Difference A − B"
          />
        ) : compareMode && scenarioA && scenarioB ? (
          <div className="grid h-full grid-cols-2 gap-1">
            <FloodMap
              mapCenter={mapCenter}
              metadata={metadata}
              studyBounds={studyBounds}
              studyCenter={studyCenter}
              overlayUrl={scenarioAOverlay}
              overlayBounds={overlayBounds}
              showFloodOverlay
              infraLayers={infraLayers}
              cityId={selectedCityId}
              inspectionPin={null}
              searchMarker={searchMarker}
              flyTarget={flyTarget}
              hasSimulation
              onInspect={handleInspect}
              onZoomChange={setZoomLevel}
              zoomLevel={zoomLevel}
              title="Scenario A"
              viewport={syncedViewport}
              onViewportChange={setSyncedViewport}
            />
            <FloodMap
              mapCenter={mapCenter}
              metadata={metadata}
              studyBounds={studyBounds}
              studyCenter={studyCenter}
              overlayUrl={scenarioBOverlay}
              overlayBounds={overlayBounds}
              showFloodOverlay
              infraLayers={infraLayers}
              cityId={selectedCityId}
              inspectionPin={inspection}
              searchMarker={searchMarker}
              flyTarget={flyTarget}
              hasSimulation
              onInspect={handleInspect}
              onZoomChange={setZoomLevel}
              zoomLevel={zoomLevel}
              title="Scenario B"
              viewport={syncedViewport}
              onViewportChange={setSyncedViewport}
            />
          </div>
        ) : (
          <>
          <FloodMap
            mapCenter={mapCenter}
            metadata={metadata}
            studyBounds={studyBounds}
            studyCenter={studyCenter}
            overlayUrl={isHistory ? null : isSimulation ? twinScenarioOverlay || twinBaselineOverlay || activeOverlayUrl : activeOverlayUrl}
            overlayBounds={overlayBounds}
            showFloodOverlay={isHistory ? false : isExplore ? exploreLayers.floodExtent : true}
            forecastOverlayUrl={
              (platformView === "forecast" || platformView === "explore") &&
              showForecastOverlay &&
              (!isExplore || exploreLayers.forecast)
                ? forecastOverlayUrl
                : null
            }
            floodSummary={floodSummary}
            onOsmInspect={(payload) => {
              setOsmInspect(payload);
              if (payload) {
                const match = impactAssets.find(
                  (row) =>
                    row.id === payload.id ||
                    (row.name === payload.name && row.asset_type === payload.type)
                );
                setSelectedImpactAsset(match || payload);
              }
            }}
            infraLayers={infraLayers}
            cityId={selectedCityId}
            inspectionPin={inspection}
            searchMarker={searchMarker}
            flyTarget={flyTarget}
            hasSimulation={Boolean(activeScenario || twinScenarioOverlay || twinBaselineOverlay)}
            onInspect={handleInspect}
            onZoomChange={setZoomLevel}
            zoomLevel={zoomLevel}
            showForecastOverlay={showForecastOverlay && (!isExplore || exploreLayers.forecast)}
            onToggleForecast={() => setShowForecastOverlay((value) => !value)}
            showRainfall={isExplore ? Boolean(exploreLayers.rainfall) : showRainfall}
            onToggleRainfall={() => {
              if (isExplore) {
                setExploreLayers((current) => ({ ...current, rainfall: !current.rainfall }));
              } else {
                setShowRainfall((value) => !value);
              }
            }}
            rainfallStatus={rainfallStatus}
            rainfallSummary={rainfallSummary}
            rainfallOverlayUrl={
              rainfallOverlayId && (isExplore ? exploreLayers.rainfall : showRainfall)
                ? artifactOverlayUrl(rainfallOverlayId)
                : null
            }
            terrainOverlayUrl={
              terrainOverlayId && (isExplore ? exploreLayers.terrain : showTerrain)
                ? artifactOverlayUrl(terrainOverlayId)
                : null
            }
            evacRoutes={isImpact ? impactEvacuation?.routes : null}
            showTerrain={isExplore ? Boolean(exploreLayers.terrain) : showTerrain}
            onToggleTerrain={() => {
              if (isExplore) {
                setExploreLayers((current) => ({ ...current, terrain: !current.terrain }));
              } else {
                setShowTerrain((value) => !value);
              }
            }}
            showRivers={isRiver ? true : isExplore ? exploreLayers.rivers : showRivers}
            onToggleRivers={() => setShowRivers((value) => !value)}
            onCoordinateSelect={handleCoordinateSelect}
            typeFilter={isExplore ? typeFilterFromLayers(exploreLayers, infraFilter) : ""}
            enabledTypes={
              isImpact
                ? impactEnabledTypes
                : isExplore
                  ? osmEnabledTypes
                  : isHistory
                    ? ["hospital", "school", "road", "shelter"]
                    : undefined
            }
            showLayerLegend={!isExplore && !isRiver && !isImpact && !isHistory}
            fitToken={fitToken}
            resetToken={resetToken}
            selectedRiverId={selectedRiver?.id || selectedRiver?.river_id}
            selectedSegmentId={selectedRiver?.segment_id}
            topologyHighlights={topologyHighlights}
            impactById={isImpact ? impactById : undefined}
            onRiverSelect={handleRiverSelect}
            regionSelected={selectedRegion}
            onRegionSelect={() => {
              setSelectedRegion(true);
              setSelectedRiver(null);
              setOsmInspect(null);
            }}
            selectionMode={isExplore ? selectionMode : "none"}
            selectionRect={selectionRect}
            onSelectionPoint={setSelectionRect}
          />
          {(dedicatedWorkspace) && (
            <ExploreMapControls
              onFitRegion={() => setFitToken((value) => value + 1)}
              onResetExtent={() => setResetToken((value) => value + 1)}
              latitude={searchMarker?.latitude}
              longitude={searchMarker?.longitude}
              showMobileActions
              onOpenLayers={() =>
                setMobileExplorePanel((current) => (current === "layers" ? null : "layers"))
              }
              onOpenAnalysis={() =>
                setMobileExplorePanel((current) => (current === "analysis" ? null : "analysis"))
              }
            />
          )}
          </>
        )}

        {searchNotice && (
          <div className="pointer-events-none absolute bottom-28 left-1/2 z-[1000] w-[min(520px,calc(100%-2rem))] -translate-x-1/2 rounded-xl border border-amber-400/40 bg-amber-500/15 px-4 py-3 text-sm text-amber-100 backdrop-blur">
            {searchNotice}
          </div>
        )}

        <TimePlaybackBar
          enabled={Boolean(activeScenario)}
          currentTime={currentTime}
          duration={duration}
          timeIndex={timeIndex}
          availableTimes={availableTimes}
          isPlaying={isPlaying}
          isCollapsed={isCollapsed}
          onToggleCollapse={() => setIsCollapsed((value) => !value)}
          onPlayPause={handlePlayPause}
          onReset={handleReset}
          onScrub={handleScrub}
        />

        <InspectionCard inspection={inspection} onClose={() => setInspection(null)} />
        {osmInspect && !isExplore && !isRiver && !isImpact && !isSimulation && !isHistory && (
          <div className="pointer-events-auto absolute bottom-28 right-6 z-[1000] w-72 rounded-xl border border-slate-200 bg-white/95 p-4 text-sm shadow-xl">
            <div className="mb-2 flex items-start justify-between">
              <p className="font-semibold text-slate-900">{osmInspect.name}</p>
              <button type="button" onClick={() => setOsmInspect(null)} className="text-slate-500">
                ×
              </button>
            </div>
            <p className="text-slate-600">{osmInspect.type}</p>
            <p className="mt-1 text-xs text-slate-500">
              Regional maximum depth{" "}
              {osmInspect.regional_max_depth_m == null
                ? "UNAVAILABLE"
                : `${Number(osmInspect.regional_max_depth_m).toFixed(3)} m`}
            </p>
            <p className="text-xs text-slate-500">Per-feature depth NOT_COMPUTED</p>
            <p className="text-xs text-slate-500">Accessibility {osmInspect.accessibility}</p>
          </div>
        )}
        <AssistantDock
          cityId={selectedCityId}
          visible={platformView !== "research"}
          role={role}
          context={{
            selected_region: selectedCityId || null,
            selected_coordinates: searchMarker
              ? { latitude: searchMarker.latitude, longitude: searchMarker.longitude }
              : null,
            selected_river: selectedRiver?.id || selectedRiver?.river_id || null,
            selected_segment: selectedRiver?.segment_id || null,
            active_layers: Object.keys(exploreLayers).filter((key) => exploreLayers[key]),
            active_scenario: scenarioName || twinScenarioId || null,
            baseline_id: twinBaselineId || jobAId || null,
            scenario_id: twinScenarioId || jobBId || null,
            forecast_horizon: timelineHorizon,
            current_data_status: regionStatus?.risk?.provenance?.data_status || null,
            selected_job: physicsJobId || twinScenarioId || null,
            selected_event_id: selectedHistoryEventId || null,
          }}
        />
        </div>
        {isImpact ? (
          <ImpactEvidence summary={impactSummary} selectedAsset={selectedImpactAsset} />
        ) : isSimulation ? (
          <ScenarioCompareBar
            workspace={twinWorkspace}
            baselineJob={twinBaselineJob}
            scenarioJob={twinScenarioJob}
            difference={twinDifference}
            impact={twinImpact}
            times={twinTimes}
            selectedTime={twinSelectedTime}
            onSelectTime={setTwinSelectedTime}
            onGenerateReport={handleTwinReport}
            report={twinReport}
          />
        ) : isHistory ? (
          <div>
            {historyTab === "events" && (
              <>
                <HistoryTimeline
                  observations={historyDetail?.timeline || []}
                  selectedId={historyObservation?.observation_id}
                  onSelect={setHistoryObservation}
                  statusText={
                    historyObservation
                      ? `OBSERVED ${historyObservation.timestamp || "timestamp UNAVAILABLE"} source ${historyObservation.source || "UNAVAILABLE"}`
                      : "No observation selected"
                  }
                />
                <HistoryCompareBar
                  predictions={historyDetail?.predictions || []}
                  compare={historyCompare}
                  selectedPredictionId={historyPredictionId}
                  onSelectPrediction={(row) => setHistoryPredictionId(row.prediction_id)}
                  onGenerateReport={handleHistoryReport}
                  report={historyReport}
                  generating={historyReportPending}
                />
              </>
            )}
          </div>
        ) : isRiver ? (
          <RiverTimeSeries observations={riverObservations} />
        ) : isExplore ? (
          <ExploreTimeline
            cityId={selectedCityId}
            forecast={regionStatus?.forecast}
            selectedTime={exploreTime}
            onSelectTime={(key) => setExploreTime(key)}
          />
        ) : (
          <ForecastTimeline
            forecast={regionStatus?.forecast}
            horizon={timelineHorizon}
            onHorizonChange={setTimelineHorizon}
            cityId={selectedCityId}
          />
        )}
      </main>
      <aside
        className={`z-[1100] shrink-0 flex-col gap-3 overflow-y-auto border-l border-slate-800 bg-slate-950 px-3 py-3 text-slate-100 ${
          dedicatedWorkspace
            ? `explore-right w-80 ${mobileExplorePanel === "analysis" ? "explore-sheet-open" : "max-lg:hidden"} lg:flex`
            : "flex w-80"
        }`}
      >
        {isImpact ? (
          <>
            <ImpactSummaryPanel
              summary={impactSummary}
              role={role}
              selectedAsset={selectedImpactAsset}
              onSelectAsset={setSelectedImpactAsset}
              assets={impactAssets}
            />
            {role !== "general" && <ShelterPanel shelters={impactShelters} />}
            {role !== "general" && <EvacuationPanel evacuation={impactEvacuation} />}
            <ResourcePlanningPanel
              resources={impactResources}
              allowed={role === "emergency" || role === "admin"}
            />
            <button
              type="button"
              className="text-left text-[11px] text-sky-300 underline"
              onClick={() => setPlatformView("explore")}
            >
              Return to map
            </button>
          </>
        ) : isSimulation ? (
          <>
            <ScenarioSummary
              cityName={cityMetadata?.name}
              workspace={twinWorkspace}
              baselineJob={twinBaselineJob}
              scenarioJob={twinScenarioJob}
              impact={twinImpact}
              mapMode={twinMapMode}
              onMapMode={setTwinMapMode}
            />
            <ScenarioHistory
              history={twinHistory}
              selectedId={twinScenarioId || twinBaselineId}
              onSelect={(row) => {
                const id = row.job_id || row.id;
                if (Number(row.rainfall_multiplier) === 1) {
                  setTwinBaselineId(id);
                  setTwinBaselineJob(row);
                } else {
                  setTwinScenarioId(id);
                  setTwinScenarioJob(row);
                  setPhysicsJobId(id);
                }
                setTwinRefresh((value) => value + 1);
              }}
            />
            <ReportsPanel cityId={selectedCityId} visible />
            {twinDifference && !twinDifference.available && (
              <p className="text-[11px] text-amber-200">{twinDifference.reason}</p>
            )}
            <p className="text-[10px] text-slate-500">
              Analysis generated at {twinWorkspace?.generated_at || twinScenarioJob?.completed_at || "UNAVAILABLE"}.
              Not a live flood map.
            </p>
          </>
        ) : isHistory ? (
          historyTab === "events" ? (
            <HistorySummary
              detail={historyDetail}
              observation={historyObservation}
              compare={historyCompare}
            />
          ) : (
            <ModelPerformanceCenter
              payload={modelPerformance}
              selectedId={selectedModelId}
              onSelect={(row) => setSelectedModelId(row.id)}
            />
          )
        ) : isRiver ? (
          <RiverIntelligencePanel
            overview={riverOverview}
            segment={riverSegmentDetail}
            neighbors={riverNeighbors}
            observations={riverObservations}
            risk={regionStatus?.risk}
            onOpenForecast={() => setPlatformView("forecast")}
            onOpenScenario={() => setPlatformView("simulation")}
            onOpenExplore={() => setPlatformView("explore")}
            onSelectNeighbor={(row) =>
              handleRiverSelect({
                id: selectedRiverId,
                river_id: selectedRiverId,
                name: activeRiverRecord?.name,
                segment_id: row.id,
              })
            }
          />
        ) : isExplore ? (
          <SelectedAreaPanel
            cityName={cityMetadata?.name}
            cityId={selectedCityId}
            selection={{
              latitude: searchMarker?.latitude ?? inspection?.latitude,
              longitude: searchMarker?.longitude ?? inspection?.longitude,
              region_id: searchMarker?.region_id || selectedCityId,
            }}
            risk={regionStatus?.risk}
            flood={{
              status:
                activeOverlayUrl || forecastOverlayUrl
                  ? "overlay attached (physics/scenario or DEMO heuristic)"
                  : null,
              probability: (regionStatus?.forecast?.horizons || []).find(
                (row) => row.horizon_hours === timelineHorizon
              )?.flood_probability,
              horizon: `${timelineHorizon}h heuristic (DEMO)`,
              depth_m: inspection?.depth ?? inspection?.depth_m ?? null,
              exposure: regionStatus?.risk?.exposure,
              source: floodSummary?.source || regionStatus?.forecast?.provenance?.provider,
              timestamp: floodSummary?.created_at || regionStatus?.forecast?.provenance?.retrieved_at,
            }}
            forecast={regionStatus?.forecast}
            river={selectedRiver}
            infrastructure={osmInspect}
            nearby={nearbyInfra}
            dataStatus={{
              source: regionStatus?.risk?.provenance?.provider || regionStatus?.forecast?.provenance?.provider,
              dataset: regionStatus?.risk?.provenance?.dataset,
              status: regionStatus?.risk?.provenance?.data_status,
              freshness: regionStatus?.risk?.provenance?.freshness,
              fallbackUsed: regionStatus?.risk?.provenance?.fallback_used,
              note: "LIVE is never claimed unless a source genuinely qualifies.",
            }}
            onOpenForecast={() => setPlatformView("forecast")}
            onOpenRiver={() => setPlatformView("river")}
            onOpenImpact={() => setPlatformView("impact")}
          />
        ) : (
          <>
        <AlertsPanel cityId={selectedCityId} visible={platformView !== "research"} />
        <JobsListPanel
          visible={role !== "general"}
          onSelectJob={(job) => setPhysicsJobId(job.job_id || job.id)}
        />
        {role === "general" && (
          <p className="text-[11px] text-slate-500">Recent simulations: UNAVAILABLE for General role (jobs.read).</p>
        )}
        <ModelStatusPanel visible={platformView === "explore"} />
        <DataHealthPanel cityId={selectedCityId} visible={role === "emergency" || role === "admin"} />
        {regionStatus?.command && (
          <section className="glass-panel rounded-lg px-4 py-3 text-xs text-slate-300">
            <h2 className="mb-1 font-semibold uppercase tracking-wide text-slate-400">High-risk / KPIs</h2>
            <p>Risk {regionStatus.command.current_risk}</p>
            <p>
              {regionStatus.command.population_exposed == null
                ? "POPULATION EXPOSURE: UNAVAILABLE"
                : `POPULATION EXPOSURE: ${regionStatus.command.population_exposed}`}
            </p>
            <p>Hospitals at risk: {regionStatus.command.hospitals_at_risk == null ? "UNAVAILABLE" : regionStatus.command.hospitals_at_risk}</p>
            <p className="text-amber-200">{regionStatus.command.disclaimer}</p>
          </section>
        )}
          </>
        )}
      </aside>
    </div>
    </RoleShell>
  );
}
