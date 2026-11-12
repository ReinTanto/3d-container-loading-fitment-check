# 3D Container Loading Fitment Check — Release 1.0

A self-hosted REST API that answers one question:

> **Do these products fit in this container — and if so, how much space is left?**

Send the box dimensions and your products (dimensions + quantity). Get back a
boolean and the remaining space as a volume and a percentage. No credentials,
no external services, no network calls — all computation is local.

## What's in this release

### API (`POST /check`, `GET /health`)
- **Fit check** — send a container + one or more products (each with its own
  dimensions and quantity); get back `fits` (boolean) and the remaining space
  as both a **volume** and a **percentage**.
- **Multiple products, multiple dimensions, multiple quantities** in a single
  container, all in one request.
- **Exact placement of every unit** — `placements` returns the corner and
  placed (possibly rotated) dimensions of each unit, usable directly as
  loading instructions.
- **Optional weight limit** — set `box.max_weight` and per-unit `weight`; the
  result reports `weight_ok` and the total weight.
- **Per-product orientation** — `"any"` (unit may be rotated freely, all 6
  orientations) or `"fixed"` (unit must stay upright; only its base may swap).
- **Full-support rule (always on)** — every unit's entire bottom face must rest
  on solid support (the floor, or placed boxes whose combined top surface fully
  covers the base). **No ledges, no floating boxes**: a unit is never placed
  where part of its base would overhang into the air.
- **Deterministic** — the same request always returns the same answer.
- **OpenAPI / Swagger UI** at `/docs`, plus `GET /health` for liveness probes.
- **Permissive CORS** — callable from any origin (self-hosted, no credentials).

### 3D test frontend (self-contained, no build step)
- Enter the container size and products (name, dimensions, quantity, weight,
  orientation), press **Calculate & visualize**, and see the result rendered in
  three.js.
- Transparent container shell, one colour per product, ground grid + axes,
  orbit controls (rotate / zoom / pan), hover highlight with a tooltip, and
  camera auto-fit.
- **Client-side collision + containment check** — independently re-verifies that
  no two placed boxes overlap and that every box lies inside the container,
  surfaced in the HUD and result panel.
- **Requested vs. actually-placed volume** — when a load does not fit, the panel
  shows the total volume you requested against the volume that actually fit.
- **Static idle scene** — a sample load is shown on load so the view is never
  blank (no auto-rotation; orbit it manually).
- **Responsive** — the panel stacks above the 3D view on narrow screens.
- Styled after the visualizer in
  [skjolber/3d-bin-container-packing](https://github.com/skjolber/3d-bin-container-packing).

### Solver
- Extreme-points constructive heuristic, largest-first, 6-axis rotation, bounded
  multi-pass, accelerated with a 3D interval tree (octree) for fast collision
  and support queries.
- **Honesty caveat:** `fits: true` is reliable (a valid placement is returned).
  `fits: false` means this heuristic did not find an arrangement; it is not a
  proof that none exists.

### Documentation
- **API guide** (`docs/API.md`) — endpoints, request/response reference, worked
  examples, client snippets (Python / JS / cURL), error handling, semantics &
  guarantees, performance.
- **3D view guide** (`docs/3D-VIEW.md`) — how the visualization works and how to
  build your own (with a minimal skeleton).
- **Kickoff & requirements** (`docs/KICKOFF.md`) and **build log**
  (`docs/BUILD_LOG.md`) — the process, issues found, and fixes.

### Testing
- 63 tests covering the solver, use cases, the API, edge cases, orientation, and
  the full-support rule — all passing.

## Quick start

```bash
# Docker
docker build -t fitcheck .
docker run -d --name fitcheck -p 8000:8000 fitcheck

# or without Docker
pip install .
python -m fitcheck        # serves on http://0.0.0.0:8000
```

Swagger UI: http://localhost:8000/docs

## 3D frontend

```bash
cd frontend
python3 -m http.server 5500
# open http://localhost:5500
```

The page defaults to calling the API at `http://localhost:8000`.
