"""Core 3D bin-packing feasibility solver.

Algorithm: extreme-points constructive heuristic.

1. Expand product quantities into individual units.
2. Sort units by volume, largest first (ties broken by product id, then
   unit index, so the result is deterministic).
3. For each unit, try all 6 axis-aligned rotations. For each rotation,
   look for the lowest valid position among "extreme points" — candidate
   positions derived from the corners of already-placed boxes (a box
   corner projected onto the floor, and onto the top of other boxes).
   A position is valid when the unit's AABB does not overlap any
   already-placed box and stays inside the container.
4. All units placed -> fits; otherwise the first unit that could not be
   placed is reported.

Honesty caveat: a "fits" answer is reliable (a valid placement is
returned). A "does not fit" answer means this heuristic did not find an
arrangement; it is not a proof that none exists.

Complexity is O(n^2 * 6 * candidates) in the worst case, which is fine
for a few thousand units.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import permutations


@dataclass(frozen=True)
class Box:
    """The container. Dimensions in the caller's units."""

    length: float
    width: float
    height: float
    max_weight: float | None = None


@dataclass(frozen=True)
class Product:
    """A product type. Quantity is expanded into individual units."""

    id: str
    length: float
    width: float
    height: float
    quantity: int
    weight: float | None = None


@dataclass
class Placement:
    """Where one unit sits. (x, y, z) is the corner at the container
    origin; (dx, dy, dz) are the placed (possibly rotated) dimensions."""

    product_id: str
    unit: int
    x: float
    y: float
    z: float
    dx: float
    dy: float
    dz: float

    def volume(self) -> float:
        return self.dx * self.dy * self.dz


@dataclass
class CheckResult:
    fits: bool
    units_total: int
    units_placed: int
    box_volume: float
    used_volume: float
    remaining_volume: float
    remaining_volume_pct: float
    used_volume_pct: float
    total_weight: float
    max_weight: float | None
    weight_ok: bool
    placements: list[Placement] = field(default_factory=list)
    first_unplaced: tuple[str, int] | None = None


def _rotations(l: float, w: float, h: float) -> list[tuple[float, float, float]]:
    """All 6 distinct axis-aligned orientations of a box."""
    return list(dict.fromkeys(permutations((l, w, h))))


def _overlaps(
    x: float, y: float, z: float, dx: float, dy: float, dz: float,
    placed: list[tuple[float, float, float, float, float, float]],
    eps: float,
) -> bool:
    """AABB overlap test against all placed boxes."""
    for (px, py, pz, pdx, pdy, pdz) in placed:
        if (
            x + dx <= px + eps
            or px + pdx <= x + eps
            or y + dy <= py + eps
            or py + pdy <= y + eps
            or z + dz <= pz + eps
            or pz + pdz <= z + eps
        ):
            continue  # separated on at least one axis
        return True
    return False


