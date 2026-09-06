# FloodLens: 2D Hydrodynamic Flood Simulation Engine

FloodLens is a high-performance, vectorized 2D shallow-water finite-volume hydrodynamic modeling framework designed for overland flood simulation, complex topography routing, and real-time scenario analysis.

---

## Key Features

- **Robust Hydrodynamic Core**: Vectorized 2D shallow-water solver using hydrostatic reconstruction (Audusse et al.) and Rusanov numerical fluxes.
- **Well-Balanced & Stable**: Exact C-property preservation for lake-at-rest steady states (< 1e-14 error) and semi-implicit Manning friction regularization preventing thin-sheet wetting front velocity singularities.
- **Hydrological Integration**: Fully coupled mass-conserving rainfall and non-negative infiltration source terms.
- **Configurable Boundary Conditions**: Support for reflective (wall) and transmissive (open/outflow) boundary conditions via ghost-cell padding.
- **Layered Architecture**: Strictly decoupled numerical kernels, simulation core, application services, and visualization pipelines.
- **Production CLI & Python API**: Unified execution interfaces for both programmatic workflows and terminal batch pipelines.

---

## Installation

```bash
# Clone repository
git clone https://github.com/your-org/floodlens-x.git
cd floodlens-x

# Install in editable mode
pip install -e .

# Run test suite (optional: deselect the known xgboost quarantine)
pytest tests --deselect tests/test_phase4_baselines.py::test_xgboost_beats_persistence_track_a_and_b
```

---

## Platform (Command Center)

The product UI is a Vite/React/Leaflet Command Center talking to FastAPI `/api/v1`. This is **LOCAL-DEMO**, not cloud-production.

