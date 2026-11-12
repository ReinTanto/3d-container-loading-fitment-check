"""Core 3D bin-packing feasibility solver.

Algorithm: extreme-points constructive heuristic, accelerated with a 3D
interval tree (octree) for fast overlap and "top of supporting boxes"
queries (see ``octree.py``).

1. Expand product quantities into individual units.
2. Sort units by volume, largest first (ties broken by product id, then
   unit index, so the result is deterministic).
3. For each unit, try all 6 axis-aligned rotations. For each rotation,
   look for the lowest valid position among "extreme points" — candidate
   positions derived from the corners of already-placed boxes. A position
   is valid when the unit's AABB does not overlap any already-placed box
   and stays inside the container.
4. A unit that does not fit now may fit after later (smaller) units are
   placed, so placement is done in bounded multi-pass: stop a pass at the
   first failure, and only retry if a later unit was placed (which is what
   changes the arrangement).
5. All units placed -> fits; otherwise the first unit that could not be
   placed is reported.

Honesty caveat: a "fits" answer is reliable (a valid placement is
returned). A "does not fit" answer means this heuristic did not find an
arrangement; it is not a proof that none exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import permutations

from .octree import Octree


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

    # Rotation order per distinct size: canonical orientation first, then the
    # other permutations in fixed order. Deterministic.
    rotation_order: dict[tuple[float, float, float], list[tuple[float, float, float]]] = {}
    for (pid, idx, l, w, h, _) in units:
        if (l, w, h) not in rotation_order:
            rotation_order[(l, w, h)] = _rotations(l, w, h)

    box_volume = box.length * box.width * box.height
    # Epsilon scales with the input magnitude: a fixed 1e-9 breaks when the
    # caller uses large units (e.g. millimetres), because float64 spacing at
    # 1e6 is ~1e-10 — "0.0 + 1e-9" is not 0.0, so the floor corner is
    # rejected and stacking silently fails.
    scale = max(box.length, box.width, box.height, 1.0)
    eps = max(1e-9, scale * 1e-9)

    # Occupancy structure for fast overlap / top-z queries.
    tree = Octree(box.length, box.width, box.height)
    # Flat list of placed boxes, for generating candidate x/y coordinates.
    placed: list[tuple[float, float, float, float, float, float]] = []
    placements: list[Placement] = []
    total_weight = 0.0
    first_unplaced: tuple[str, int] | None = None

    for (pid, idx, l, w, h, weight) in units:
        total_weight += weight or 0.0

    def try_place(
        l: float, w: float, h: float,
        xs: list[float],
        ys: list[float],
    ) -> tuple[float, float, float, float, float, float] | None:
        """Find the lowest valid spot for one unit, or None."""
        rots = rotation_order[(l, w, h)]
        # Short-circuit: if no rotation fits the box's dimensions, the unit
        # can never be placed — return immediately.
        if not any(
            dx <= box.length + eps and dy <= box.width + eps and dz <= box.height + eps
            for (dx, dy, dz) in rots
        ):
            return None
        for (dx, dy, dz) in rots:
            if dx > box.length + eps or dy > box.width + eps or dz > box.height + eps:
                continue
            for x in xs:
                if x + dx > box.length + eps:
                    continue
                for y in ys:
                    if y + dy > box.width + eps:
                        continue
                    # Candidate z: 0 plus the top of the highest placed box
                    # whose footprint overlaps this unit's footprint in 2D.
                    # (Overlap, not containment: a unit may rest on a box it
                    # only partially overflows — e.g. pallets in a row.)
                    zs = [0.0, tree.top_z(x, y, dx, dy, eps)]
                    for z in sorted(zs):
                        if z + dz > box.height + eps:
                            continue
                        if not tree.overlaps(x, y, z, dx, dy, dz, eps):
                            return (x, y, z, dx, dy, dz)
        return None

    # 3. Bounded multi-pass placement.
    #
    # A single pass is order-dependent: a unit that does not fit now may fit
    # after later (smaller) units are placed. So we walk `pending` in order,
    # stop a pass at the first failure, and only retry if a later unit was
    # placed (which is the only thing that changes the arrangement). This
    # keeps an over-capacity load (many fitting + some not) at O(n^2)
    # instead of re-attempting the same failing unit on every pass.
    pending: list[tuple[str, int, float, float, float]] = [
        (pid, idx, l, w, h) for (pid, idx, l, w, h, _) in units
    ]

    while pending:
        xs = sorted({0.0} | {b[0] for b in placed} | {b[0] + b[3] for b in placed})
        ys = sorted({0.0} | {b[1] for b in placed} | {b[1] + b[4] for b in placed})
        placed_this_pass = 0
        fail_index: int | None = None
        for i, (pid, idx, l, w, h) in enumerate(pending):
            spot = try_place(l, w, h, xs, ys)
            if spot is None:
                fail_index = i
                if first_unplaced is None:
                    first_unplaced = (pid, idx)
                break
            placed.append(spot)
            tree.add(spot[0], spot[1], spot[2], spot[3], spot[4], spot[5])
            placements.append(
                Placement(pid, idx, spot[0], spot[1], spot[2], spot[3], spot[4], spot[5])
            )
            placed_this_pass += 1
            if first_unplaced is not None and (pid, idx) == first_unplaced:
                first_unplaced = None
        if fail_index is None:
            break  # everything placed
        if placed_this_pass == 0:
            break  # nothing changed; no further pass can help
        # Resume from the failed unit; drop the already-placed prefix.
        pending = pending[fail_index:]

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