def check(box: Box, products: list[Product]) -> CheckResult:
    """Run the fitment check. Deterministic."""
    if box.length <= 0 or box.width <= 0 or box.height <= 0:
        raise ValueError("box dimensions must be positive")
    for p in products:
        if p.quantity < 0:
            raise ValueError(f"product {p.id!r}: quantity must be >= 0")
        if p.length <= 0 or p.width <= 0 or p.height <= 0:
            raise ValueError(f"product {p.id!r}: dimensions must be positive")

    # 1. Expand quantities into units (deterministic order).
    units: list[tuple[str, int, float, float, float, float | None]] = []
    for p in products:
        for i in range(1, p.quantity + 1):
            units.append((p.id, i, p.length, p.width, p.height, p.weight))

    # 2. Largest volume first; deterministic tie-break.
    units.sort(key=lambda u: (-(u[2] * u[3] * u[4]), u[0], u[1]))

    # Rotation order per unit: canonical orientation first, then the other
    # 5 permutations in fixed order. Deterministic.
    rotation_order: dict[tuple[float, float, float], list[tuple[float, float, float]]] = {}
    for (pid, idx, l, w, h, _) in units:
        rotation_order[(l, w, h)] = _rotations(l, w, h)

    box_volume = box.length * box.width * box.height
    # Epsilon scales with the input magnitude: a fixed 1e-9 breaks when the
    # caller uses large units (e.g. millimetres), because float64 spacing at
    # 1e6 is ~1e-10 — "0.0 + 1e-9" is not 0.0, so the floor corner is
    # rejected and stacking silently fails.
    scale = max(box.length, box.width, box.height, 1.0)
    eps = max(1e-9, scale * 1e-9)

    def try_place(
        l: float, w: float, h: float,
        placed: list[tuple[float, float, float, float, float, float]],
    ) -> tuple[float, float, float, float, float, float] | None:
        """Find the best (lowest) spot for one unit, or None."""
        for (dx, dy, dz) in rotation_order[(l, w, h)]:
            if dx > box.length + eps or dy > box.width + eps or dz > box.height + eps:
                continue
            xs = sorted({0.0} | {b[0] for b in placed} | {b[0] + b[3] for b in placed})
            ys = sorted({0.0} | {b[1] for b in placed} | {b[1] + b[4] for b in placed})
            for x in xs:
                if x + dx > box.length + eps:
                    continue
                for y in ys:
                    if y + dy > box.width + eps:
                        continue
                    # Candidate z: 0 plus the top of every placed box whose
                    # footprint *overlaps* the new unit's footprint in 2D.
                    # (Overlap, not containment: a unit may rest on a box it
                    # only partially overflows — e.g. pallets in a row.)
                    zs = {0.0}
                    for (px, py, pz, pdx, pdy, pdz) in placed:
                        if (
                            x + dx > px + eps
                            and px + pdx > x + eps
                            and y + dy > py + eps
                            and py + pdy > y + eps
                        ):
                            zs.add(pz + pdz)
                    for z in sorted(zs):
                        if z + dz > box.height + eps:
                            continue
                        if not _overlaps(x, y, z, dx, dy, dz, placed, eps):
                            return (x, y, z, dx, dy, dz)
        return None

    # 3. Greedy placement at extreme points, in multiple passes.
    #
    # A single pass is order-dependent: a unit that does not fit now may fit
    # after later (smaller) units are placed. So we make a first pass in
    # largest-first order, collect the units that could not be placed, and
    # then retry them in further passes until no progress is made.
    placed: list[tuple[float, float, float, float, float, float]] = []
    placements: list[Placement] = []
    total_weight = 0.0
    first_unplaced: tuple[str, int] | None = None

    pending = list(units)
    for (pid, idx, l, w, h, weight) in units:
        total_weight += weight or 0.0

    while pending:
        progress = False
        still_pending = []
        for (pid, idx, l, w, h, _) in pending:
            spot = try_place(l, w, h, placed)
            if spot is None:
                still_pending.append((pid, idx, l, w, h, None))
                if first_unplaced is None:
                    first_unplaced = (pid, idx)
                continue
            placed.append(spot)
            placements.append(
                Placement(pid, idx, spot[0], spot[1], spot[2], spot[3], spot[4], spot[5])
            )
            progress = True
        if not progress:
            break
        pending = still_pending

    used_volume = sum(pl.volume() for pl in placements)
    remaining = max(0.0, box_volume - used_volume)
    weight_ok = True
    if box.max_weight is not None:
        weight_ok = total_weight <= box.max_weight + eps

    fits = first_unplaced is None and weight_ok

    return CheckResult(
        fits=fits,
        units_total=len(units),
        units_placed=len(placements),
        box_volume=box_volume,
        used_volume=used_volume,
        remaining_volume=remaining,
        remaining_volume_pct=100.0 * remaining / box_volume if box_volume else 0.0,
        used_volume_pct=100.0 * used_volume / box_volume if box_volume else 0.0,
        total_weight=total_weight,
        max_weight=box.max_weight,
        weight_ok=weight_ok,
        placements=placements,
        first_unplaced=first_unplaced,
    )