**Live demo:** [https://floodlens-x.vercel.app](https://floodlens-x.vercel.app) — Vercel hosts the UI and rewrites `/api` to a Render FastAPI service (`FLOODLENS_DEMO_FIXTURES=1`). Render’s free instance sleeps after idle; the first request after sleep can take ~30s.

```bash
# API (from repo root)
export PYTHONPATH=src MPLCONFIGDIR=/tmp/mpl-floodlens
python -m uvicorn floodlens.application.web_server:app --host 127.0.0.1 --port 8000

# Frontend
cd frontend && npm install && npm run dev
```

Open `http://127.0.0.1:5173/`. Demo identity: `Authorization: Bearer demo.<general|emergency|researcher|admin>`.

Optional infra (`docker compose up`): PostGIS, Redis, MinIO. The API does not require them.

Environment template: `.env.example`. Do not commit secrets.

Scientific freeze: Spatial AI **NOT_VALIDATED**, spatial API **UNAVAILABLE**, Target B **PARTIALLY FEASIBLE**, model training **NOT AUTHORIZED**, solver `src/floodlens/numerical/**` unmodified.

See `docs/PHASE_7_9_FINAL_INTEGRATION_REPORT.md` for the capability matrix, RBAC, deployment classification, and known limitations.

---

## Quickstart

### 1. Command Line Interface (CLI)

Run a baseline simulation and export results:

```bash
floodlens \
  --nx 100 \
  --ny 100 \
  --lx 2000.0 \
  --ly 2000.0 \
  --t-end 60.0 \
  --cfl 0.8 \
  --manning-n 0.035 \
  --rainfall 1.388e-5 \
  --bc transmissive \
  --output-dir ./sim_results
```

Outputs generated in `./sim_results`:
- `flood_depth_map.png`: Instantaneous flood depth visualization.
- `simulation_result.npz`: Compressed hydrodynamic state tensor `(Nx, Ny, 3)` and elevation grid.

View all CLI options:

```bash
floodlens --help
```

---

### 2. Python API

```python
import numpy as np
from floodlens.core.config import SimulationConfig
from floodlens.application.dem_manager import DEMManager
from floodlens.application.service import SimulationService
from floodlens.visualization.layer import VisualizationLayer

# 1. Configure simulation
config = SimulationConfig(
    Nx=50,
    Ny=50,
    Lx=1000.0,
    Ly=1000.0,
    T_end=10.0,
    CFL=0.8,
    manning_n=0.03,
    boundary_condition="transmissive"
)

# 2. Setup topography
x = np.linspace(0, config.Lx, config.Nx)
y = np.linspace(0, config.Ly, config.Ny)
X, Y = np.meshgrid(x, y, indexing="ij")
z = 0.005 * ((X - 500)**2 + (Y - 500)**2)

# 3. Run scenario with rainfall
service = SimulationService(config)
result = service.run_scenario(
    dem=z,
    rainfall_rate=1e-4,
    steps=10,
    track_progress=False
)

# 4. Generate diagnostics & metrics
viz = VisualizationLayer()
metrics = viz.compute_metrics(result.final_state, config)
print(f"Inundated Area: {metrics['inundated_area']:.2f} m²")
print(f"Max Water Depth: {metrics['max_depth']:.4f} m")

# 5. Export figure headlessly
viz.plot_instantaneous_depth(result.final_state, z, save_path="flood_map.png")
```

---

## Architecture

FloodLens is organized into four decoupled layers:

### 1. Numerical Core (`src/floodlens/numerical/`)

Provides low-level 2D finite-volume kernels:

- **`flux.py`**: Physical flux functions (Rusanov, momentum, pressure gradient).
- **`reconstruction.py`**: Hydrostatic reconstruction at cell interfaces.
- **`riemann.py`**: Approximate Riemann solver implementation.
- **`sources.py`**: Bed-slope and Manning friction source terms.
- **`timestep.py`**: CFL-adaptive timestep selection.
- **`vectorized.py`**: NumPy-vectorized 2D kernel loops.
- **`boundary.py`**: Ghost-cell padding for reflective/transmissive boundaries.
- **`timestepper.py`**: Main explicit RK2 time integration loop.

### 2. Simulation Core (`src/floodlens/core/`)

Wraps numerical kernels in a stateful API:

- **`config.py`**: Immutable `SimulationConfig` dataclass.
- **`grid.py`**: Grid metrics (`GridData`).
- **`state.py`**: Hydrodynamic state snapshot (`SimulationState`).
- **`result.py`**: Final result payload (`SimulationResult`).
- **`diagnostics.py`**: Structured diagnostic report (`DiagnosticsReport`).
- **`simulator.py`**: High-level `ShallowWaterSimulator` and `ShallowWaterSimulatorWithDiagnostics`.

### 3. Application Layer (`src/floodlens/application/`)

Provides user-facing services:

- **`input_manager.py`**: Synthetic test terrain generators (parabolic bowl, etc.).
- **`dem_manager.py`**: Digital Elevation Model ingestion, validation, resampling.
- **`progress.py`**: Iteration progress telemetry and logging.
- **`service.py`**: High-level `SimulationService` orchestrating the full workflow.

### 4. Visualization Layer (`src/floodlens/visualization/`)

Produces publication-quality outputs:

- **`layer.py`**: `VisualizationLayer` with depth maps, velocity quiver plots, flood extent masks, and temporal analysis.

---

## Numerical Formulation

### Governing Equations

The framework solves the 2D conservative Shallow Water Equations (Saint-Venant system):

$$\frac{\partial U}{\partial t} + \frac{\partial F(U)}{\partial x} + \frac{\partial G(U)}{\partial y} = S_{\text{bed}}(U) + S_{\text{friction}}(U) + S_{\text{source}}$$

Where:

- **State vector**: $U = [h, hu, hv]^T$
  - $h$: Water depth (m)
  - $u, v$: Flow velocities (m/s)
- **Flux vectors**:
  - $F(U) = [hu, hu^2 + \frac{1}{2}gh^2, huv]^T$ (X-momentum flux)
  - $G(U) = [hv, huv, hv^2 + \frac{1}{2}gh^2]^T$ (Y-momentum flux)
- **Source terms**:
  - $S_{\text{bed}}$: Hydrostatic topography slope
  - $S_{\text{friction}}$: Semi-implicit Manning-Strickler friction: $f_n = -\frac{gn^2}{h^{1/3}}\sqrt{u^2 + v^2}$
  - $S_{\text{source}}$: Mass balance $(R - I)$ where $R$ = rainfall rate, $I$ = infiltration rate

### Spatial Discretization

- **Reconstruction**: Hydrostatic reconstruction with conservative momentum redistribution at cell interfaces.
- **Riemann Solver**: Approximate Rusanov solver with acoustic wave-speed estimators.
- **Flux Divergence**: Conservative finite-volume divergence on a structured Cartesian grid.
- **Dry-Cell Handling**: Strict threshold-based detection ($h \leq h_{\text{dry}}$) with momentum desingularization.

### Temporal Integration

- **Time Stepping**: Explicit 2nd-order Runge-Kutta (RK2).
- **CFL Stability**: Adaptive timestep selection $\Delta t = C \cdot \min(\Delta x / u_{\max}, \Delta y / v_{\max})$ where $C \in (0, 1.5)$ is user-configurable.
- **Infiltration Handling**: Non-negative depth preservation via clipping after mass source application.

---

## Testing & Verification

The test suite enforces machine-precision invariants against analytical solutions and baseline regression oracles:

```bash
pytest -v
```

### Validation Suites

| Module | Purpose | Key Tests |
|--------|---------|-----------|
| `test_equivalence.py` | Regression oracle baseline | Lake-at-rest (< 1e-14), dam-break equivalence |
| `test_sources.py` | Rainfall & infiltration | Zero-rain equivalence, mass conservation, non-negativity |
| `test_boundary.py` | Boundary condition symmetry | Reflective momentum flip, transmissive zero-gradient |
| `test_timestep.py` | CFL timestep selection | Dynamic scaling under flow, baseline maintenance |
| `test_sunamganj_forensics.py` | Steep DEM stability | Wetting-front velocity bounding (< 10 m/s) |
| `test_performance.py` | Vectorized kernel timing | Runtime scaling benchmarks |
| `test_api_integration.py` | Core API coherence | State persistence, diagnostics transparency |
| `test_e2e_pipeline.py` | End-to-end workflow | DEM resampling, multi-step simulation, export |
| `test_cli.py` | CLI entrypoint | Argument parsing, file export |

All 27 tests pass with zero warnings:

```
27 passed in 30.80s
```

---

## Configuration Reference

### SimulationConfig

```python
from floodlens.core.config import SimulationConfig

config = SimulationConfig(
    # Grid dimensions
    Nx=50,              # Cell count in X
    Ny=50,              # Cell count in Y
    Lx=1000.0,          # Domain width (m)
    Ly=1000.0,          # Domain height (m)
    
    # Physics
    g=9.81,             # Gravitational acceleration (m/s²)
    manning_n=0.03,     # Manning roughness coefficient
    
    # Numerics
    CFL=0.8,            # Courant safety coefficient
    dt_initial=0.01,    # Initial timestep (s)
    T_end=10.0,         # Simulation end time (s)
    h_dry_threshold=1e-4,  # Dry cell threshold (m)
    
    # Boundary conditions
    boundary_condition="reflective",  # "reflective" or "transmissive"
    
    # Metadata
    name="FloodLens_Simulation"
)
```

---

## Common Workflows

### Batch Simulation with Variable Rainfall

```python
import numpy as np
from floodlens.core.config import SimulationConfig
from floodlens.application.service import SimulationService
from floodlens.visualization.layer import VisualizationLayer

config = SimulationConfig(Nx=100, Ny=100, Lx=5000, Ly=5000, T_end=3600)
dem = np.random.rand(100, 100) * 10  # Synthetic elevation

rainfall_scenarios = [0.0, 1e-5, 5e-5, 1e-4]
service = SimulationService(config)
viz = VisualizationLayer()

for rain in rainfall_scenarios:
    result = service.run_scenario(dem=dem, rainfall_rate=rain, steps=20)
    metrics = viz.compute_metrics(result.final_state, config)
    print(f"Rain={rain:.2e}: Inundated Area={metrics['inundated_area']:.0f} m²")
```

### DEM Ingestion & Resampling

```python
from floodlens.application.dem_manager import DEMManager
from floodlens.core.config import SimulationConfig

dem_mgr = DEMManager()

# Load raw high-resolution DEM (e.g., from GeoTIFF)
raw_dem = np.load("high_res_dem.npy")  # 1000x1000

# Validate
validated = dem_mgr.validate_raw_input(raw_dem)

# Resample to simulation grid
config = SimulationConfig(Nx=100, Ny=100, Lx=10000, Ly=10000)
resampled = dem_mgr.resample_terrain(validated, config)  # 100x100
```

### Direct Lower-Level Access

```python
from floodlens.numerical.timestepper import run_shallow_water_simulation
import numpy as np

U = np.zeros((50, 50, 3), dtype=np.float64)
U[:, :, 0] = 1.0  # 1 m depth everywhere
z = np.zeros((50, 50))

U_final, frames = run_shallow_water_simulation(
    U_initial=U,
    z_field=z,
    dx=20.0,
    dy=20.0,
    t_end=10.0,
    dt_initial_sim=0.01,
    g=9.81,
    h_dry_threshold=1e-4,
    manning_n_sim=0.03,
    cfl_sim=0.8,
    bc_type="reflective",
    rainfall_rate_mps_sim=0.0,
    infiltration_rate_mps_sim=0.0,
    store_frames=False
)
```

---

## Performance

Vectorized kernels are optimized for CPU throughput. A typical 50×50 grid with 5 explicit RK2 timesteps executes in < 0.5 seconds on a modern multi-core processor.

For large-scale simulations (> 500×500), consider:
- Increasing `CFL` toward 0.9 (closer to stability boundary).
- Reducing output/diagnostic frequency.
- Using GPU-accelerated backends (future work).

---

## References

- Audusse, E., Bouchut, F., Bristeau, M., Klein, R., & Perthame, B. (2004). "A fast and stable well-balanced scheme with hydrostatic reconstruction for shallow water flows." *SIAM Journal on Scientific Computing*, 25(6), 2050–2065.

- Rusanov, V. V. (1961). "Calculation of interaction of non-stationary shock waves with obstacles." *Journal of Computational Mathematics and Mathematical Physics*, 1(2), 267–279.

- Manning, R. (1891). "On the flow of water in open channels and pipes." *Transactions of the Institution of Civil Engineers (Ireland)*, 20, 161–207.

---

## Contributing

Contributions are welcome. Please ensure:

1. All numerical changes are validated against regression oracles.
2. New tests are added to `tests/`.
3. Code follows the existing module structure and naming conventions.
4. The full test suite passes: `pytest -v`.

---

## License

See LICENSE file for terms.

---

## Contact

For questions or issues, please open a GitHub issue or contact the development team.
