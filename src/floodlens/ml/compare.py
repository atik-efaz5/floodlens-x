"""Fair comparison protocol: persistence / heuristic / physics SWE burst / AI.

Physics is scored against the same labels with an explicit clock footnote.
"""

from __future__ import annotations

from typing import Optional, Sequence

from floodlens.application.forecast import HeuristicForecastProvider
from floodlens.ml.baselines import evaluate_baselines, fit_baselines
from floodlens.ml.schema import ForecastSample

PHYSICS_FOOTNOTE = (
    "Physics Baseline v0.1 is a short shallow-water burst forced by forecast rain "
    "at t+h. Solver seconds are not meteorological hours and this is not a 24 h "
    "inundation model. A worse or better score here is not a ranking of 'AI vs hydrodynamics'."
)

COMPARISON_NOT_YET_COMPARABLE = (
    "COMPARISON NOT YET COMPARABLE. Spatial AI maps 8-day GFM occurrence. "
    "Physics is a sub-second SWE burst on ~16×16 cells, not a 6–72 h inundation forecast. "
    "Compare spatial AI only to spatial persistence / climatology / JRC RP lookup, not to this burst."
)

SURROGATE_NOTE = (
    "Optional SURROGATE table (AI vs physics flood_fraction) trains or scores against "
    "SWE output. That is an emulator experiment, not operational skill."
)


def comparison_table(samples: Sequence[ForecastSample], track: str = "A") -> dict:
    fitted = fit_baselines(samples, track=track)
    val = evaluate_baselines(samples, fitted, "val")
    test = evaluate_baselines(samples, fitted, "test")
    heuristic = HeuristicForecastProvider().forecast("dhaka")
    return {
        "track": track,
        "label_kind": "MODELLED" if track == "A" else "OBSERVED",
        "val": val,
        "test": test,
        "heuristic": {
            "status": "IMPLEMENTED",
            "model_kind": "HEURISTIC",
            "data_status": "DEMO",
            "note": "Deployed heuristic nowcast. Scored separately from learned models.",
            "horizons": heuristic.get("horizons"),
        },
        "physics": {
            "status": "IMPLEMENTED",
            "model_kind": "PHYSICS_BASELINE",
            "clock": "solver_seconds_not_meteorological_hours",
            "footnote": PHYSICS_FOOTNOTE,
        },
        "ai": {
            "status": "TRAINED_EXPERIMENT" if val.get("n") else "NOT_TRAINED",
            "promoted_to_catalog": False,
            "note": "Catalog remains NOT_TRAINED until VALIDATED on real labels.",
        },
        "hybrid": {"status": "NOT_IMPLEMENTED", "design": "residual correction later (4.7+)"},
        "surrogate": {"status": "NOT_RUN", "note": SURROGATE_NOTE},
        "ranking_claim": None,
        "accuracy_claim": None,
        "footnote": PHYSICS_FOOTNOTE,
        "comparable_to_physics": False,
        "comparison_status": "COMPARISON NOT YET COMPARABLE",
        "comparison_note": COMPARISON_NOT_YET_COMPARABLE,
    }


def physics_binary_from_fraction(flood_fraction: Optional[float], threshold: float = 0.0) -> Optional[int]:
    if flood_fraction is None:
        return None
    return 1 if float(flood_fraction) > threshold else 0
