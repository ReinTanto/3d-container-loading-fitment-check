# Kickoff & Requirements Document

**Project:** 3d-container-loading-fitment-check
**Date:** 2026-11-12
**Status:** Approved for development

## 1. Background

We need a self-hosted API to check whether a set of products fits inside a
container (truck box, shipping container, cargo space). The API takes the
available space dimensions and the product dimensions (with quantities), and
answers:

1. Does the load fit? (boolean)
2. If it fits, how much space is left? (volume and/or percentage)

The use case is **single container, multiple products, multiple dimensions**.
We are *not* trying to split a load across multiple containers, and we are
*not* trying to find the smallest container that fits — the container is given.

### Why not an existing open-source project?

| Project | Reason rejected |
|---|---|
| Binacle.Net | Built for "which of my boxes is smallest"; heuristic, integer-only, no weight support |
| sardine-can | 2014 master-thesis project, barely maintained, optional solver parts need commercial Gurobi/CPLEX licenses |
| wutesta0101-hue/container-packing | Container types are preset (20/40 ft), forklift-specific, full React+Postgres app — heavy to run just for one check |
| skjolber/3d-bin-container-packing | Solid library (Apache-2.0) but Java; would need wrapping in an HTTP service anyway |

Conclusion: the spec is a well-understood single-container 3D bin-packing
feasibility check. The core solver is small (~200–300 lines), so building our
own is the cleanest path.

## 2. Requirements (as requested)

### Functional

- **R1.** `POST` endpoint that accepts:
  - the container/box dimensions (length, width, height), and
  - a list of products, each with dimensions and a quantity.
- **R2.** Returns a **boolean** indicating whether the products fit.
- **R3.** Returns the **remaining space** as a **volume** and a **percentage**
  (when the load fits).
- **R4.** Supports **multiple products with different dimensions** loaded into
  **one** container.
- **R5.** Supports **quantity** per product (e.g. 40 units of the same box).
- **R6.** Self-hostable: runs in Docker, no external dependencies beyond the
  runtime, no credentials or API keys required.

### Non-functional

- **N1.** Deterministic: the same request always gives the same answer.
- **N2.** Fast: a typical request (≤ a few thousand units) resolves in
  milliseconds to low seconds.
- **N3.** No credentials, API keys, or network calls. All computation is local.
- **N4.** Documented API (OpenAPI/Swagger) and documented build process.

### Design decisions (agreed at kickoff)

- **Stack:** Python 3.12 + FastAPI + Pydantic (served by uvicorn).
- **Solver:** "extreme points" constructive heuristic:
  1. Expand quantities into individual units.
  2. Sort units by volume, largest first.
  3. For each unit, try all 6 axis-aligned rotations; place at the lowest
     valid candidate position (extreme points = corners of already-placed
     boxes, projected onto the floor and on top of other boxes).
  4. All units placed → `fits: true`; otherwise `fits: false`.
- **Remaining space** is exact volume arithmetic:
  `remaining = box_volume − Σ unit_volumes`. The percentage is
  `remaining / box_volume`. Note: the *shape* of the remaining space is
  fragmented; the number tells how much is left, not whether it is one block.
- **Honesty caveat (documented in the API):** a `fits: true` answer is
  reliable (a valid placement is returned). A `fits: false` answer means the
  heuristic did not find an arrangement — it is not a mathematical proof that
  none exists.
- **Weight support (optional):** the box may carry a `max_weight`; products
  may carry a `weight`. If given, the total weight must also fit.

## 3. API contract (v1)

### `POST /check`

Request:
```json
{
  "box": {
    "length": 1200,
    "width": 250,
    "height": 300,
    "max_weight": 24000
  },
  "products": [
    { "id": "a", "length": 100, "width": 80, "height": 60, "quantity": 40, "weight": 25 },
    { "id": "b", "length": 60, "width": 40, "height": 40, "quantity": 12, "weight": 10 }
  ]
}
```

Response:
```json
{
  "fits": true,
  "used_volume": 144.0,
  "box_volume": 90000,
  "remaining_volume": 89856.0,
  "remaining_volume_pct": 99.84,
  "used_volume_pct": 0.16,
  "total_weight": 1140,
  "max_weight": 24000,
  "weight_ok": true,
  "units_placed": 52,
  "units_total": 52,
  "placements": [
    { "product_id": "a", "unit": 1, "x": 0, "y": 0, "z": 0,
      "dx": 100, "dy": 80, "dz": 60 }
  ]
}
```

Field notes:
- `fits` is `true` only if **all** units are placed **and** the weight limit
  (if given) is respected.
- `placements` is the exact corner + placed dimensions of every unit, in the
  units of the request. Useful for loading instructions.
- Units are arbitrary (mm, cm, inches…) as long as they are consistent.
- Dimensions are positive numbers (floats allowed; the solver works on the
  given numbers).
- `max_weight` and `weight` are optional. If `max_weight` is given and any
  product lacks a weight, the request is rejected (422) to avoid silent
  under-counting.

### `GET /health`

Returns `{"status": "ok"}`. Suitable for container probes.

### `GET /`

OpenAPI documentation (Swagger UI).

## 4. Out of scope (v1)

- Splitting a load across multiple containers.
- Finding the smallest container that fits.
- Irregular (non-rectangular) shapes.
- Optimization objectives (minimize trucks, maximize revenue, axle load).
- Unloading order / LIFO constraints.
- Persistence, authentication, multi-tenancy.

## 5. Test plan

- **Unit tests** for the solver:
  - exact fit (volume fills the box exactly),
  - trivially fits (small boxes, large container),
  - trivially does not fit (one unit taller than the box),
  - rotation-dependent fit (a unit only fits rotated),
  - quantity expansion,
  - weight limit rejection,
  - deterministic output.
- **Use-case tests** (realistic scenarios):
  - EU pallets (120×80×~100 cm) in a 40 ft container (1200×235×235 cm),
  - mixed parcel sizes in a 2.5 m truck box,
  - a load that fits only with rotation,
  - an over-capacity load (must return `fits: false`),
  - weight-limited load.
- **API tests** (FastAPI TestClient): request validation (422 cases),
  response shape, `GET /health`.

## 6. Definition of done

- [ ] `POST /check` implements R1–R5, N1–N3.
- [ ] Docker image builds and runs; `GET /health` works.
- [ ] Unit + use-case + API test suites pass.
- [ ] OpenAPI docs served at `/`.
- [ ] README with quick start (curl + Docker).
- [ ] `docs/BUILD_LOG.md` documents the build process, issues found, and fixes.
- [ ] Repo is public; no credentials or tokens in the repo.
