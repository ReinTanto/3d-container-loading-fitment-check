# Build Log

This document records the process of building the 3D container loading
fitment-check service: what was done, the issues that came up, and how
each was fixed.

## 1. Process overview

1. **Requirements first.** A kickoff/requirements document
   ([KICKOFF.md](KICKOFF.md)) was written before any code, capturing every
   requested feature (R1–R6, N1–N4) and the agreed design decisions.
2. **Scaffold.** Python 3.12 + FastAPI + Pydantic, `src/` layout,
   `pyproject.toml`, Dockerfile.
3. **Solver.** Extreme-points constructive heuristic in
   `src/fitcheck/solver.py`.
4. **API layer.** `src/fitcheck/api.py` with Pydantic validation.
5. **Tests.** Three suites: solver unit tests, realistic use-case tests,
   and API tests (FastAPI TestClient).
6. **Verify.** Full pytest run + live server exercised with curl +
   Docker image build.

## 2. Issues found and fixes

### Issue 1 — Fixed epsilon broke with large units (silent stacking failure)

**Symptom.** The 40 ft container use case (dimensions ~1200) failed: only
2 of 3 height layers were built. A 100×100×100 box with 50×50×50 units
also misbehaved.

**Root cause.** The overlap test used a fixed `eps = 1e-9`. With float64,
the spacing at magnitude 1e3–1e6 is ~1e-13–1e-10, so `0.0 + 1e-9` is *not*
`0.0`. The floor corner `z = 0.0` was therefore not recognised as "on top
of" a placed box at `z = 0`, and stacking on the floor silently failed.

**Fix.** Scale the epsilon with the input magnitude:
```python
scale = max(box.length, box.width, box.height, 1.0)
eps = max(1e-9, scale * 1e-9)
```

### Issue 2 — z-candidate generation used containment instead of overlap

**Symptom.** Even after the epsilon fix, pallets in a row could not stack
beyond 2 layers. A pallet at x=1080 (footprint 1080–1200) could not rest
on the pallet at x=960 (footprint 960–1080) — their footprints only
*touch*, they don't contain each other.

**Root cause.** The code only added a z-level from a placed box when that
box's footprint **contained** the new unit's footprint. Real stacking
rests on partial overlap (a unit overhanging its support is physically
fine for a feasibility check).

**Fix.** Changed the condition to a 2D **overlap** test:
```python
if (x + dx > px + eps and px + pdx > x + eps
    and y + dy > py + eps and py + pdy > y + eps):
    zs.add(pz + pdz)
```

### Issue 3 — Single-pass greedy is order-dependent

**Symptom.** A unit that doesn't fit *now* may fit after later (smaller)
units are placed. A single largest-first pass can leave placeable units
unplaced.

**Fix.** Multi-pass placement: make a first pass in largest-first order,
collect the units that could not be placed, then retry them in further
passes until no progress is made. This is still a heuristic (not a
completeness proof), but it recovers many cases a single pass misses and
is deterministic.

### Issue 4 — Test expectation errors (my own arithmetic)

Several test expectations were wrong on my side, not the solver's:

