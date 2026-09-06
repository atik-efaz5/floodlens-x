import { useMemo, useState } from "react";

export function useScenarioComparison() {
  const [compareMode, setCompareMode] = useState(false);
  const [scenarioA, setScenarioA] = useState(null);
  const [scenarioB, setScenarioB] = useState(null);
  const [activeSlot, setActiveSlot] = useState("A");

  const comparisonStats = useMemo(() => {
    if (!scenarioA?.runResult || !scenarioB?.runResult) {
      return null;
    }

    return {
      deltaMaxDepth:
        scenarioB.runResult.max_depth_m - scenarioA.runResult.max_depth_m,
      deltaFloodedArea:
        scenarioB.runResult.flooded_area_km2 - scenarioA.runResult.flooded_area_km2,
    };
  }, [scenarioA, scenarioB]);

  const saveScenario = (snapshot) => {
    if (activeSlot === "A") {
      setScenarioA(snapshot);
    } else {
      setScenarioB(snapshot);
    }
  };

  return {
    compareMode,
    setCompareMode,
    scenarioA,
    scenarioB,
    activeSlot,
    setActiveSlot,
    comparisonStats,
    saveScenario,
  };
}
