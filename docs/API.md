# API Guide

The 3D Container Loading Fitment Check API is a small, self-hosted REST
service. It has two endpoints:

- `POST /check` — the main endpoint: send a container and products, get back
  whether they fit, the remaining space, and the exact placement of every unit.
- `GET /health` — a liveness probe.

There are **no credentials, API keys, or required configuration**. The service
accepts any origin (CORS is open) because it is a local, self-hosted tool.

---

## Table of contents

1. [Running the service](#1-running-the-service)
2. [`POST /check`](#2-post-check)
   - [Request](#request)
   - [Response](#response)
   - [Worked examples](#worked-examples)
3. [`GET /health`](#3-get-health)
4. [Error handling](#4-error-handling)
5. [Client examples](#5-client-examples)
   - [Python](#python)
   - [JavaScript / Node](#javascript--node)
   - [cURL](#curl)
6. [Semantics & guarantees](#6-semantics--guarantees)
7. [Performance](#7-performance)

---

## 1. Running the service

### Docker

```bash
docker build -t fitcheck .
docker run -d --name fitcheck -p 8000:8000 fitcheck
```

### From source

```bash
pip install .
python -m fitcheck          # serves on http://0.0.0.0:8000
# or
uvicorn fitcheck.api:app --host 0.0.0.0 --port 8000
```

Once running:

- API: `http://localhost:8000`
- OpenAPI / Swagger UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

---

## 2. `POST /check`

Checks whether a set of products fits in a single container and reports the
remaining space.

### Request

`Content-Type: application/json`

```jsonc
{
  "box": {
    "length": 1200,        // required, > 0  (any consistent unit)
    "width": 235,          // required, > 0
    "height": 235,         // required, > 0
    "max_weight": 24000    // optional, > 0  (weight limit; see below)
  },
  "products": [            // required, at least 1
    {
      "id": "pallet",      // required, 1..200 chars
      "length": 120,       // required, > 0
      "width": 80,         // required, > 0
      "height": 100,       // required, > 0
      "quantity": 30,      // required, 0..100000
      "weight": 500,       // optional, >= 0 (required if box.max_weight is set)
      "orientation": "any"  // optional: "any" (default) or "fixed"
    }
  ]
}
```

#### Field reference

**`box`**

| Field | Type | Required | Constraints | Notes |
|---|---|---|---|---|
| `length` | number | yes | `> 0` | Container length |
| `width` | number | yes | `> 0` | Container width |
| `height` | number | yes | `> 0` | Container height |
| `max_weight` | number | no | `> 0` | Optional weight limit. If set, **every** product must have a `weight` (else 422). |

**`products[]`**

| Field | Type | Required | Constraints | Notes |
|---|---|---|---|---|
| `id` | string | yes | 1–200 chars | Identifies the product; echoed back in `placements`. |
| `length` | number | yes | `> 0` | Product length |
| `width` | number | yes | `> 0` | Product width |
| `height` | number | yes | `> 0` | Product height |
| `quantity` | int | yes | 0–100000 | How many identical units. `0` is allowed (a no-op product). |
| `weight` | number | no | `>= 0` | Per-unit weight. Required for every product if `box.max_weight` is set. |
| `orientation` | string | no | `"any"` \| `"fixed"` | Default `"any"`. `"any"` = may rotate freely (all 6 orientations). `"fixed"` = must stay upright (only the base length/width may swap). |

**Units** are arbitrary (mm, cm, inches…) as long as they are consistent
across the box and all products.

### Response

`200 OK` — `application/json`

```jsonc
{
  "fits": true,                 // true only if ALL units placed AND weight ok
  "units_total": 30,           // total units requested (sum of quantities)
  "units_placed": 30,          // units actually placed
  "box_volume": 66270000,      // length * width * height
  "used_volume": 28800000,     // sum of placed unit volumes
  "remaining_volume": 37470000, // box_volume - used_volume
  "remaining_volume_pct": 56.54, // 100 * remaining / box_volume
  "used_volume_pct": 43.46,    // 100 * used / box_volume
  "total_weight": 15000,       // sum of placed unit weights
  "max_weight": 24000,         // echoed from the request (null if not set)
  "weight_ok": true,           // total_weight <= max_weight (true if no limit)
  "placements": [              // one entry per placed unit
    {
      "product_id": "pallet",
      "unit": 1,
      "x": 0,                 // corner at the container origin
      "y": 0,
      "z": 0,
      "dx": 120,             // placed (possibly rotated) dimensions
      "dy": 80,
      "dz": 100
    }
    // ... one per unit
  ],
  "first_unplaced": null       // null if all fit; else { "product_id", "unit" }
}
```

#### Response field reference

| Field | Type | Meaning |
|---|---|---|
| `fits` | bool | `true` only if **all** units are placed **and** the weight limit (if set) is respected. |
| `units_total` | int | Total units requested (sum of all `quantity`). |
| `units_placed` | int | Units actually placed. Equals `units_total` when `fits` is true. |
| `box_volume` | number | `length * width * height`. |
| `used_volume` | number | Sum of the placed units' volumes. |
| `remaining_volume` | number | `box_volume - used_volume` (the space left). |
| `remaining_volume_pct` | number | `100 * remaining_volume / box_volume`. |
| `used_volume_pct` | number | `100 * used_volume / box_volume`. |
| `total_weight` | number | Sum of the placed units' weights. |
| `max_weight` | number \| null | Echoed from the request. |
| `weight_ok` | bool | `total_weight <= max_weight` (always true if no limit). |
| `placements[]` | array | Exact placement of every placed unit (see below). |
| `first_unplaced` | object \| null | The first unit that could not be placed: `{ "product_id", "unit" }`. `null` when everything fits. |

**`placements[]` entries**

| Field | Type | Meaning |
|---|---|---|
| `product_id` | string | The product's `id`. |
| `unit` | int | 1-based index of the unit within that product. |
| `x`, `y`, `z` | number | The corner of the unit at the container origin. |
| `dx`, `dy`, `dz` | number | The placed (possibly rotated) dimensions. |

`placements` is usable directly as loading instructions: a unit occupies the
AABB from `(x, y, z)` to `(x+dx, y+dy, z+dz)`.

### Worked examples

#### Example 1 — Pallets in a 40 ft container (fits)

```bash
curl -s http://localhost:8000/check \
  -H 'Content-Type: application/json' \
  -d '{
    "box": { "length": 1200, "width": 235, "height": 235 },
    "products": [
      { "id": "pallet", "length": 120, "width": 80, "height": 100, "quantity": 30 }
    ]
  }'
```

```json
{
  "fits": true,
  "units_total": 30,
  "units_placed": 30,
  "box_volume": 66270000,
  "used_volume": 28800000,
  "remaining_volume": 37470000,
  "remaining_volume_pct": 56.54,
  "used_volume_pct": 43.46,
  "total_weight": 0,
  "max_weight": null,
  "weight_ok": true,
  "placements": [ { "product_id": "pallet", "unit": 1, "x": 0, "y": 0, "z": 0, "dx": 120, "dy": 80, "dz": 100 } ],
  "first_unplaced": null
}
```

#### Example 2 — Over capacity (does not fit)

50 pallets in the same container (only 40 physically fit):

```json
{
  "fits": false,
  "units_total": 50,
  "units_placed": 40,
  "remaining_volume_pct": 42.1,
  "first_unplaced": { "product_id": "pallet", "unit": 41 }
}
```

#### Example 3 — Weight limit exceeded

```bash
curl -s http://localhost:8000/check \
  -H 'Content-Type: application/json' \
  -d '{
    "box": { "length": 1200, "width": 235, "height": 235, "max_weight": 15000 },
    "products": [
      { "id": "pallet", "length": 120, "width": 80, "height": 100, "quantity": 40, "weight": 500 }
    ]
  }'
```

```json
{
  "fits": false,
  "units_placed": 40,
  "total_weight": 20000,
  "max_weight": 15000,
  "weight_ok": false
}
```

All 40 pallets fit geometrically, but 20,000 kg exceeds the 15,000 kg limit,
so `fits` is `false` with `weight_ok: false`.

#### Example 4 — Fixed orientation

A tall product (10×10×40) in a short container (height 30). It only fits if
tilted, so `fixed` rejects it while `any` accepts it:

```jsonc
// orientation: "any"   -> { "fits": true }
// orientation: "fixed" -> { "fits": false, "units_placed": 0 }
```

---

## 3. `GET /health`

```bash
curl -s http://localhost:8000/health
```

```json
{ "status": "ok" }
```

Suitable for container liveness/readiness probes.

---

## 4. Error handling

Errors are returned as JSON with an HTTP status code and a `detail` string.

| Status | When |
|---|---|
| `422` | Request failed validation: a non-positive dimension, a negative quantity, an empty `products` list, an invalid `orientation`, or `box.max_weight` set while a product has no `weight`. |
| `500` | An unexpected server error. |

Example `422` (negative dimension):

```json
{ "detail": [ { "loc": ["body", "box", "length"], "msg": "Input should be greater than 0", "type": "greater_than" } ] }
```

Example `422` (missing weight with a weight limit):

```json
{ "detail": "box.max_weight is set but product 'pallet' has no weight; add a weight to every product" }
```

Always check the response status before parsing the body.

---

## 5. Client examples

### Python

```python
import requests

API = "http://localhost:8000"

def check_fits(box, products):
    resp = requests.post(f"{API}/check", json={"box": box, "products": products}, timeout=30)
    resp.raise_for_status()
    return resp.json()

result = check_fits(
    box={"length": 1200, "width": 235, "height": 235},
    products=[
        {"id": "pallet", "length": 120, "width": 80, "height": 100, "quantity": 30},
        {"id": "parcel", "length": 60, "width": 40, "height": 40, "quantity": 10},
    ],
)

if result["fits"]:
    print(f"Fits. {result['remaining_volume_pct']:.1f}% space left.")
else:
    print(f"Does not fit. Stopped at {result['first_unplaced']}.")

# Loading instructions:
for p in result["placements"]:
    print(f"{p['product_id']} #{p['unit']}: ({p['x']},{p['y']},{p['z']}) "
          f"size {p['dx']}x{p['dy']}x{p['dz']}")
```

### JavaScript / Node

```javascript
const API = "http://localhost:8000";

async function checkFits(box, products) {
  const resp = await fetch(`${API}/check`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ box, products }),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

const result = await checkFits(
  { length: 1200, width: 235, height: 235 },
  [
    { id: "pallet", length: 120, width: 80, height: 100, quantity: 30 },
    { id: "parcel", length: 60, width: 40, height: 40, quantity: 10 },
  ],
);

console.log(result.fits, `${result.remaining_volume_pct.toFixed(1)}% left`);
```

### cURL

See the [worked examples](#worked-examples) above.

---

## 6. Semantics & guarantees

- **`fits: true` is reliable.** When the API reports a fit, the `placements`
  are a valid, non-overlapping arrangement that respects the weight limit and
  the full-support rule. You can use them directly.
- **`fits: false` is a heuristic result, not a proof.** It means *this*
  heuristic did not find an arrangement; it is not a mathematical proof that
  none exists. (The check is deterministic, so the same request always gives
  the same answer.)
- **`remaining_volume` / `remaining_volume_pct` are exact** volume arithmetic
  (`box_volume - used_volume`). They tell you how much space is left, not
  whether the leftover is one contiguous block (the leftover is fragmented).
- **When the load does not fit**, `used_volume` reflects only the units that
  *were* placed. The total volume you requested may be larger than
  `used_volume` — the difference is waste (remnants, gaps, alignment loss).
- **Full-support rule (always on):** every unit's entire bottom face rests on
  solid support (the floor, or placed boxes whose combined top surface fully
  covers the base). No ledges or floating boxes.
- **Orientation:** `"any"` tries all 6 axis-aligned rotations; `"fixed"` keeps
  the unit upright (only the base length/width may swap).

---

## 7. Performance

- **Typical loads** (a few dozen to a few hundred units) resolve in well under
  a second.
- **Large, dense loads** (thousands of identical units) are a pathological
  worst case for the extreme-points heuristic and can take on the order of
  10–20 seconds. If you regularly pack very large unit counts, consider
  batching or pre-aggregating identical products.
- The service is stateless; each request is independent and the solver is
  deterministic.