- `test_trivially_fits`: 5 × 10³ = 5000, not 500 (box is 100³ = 1,000,000).
- `test_exact_fit`: 8 × 125,000 = 1,000,000 = 100³, not 100,000.
- `test_eu_pallets_in_40ft_container`: I initially computed "58 pallets
  max" from floor area alone, ignoring that the 80 cm width only allows
  **2** rows (2×80=160 ≤ 235, 3×80=240 > 235). The true capacity is
  10 × 2 × 2 = **40**. The solver was correct; the test was fixed to ask
  for 30 (fits) and 50 (doesn't fit, 40 placed).
- `test_weight_limited_load`: adjusted quantities to stay within the
  geometric capacity of 40.

**Lesson.** When a "failure" appears, verify the expected value by
independent calculation before changing the solver. In every case here the
solver was right and the test was wrong.

### Issue 5 — `Product` dataclass required `quantity` positionally

**Symptom.** `test_single_unit_too_big` raised `TypeError: Product.__init__
() missing 1 required positional argument: 'quantity'`.

**Fix.** The test helper `prod()` defaults `qty=1`, but the use-case test
called `Product(...)` directly without `quantity`. Fixed the call to pass
`quantity=1`.

## 3. Verification

- **Unit tests** (`tests/test_solver.py`): trivial fit, exact fit,
  too-tall, over-volume, rotation-dependent fit, stacking, weight limit
  ok/exceeded, determinism, zero quantity, no-overlap invariant, invalid
  dimensions.
- **Use-case tests** (`tests/test_use_cases.py`): EU pallets in a 40 ft
  container (fits / over-capacity), mixed parcels in a 2.5 m truck box,
  weight-limited load (ok / exceeded), single unit too big.
- **API tests** (`tests/test_api.py`): health, fits, does-not-fit,
  weight-rejected, missing-weight 422, negative-dimension 422,
  empty-products 422, OpenAPI served.
- **Live server** exercised with `curl` against all use cases + validation.
- **Edge-case tests** (`tests/test_edge_cases.py`): boundary dimensions,
  float precision, very large/small units, zero/negative dimensions, zero
  quantities, identical-cube grids, rotation-only fits, weight at/over
  limit, determinism, no-overlap and inside-box invariants, and a
  1000-unit performance check.
- **Docker image** builds successfully.

All 53 tests pass.

## 3b. Edge-case testing (second round)

After the initial pass I systematically probed edge cases
(`tests/test_edge_cases.py`): boundary dimensions (exact fit, one-over,
one-under), float precision, very large (mm) and very small units,
zero/negative dimensions, zero quantities, identical-cube grids,
rotation-only fits, weight at/over the limit, determinism, and
no-overlap / inside-box invariants under mixed sizes.

### Issue 6 — O(n^3) performance on large loads

**Symptom.** 1000 units took 17s (and a naive multi-pass retry loop made
it 37s). The naive solver checks, for every candidate position, whether the
unit's AABB overlaps *any* of the already-placed boxes — O(n) per
candidate, O(n²) per unit, O(n³) overall.

**Fix.** Replaced the flat placed-box list with a 3D interval tree
(octree, `src/fitcheck/octree.py`) that answers both queries in ~O(log n):
- `overlaps(x, y, z, dx, dy, dz)` — does the candidate AABB collide?
- `top_z(x, y, dx, dy)` — the highest placed-box top whose footprint
  overlaps the candidate's 2D region (used to generate candidate z-levels).

After the fix: 1000 units in 4.9s, 5000 units in 4.9s (it correctly
reports that only 1000 fit in a 200³ box). The bounded multi-pass loop
(§2, issue 3) is retained: a pass stops at the first failure and only
retries if a later unit was placed, so an over-capacity load stays at
O(n²) instead of re-attempting the same failing unit on every pass.

### Issue 7 — `first_unplaced` was stale across passes

**Symptom.** A unit that failed on pass 1 but was placed on pass 2 still
left `first_unplaced` set, so `fits` was wrongly `false` even though all
units were placed.

**Fix.** Clear `first_unplaced` when the flagged unit is subsequently
placed; only set it for a unit that is still unplaced at the end.

### Test-count note

The edge-case round added 27 tests. Total is now **53 tests, all passing**
(solver 12, use-cases 6, API 8, edge-cases 27).

## 3c. 3D test frontend

A self-contained test frontend (`frontend/index.html`, no build step) was
added so the check can be exercised and the result visualized in
three.js. It was styled after the visualizer in
`skjolber/3d-bin-container-packing` (its `visualizer/viewer` React +
three.js app): dark scene (`#263238`), a transparent grey container shell
with edge outlines, one colour per product for the placed boxes (with
edge outlines), a ground grid + axis arrows, orbit controls with damping,
hover highlight + tooltip, and a camera that auto-fits the container.

- The page lets you enter the container dimensions (and optional max
  weight) and any number of products (name, L/W/H, quantity, optional
  weight), then calls `POST /check` and renders every placement.
- It is a single HTML file using an import map for three.js (no bundler),
  so it can be served with `python3 -m http.server`.
- **Issue found & fixed:** the initial API-URL fallback assumed the page
  was same-origin with the API; when served by a plain static server it
  tried to `POST` to its own port (501). Fixed by defaulting to
  `http://localhost:8000` and only using the page origin when it *is*
  port 8000.
- **Verified** with a headless Chromium (Playwright) run: a fitting load
  (40/40 units, 55% space left) and a non-fitting load (0/40) both render
  correctly, with no console errors.

## 3d. Per-product orientation (fixed vs any)

A per-product `orientation` field was added so a product can be declared
either rotatable or fixed-orientation:

- `"any"` (default) — all 6 axis-aligned rotations are tried.
- `"fixed"` — the unit must stay upright; only the base (length/width)
  swap is allowed. A product that only fits if tilted is rejected.

**Implementation.** `Product.orientation` threads through the solver: the
rotation set is now keyed by `(size, orientation)`, and `_rotations`
returns either all 6 permutations (`any`) or just the base swap
(`fixed`). The API exposes `orientation: "any" | "fixed"` (422 otherwise)
and the frontend has a per-product selector.

**Tests added** (6): fixed forces upright (a tall unit that only fits
tilted is rejected), fixed still allows the base swap, invalid
orientation raises / 422, and API any-vs-fixed. Total is now **60 tests,
all passing**.

**Issue found & fixed (test, not code).** My first "fixed must reject"
test used a unit whose base actually swapped to fit upright, so the
solver (correctly) fit it. Fixed the test to use a unit whose base
cannot fit upright at all.

## 4. Known limitations (by design)

- **Heuristic, not a proof.** `fits: true` is reliable (a valid placement
  is returned). `fits: false` means this heuristic did not find an
  arrangement; it is not a mathematical proof that none exists.
- **Remaining space** is exact volume arithmetic, but the *shape* of the
  remaining space is fragmented — the number tells how much is left, not
  whether it is one usable block.
- **No** multi-container splitting, irregular shapes, unloading order, or
  axle-load constraints (see KICKOFF.md §6).
