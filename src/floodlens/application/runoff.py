"""SIMPLE_RUNOFF_BASELINE: convert precipitation mm to SWE rainfall rate (m/s).

Assumptions (explicit):
- Open-Meteo hourly precipitation is treated as mm accumulated in that hour
  (equivalent to mm/h for that forcing snapshot).
- Conversion: m/s = (mm / 1000) / 3600.
- runoff_coefficient default 1.0: all rain becomes surface water, matching the
  existing shallow-water source term (no infiltration). Values in (0, 1]
  scale effective precipitation. There is no undocumented constant.
"""

from __future__ import annotations

RUNOFF_METHOD = "SIMPLE_RUNOFF_BASELINE"
DEFAULT_RUNOFF_COEFFICIENT = 1.0
MM_TO_MPS = 1.0 / 1000.0 / 3600.0


def precip_mm_to_mps(precip_mm: float, runoff_coefficient: float = DEFAULT_RUNOFF_COEFFICIENT) -> float:
    if precip_mm < 0:
        raise ValueError(f"precipitation_mm cannot be negative: {precip_mm}")
    if runoff_coefficient <= 0 or runoff_coefficient > 1:
        raise ValueError("runoff_coefficient must be in (0, 1]")
    return float(precip_mm) * MM_TO_MPS * float(runoff_coefficient)


def runoff_metadata(runoff_coefficient: float = DEFAULT_RUNOFF_COEFFICIENT) -> dict:
    return {
        "runoff_method": RUNOFF_METHOD,
        "runoff_coefficient": runoff_coefficient,
        "units": {"precipitation": "mm", "rainfall_rate": "m/s"},
        "equation": "effective_mps = (precip_mm / 1000 / 3600) * runoff_coefficient",
    }
