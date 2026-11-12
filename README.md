# 3D Container Loading Fitment Check

A self-hosted REST API that answers one question:

> Do these products fit in this container — and if so, how much space is left?

Send the box dimensions and your products (dimensions + quantity). Get back a
boolean and the remaining space as a volume and a percentage. No credentials,
no external services, no network calls — all computation is local.

## Quick start

```bash
docker run -d --name fitcheck -p 8000:8000 <your-image>
```

Or without Docker:

```bash
pip install .
python -m fitcheck   # serves on http://0.0.0.0:8000
```

Swagger UI: http://localhost:8000/docs

## API

### `POST /check`

```bash
curl -s http://localhost:8000/check \
  -H 'Content-Type: application/json' \
  -d '{
    "box": { "length": 1200, "width": 250, "height": 300, "max_weight": 24000 },
    "products": [
      { "id": "pallets", "length": 120, "width": 80, "height": 100, "quantity": 40, "weight": 500 },
      { "id": "parcels", "length": 60, "width": 40, "height": 40, "quantity": 12, "weight": 10 }
    ]
  }'
```

```json
{
  "fits": true,
  "units_total": 52,
  "units_placed": 52,
  "box_volume": 90000000,
  "used_volume": 5856000,
  "remaining_volume": 84144000,
  "remaining_volume_pct": 93.49,
  "used_volume_pct": 6.51,
  "total_weight": 20120,
  "max_weight": 24000,
  "weight_ok": true,
  "placements": [
    { "product_id": "pallets", "unit": 1, "x": 0, "y": 0, "z": 0, "dx": 120, "dy": 80, "dz": 100 }
  ],
  "first_unplaced": null
}
```

- `fits` is `true` only if **all** units are placed **and** the weight limit
  (if given) is respected.
- `placements` gives the exact corner + placed dimensions of every unit —
  usable as loading instructions.
- Units are arbitrary (mm, cm, inches…) as long as they are consistent.
- `max_weight` / `weight` are optional. If `max_weight` is set, every product
  must have a `weight` (otherwise 422).
- `orientation` (per product, optional, default `"any"`):
  - `"any"` — the unit may be rotated freely (all 6 orientations).
  - `"fixed"` — the unit must stay upright; only its base (length/width)
    may swap. A product that only fits if tilted will not fit when fixed.
- **Full-support rule (always on):** every unit's entire bottom face must
  rest on solid support — the floor, or placed boxes whose combined top
  surface fully covers the unit's base. **No ledges / floating boxes**: a
  unit cannot overhang, so it is never placed where part of its base would
  hang in the air.

### `GET /health`

`{"status": "ok"}`

## How it works

Extreme-points constructive heuristic, accelerated with a 3D interval tree
(octree) for fast collision and "top of supporting boxes" queries:

1. Expand quantities into individual units.
2. Sort units by volume, largest first (deterministic tie-break).
3. For each unit, try all 6 axis-aligned rotations and place it at the lowest
   valid "extreme point" (corners of already-placed boxes, on the floor or
   on top of other boxes).
4. A unit that doesn't fit now may fit after later (smaller) units are
   placed, so placement is done in bounded multi-pass.
5. All units placed → `fits: true`; otherwise the first unplaced unit is
   reported in `first_unplaced`.

Remaining space is exact volume arithmetic:
`remaining = box_volume − Σ unit_volumes`.

**Honesty caveat:** a `fits: true` answer is reliable — a valid placement is
returned. A `fits: false` answer means *this* heuristic did not find an
arrangement; it is not a mathematical proof that none exists. (Running the
check is deterministic, so you will always get the same answer for the same
request.)

## 3D test frontend

A self-contained test frontend (no build step) lets you enter the container
size and products (name, dimensions, quantity), run the check, and see the
result rendered in three.js — styled after the visualizer in
[skjolber/3d-bin-container-packing](https://github.com/skjolber/3d-bin-container-packing)
(dark scene, transparent container shell, one colour per product, ground
grid + axes, orbit controls, hover highlight, camera auto-fit).

**Run the API** (if not already running):
```bash
docker run -d --name fitcheck -p 8000:8000 <your-image>
# or: pip install . && python -m fitcheck
```

**Serve the frontend** and open it:
```bash
cd frontend
python3 -m http.server 5500
# open http://localhost:5500
```

The page defaults to calling the API at `http://localhost:8000`. If you
serve the frontend from the API's own origin (port 8000), it uses that
origin automatically. Enter a container, add products, and press
**Calculate & visualize**.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Documentation

- [Kickoff & requirements](docs/KICKOFF.md)
- [Build log — process, issues found, fixes](docs/BUILD_LOG.md)
