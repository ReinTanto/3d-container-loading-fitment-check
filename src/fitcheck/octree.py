"""Fast 3D occupancy structure for the fitment-check solver.

The naive solver checks, for every candidate position, whether the unit's
AABB overlaps any of the already-placed boxes — O(n) per candidate, O(n^2)
per unit, O(n^3) overall. That is unusable for thousands of units.

This module replaces the flat list with a 3D interval tree (octree-style)
that answers two queries in ~O(log n):

  * ``overlaps(x, y, z, dx, dy, dz)`` -> bool
  * ``top_z(x, y, dx, dy)`` -> the highest placed box top whose footprint
    overlaps the given 2D region (used to generate candidate z-levels).

The structure is a simple recursive octree: each node owns an axis-aligned
cell; boxes are stored in the deepest node they fit. Queries descend only
into nodes whose cell intersects the query region. For the sizes involved
(a few thousand boxes) this is fast and deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class _Box:
    x: float
    y: float
    z: float
    dx: float
    dy: float
    dz: float


class Octree:
    """A 3D interval tree over a known bounding volume."""

    def __init__(self, max_x: float, max_y: float, max_z: float, depth: int = 8):
        self._root = _Node(0.0, 0.0, 0.0, max_x, max_y, max_z, depth)

    def add(self, x: float, y: float, z: float,
            dx: float, dy: float, dz: float) -> None:
        self._root.insert(_Box(x, y, z, dx, dy, dz))

    def overlaps(self, x: float, y: float, z: float,
                 dx: float, dy: float, dz: float, eps: float) -> bool:
        return self._root.overlaps(x, y, z, dx, dy, dz, eps)

    def top_z(self, x: float, y: float, dx: float, dy: float,
              eps: float) -> float:
        return self._root.top_z(x, y, dx, dy, eps)

    def __len__(self) -> int:
        return self._root.count


class _Node:
    __slots__ = ("x0", "y0", "z0", "x1", "y1", "z1", "depth",
                 "children", "boxes", "count")

    def __init__(self, x0: float, y0: float, z0: float,
                 x1: float, y1: float, z1: float, depth: int):
        self.x0, self.y0, self.z0 = x0, y0, z0
        self.x1, self.y1, self.z1 = x1, y1, z1
        self.depth = depth
        self.children: list[_Node] | None = None
        self.boxes: list[_Box] = []
        self.count = 0

    # -- insertion -------------------------------------------------------

    def insert(self, b: _Box) -> None:
        # If this is a leaf (or the box spans the whole cell), store here.
        if self.children is None and self.depth > 0:
            # Subdivide if the box fits entirely in one child.
            child = self._child_for(b)
            if child is not None:
                if self.children is None:
                    self._subdivide()
                self.children[child].insert(b)
                self.count += 1
                return
        self.boxes.append(b)
        self.count += 1

    def _subdivide(self) -> None:
        mx = (self.x0 + self.x1) / 2
        my = (self.y0 + self.y1) / 2
        mz = (self.z0 + self.z1) / 2
        self.children = [
            _Node(self.x0, self.y0, self.z0, mx, my, mz, self.depth - 1),
            _Node(mx, self.y0, self.z0, self.x1, my, mz, self.depth - 1),
            _Node(self.x0, my, self.z0, mx, self.y1, mz, self.depth - 1),
            _Node(mx, my, self.z0, self.x1, self.y1, mz, self.depth - 1),
            _Node(self.x0, self.y0, mz, mx, my, self.z1, self.depth - 1),
            _Node(mx, self.y0, mz, self.x1, my, self.z1, self.depth - 1),
            _Node(self.x0, my, mz, mx, self.y1, self.z1, self.depth - 1),
            _Node(mx, my, mz, self.x1, self.y1, self.z1, self.depth - 1),
        ]

    def _child_for(self, b: _Box) -> int | None:
        """Return the child index the box fits entirely in, or None."""
        for i, c in enumerate(self._children_coords()):
            cx0, cy0, cz0, cx1, cy1, cz1 = c
            if (b.x >= cx0 and b.y >= cy0 and b.z >= cz0
                    and b.x + b.dx <= cx1 and b.y + b.dy <= cy1
                    and b.z + b.dz <= cz1):
                return i
        return None

    def _children_coords(self) -> list[tuple[float, float, float, float, float, float]]:
        if self.children is None:
            mx = (self.x0 + self.x1) / 2
            my = (self.y0 + self.y1) / 2
            mz = (self.z0 + self.z1) / 2
            return [
                (self.x0, self.y0, self.z0, mx, my, mz),
                (mx, self.y0, self.z0, self.x1, my, mz),
                (self.x0, my, self.z0, mx, self.y1, mz),
                (mx, my, self.z0, self.x1, self.y1, mz),
                (self.x0, self.y0, mz, mx, my, self.z1),
                (mx, self.y0, mz, self.x1, my, self.z1),
                (self.x0, my, mz, mx, self.y1, self.z1),
                (mx, my, mz, self.x1, self.y1, self.z1),
            ]
        return [
            (c.x0, c.y0, c.z0, c.x1, c.y1, c.z1) for c in self.children
        ]

    # -- queries ---------------------------------------------------------

    def _intersects(self, x: float, y: float, z: float,
                    dx: float, dy: float, dz: float, eps: float) -> bool:
        """Does the query AABB intersect this node's cell?"""
        return not (
            x + dx <= self.x0 + eps
            or self.x1 <= x + eps
            or y + dy <= self.y0 + eps
            or self.y1 <= y + eps
            or z + dz <= self.z0 + eps
            or self.z1 <= z + eps
        )

    def overlaps(self, x: float, y: float, z: float,
                 dx: float, dy: float, dz: float, eps: float) -> bool:
        if not self._intersects(x, y, z, dx, dy, dz, eps):
            return False
        for b in self.boxes:
            if self._box_overlaps(b, x, y, z, dx, dy, dz, eps):
                return True
        if self.children:
            for c in self.children:
                if c.overlaps(x, y, z, dx, dy, dz, eps):
                    return True
        return False

    @staticmethod
    def _box_overlaps(b: _Box, x: float, y: float, z: float,
                      dx: float, dy: float, dz: float, eps: float) -> bool:
        return not (
            x + dx <= b.x + eps
            or b.x + b.dx <= x + eps
            or y + dy <= b.y + eps
            or b.y + b.dy <= y + eps
            or z + dz <= b.z + eps
            or b.z + b.dz <= z + eps
        )

    def top_z(self, x: float, y: float, dx: float, dy: float,
             eps: float) -> float:
        """Highest placed-box top whose footprint overlaps the 2D region."""
        best = 0.0
        if not self._intersects_2d(x, y, dx, dy, eps):
            return 0.0
        for b in self.boxes:
            if self._footprint_overlaps(b, x, y, dx, dy, eps):
                top = b.z + b.dz
                if top > best:
                    best = top
        if self.children:
            for c in self.children:
                t = c.top_z(x, y, dx, dy, eps)
                if t > best:
                    best = t
        return best

    def _intersects_2d(self, x: float, y: float,
                       dx: float, dy: float, eps: float) -> bool:
        return not (
            x + dx <= self.x0 + eps
            or self.x1 <= x + eps
            or y + dy <= self.y0 + eps
            or self.y1 <= y + eps
        )

    @staticmethod
    def _footprint_overlaps(b: _Box, x: float, y: float,
                           dx: float, dy: float, eps: float) -> bool:
        return not (
            x + dx <= b.x + eps
            or b.x + b.dx <= x + eps
            or y + dy <= b.y + eps
            or b.y + b.dy <= y + eps
        )
