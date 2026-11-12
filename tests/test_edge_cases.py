"""Edge-case tests: boundary conditions, degenerate inputs, stress, invariants."""

import time

import pytest

from fitcheck.solver import Box, Product, check


def test_single_unit_exact_fit():
    r = check(Box(10, 10, 10), [Product("a", 10, 10, 10, 1)])
    assert r.fits
    assert r.remaining_volume == 0
    assert r.remaining_volume_pct == 0.0


def test_unit_one_over_size_does_not_fit():
    r = check(Box(10, 10, 10), [Product("a", 10.0001, 10, 10, 1)])
    assert not r.fits
    assert r.units_placed == 0


def test_unit_one_under_size_fits():
    r = check(Box(10, 10, 10), [Product("a", 9.9999, 10, 10, 1)])
    assert r.fits


def test_float_precision_no_false_rejection():
    """Values that are equal within float precision must not be rejected."""
    # 0.1 + 0.2 != 0.3 in float; a unit of 0.3 in a 0.3 box must fit.
    r = check(Box(0.3, 0.3, 0.3), [Product("a", 0.3, 0.3, 0.3, 1)])
    assert r.fits


def test_very_large_dimensions_mm():
    """Millimetre-scale container (12000 x 2350 x 2350) with mm pallets."""
    r = check(
        Box(12000, 2350, 2350),
        [Product("pallet", 1200, 800, 1000, 30)],
    )
    assert r.fits
    assert r.units_placed == 30


def test_very_small_dimensions():
    r = check(Box(0.001, 0.001, 0.001), [Product("a", 0.0005, 0.0005, 0.0005, 8)])
    assert r.fits
    assert r.units_placed == 8


def test_zero_height_box_rejected():
    with pytest.raises(ValueError):
        check(Box(0, 10, 10), [Product("a", 1, 1, 1, 1)])


def test_negative_box_dimension_rejected():
    with pytest.raises(ValueError):
        check(Box(10, -10, 10), [Product("a", 1, 1, 1, 1)])


def test_zero_quantity_is_noop():
    r = check(Box(10, 10, 10), [Product("a", 5, 5, 5, 0)])
    assert r.fits
    assert r.units_total == 0
    assert r.remaining_volume_pct == 100.0


def test_all_products_zero_quantity():
    r = check(Box(10, 10, 10), [
        Product("a", 5, 5, 5, 0),
        Product("b", 3, 3, 3, 0),
    ])
    assert r.fits
    assert r.units_total == 0


def test_identical_cubes_grid():
    # 3x3x3 grid of 10-cm cubes in a 30-cm box = 27 units.
    r = check(Box(30, 30, 30), [Product("cube", 10, 10, 10, 27)])
    assert r.fits
    assert r.units_placed == 27
    assert r.remaining_volume == 0


def test_identical_cubes_overfill():
    # 28 cubes of 10 in a 30 box: only 27 fit.
    r = check(Box(30, 30, 30), [Product("cube", 10, 10, 10, 28)])
    assert not r.fits
    assert r.units_placed == 27
    assert r.first_unplaced == ("cube", 28)


def test_two_products_interleave():
    """Two different sizes that must interleave to fit."""
    # Box 10x10x10. One 10x10x5 slab + two 5x5x5 cubes in the remaining half.
    r = check(Box(10, 10, 10), [
        Product("slab", 10, 10, 5, 1),
        Product("cube", 5, 5, 5, 2),
    ])
    assert r.fits
    assert r.units_placed == 3


def test_rotation_only_fit_multi_unit():
    """Units that only fit when rotated, several of them."""
    # Box 25x100x100. Units 30x20x50 only fit rotated (30 > 25 upright).
    r = check(Box(25, 100, 100), [Product("a", 30, 20, 50, 4)])
    assert r.fits
    assert r.units_placed == 4


def test_weight_zero():
    r = check(Box(10, 10, 10, max_weight=100), [Product("a", 5, 5, 5, 2, weight=0)])
    assert r.fits
    assert r.weight_ok
    assert r.total_weight == 0


def test_weight_exactly_at_limit():
    r = check(Box(10, 10, 10, max_weight=100), [Product("a", 5, 5, 5, 2, weight=50)])
    assert r.fits
    assert r.weight_ok  # 100 <= 100


def test_weight_one_over_limit():
    r = check(Box(10, 10, 10, max_weight=100), [Product("a", 5, 5, 5, 3, weight=34)])
    # 3 * 34 = 102 > 100
    assert not r.fits
    assert not r.weight_ok


def test_determinism_across_calls():
    products = [
        Product("a", 30, 25, 20, 5),
        Product("b", 15, 15, 15, 8),
        Product("c", 45, 10, 30, 3),
    ]
    results = [check(Box(100, 80, 60), list(products)) for _ in range(3)]
    for r in results[1:]:
        assert r.fits == results[0].fits
        assert [(p.x, p.y, p.z, p.dx, p.dy, p.dz) for p in r.placements] == [
            (p.x, p.y, p.z, p.dx, p.dy, p.dz) for p in results[0].placements
        ]


def test_no_overlap_invariant_stress():
    """Random-ish mixed sizes: verify no two placements overlap."""
    products = [
        Product("a", 37, 23, 19, 7),
        Product("b", 15, 15, 15, 12),
        Product("c", 50, 12, 28, 4),
        Product("d", 22, 22, 40, 6),
    ]
    r = check(Box(120, 90, 70), products)
    assert r.fits
    eps = 1e-9
    for i, a in enumerate(r.placements):
        for b in r.placements[i + 1:]:
            overlap = not (
                a.x + a.dx <= b.x + eps
                or b.x + b.dx <= a.x + eps
                or a.y + a.dy <= b.y + eps
                or b.y + b.dy <= a.y + eps
                or a.z + a.dz <= b.z + eps
                or b.z + b.dz <= a.z + eps
            )
            assert not overlap, f"overlap between {a} and {b}"


def test_placements_inside_box_invariant():
    products = [
        Product("a", 37, 23, 19, 7),
        Product("b", 15, 15, 15, 12),
        Product("c", 50, 12, 28, 4),
    ]
    r = check(Box(120, 90, 70), products)
    for p in r.placements:
        assert p.x >= 0 and p.y >= 0 and p.z >= 0
        assert p.x + p.dx <= 120 + 1e-9
        assert p.y + p.dy <= 90 + 1e-9
        assert p.z + p.dz <= 70 + 1e-9


def test_large_quantity_performance():
    """1000 identical small units must resolve quickly."""
    r = check(Box(200, 200, 200), [Product("a", 20, 20, 20, 1000)])
    # 10^3 = 1000 units of 20^3 fill a 200^3 box exactly.
    assert r.fits
    assert r.units_placed == 1000
    assert r.remaining_volume == 0


def test_large_quantity_timed():
    """Sanity bound for a large, dense load.

    1000 identical units in a 200^3 box is a pathological worst case for the
    extreme-points heuristic (every candidate position is checked against every
    placed box, and the full-support rule adds a per-candidate area query).
    Typical loads (a few dozen to a few hundred units) resolve in well under a
    second; this bound guards against regressions to many minutes."""
    start = time.perf_counter()
    check(Box(200, 200, 200), [Product("a", 20, 20, 20, 1000)])
    elapsed = time.perf_counter() - start
    assert elapsed < 20, f"took {elapsed:.2f}s"


def test_mixed_sizes_exact_tiling():
    """A box tiled by two different sizes with no waste."""
    # Box 10x10x10: one 10x10x5 slab (bottom) + four 5x5x5 cubes (top half).
    r = check(Box(10, 10, 10), [
        Product("slab", 10, 10, 5, 1),
        Product("cube", 5, 5, 5, 4),
    ])
    assert r.fits
    assert r.units_placed == 5
    assert r.remaining_volume == 0


def test_tall_thin_unit():
    """A unit taller than the box but short in another dimension."""
    r = check(Box(10, 10, 10), [Product("a", 2, 2, 11, 1)])
    # 11 > 10 in every orientation (box max dim is 10).
    assert not r.fits
    assert r.units_placed == 0


def test_unit_fits_only_when_rotated_90():
    """A 6x4x10 unit in a 4x6x10 box: only fits if 6->width, 4->length."""
    r = check(Box(4, 6, 10), [Product("a", 6, 4, 10, 1)])
    assert r.fits
    (pl,) = r.placements
    # Placed orientation must be a permutation, not the canonical (6,4,10).
    assert sorted((pl.dx, pl.dy, pl.dz)) == [4, 6, 10]


def test_empty_placements_when_nothing_fits():
    r = check(Box(5, 5, 5), [Product("a", 6, 6, 6, 5)])
    assert not r.fits
    assert r.placements == []
    assert r.units_placed == 0
    assert r.first_unplaced == ("a", 1)


def test_weight_only_rejection_still_reports_geometry():
    """When weight rejects, all units should still be geometrically placed."""
    r = check(Box(100, 100, 100, max_weight=10), [
        Product("a", 10, 10, 10, 5, weight=10),
    ])
    assert not r.fits
    assert not r.weight_ok
    assert r.units_placed == 5  # geometry fine, weight not


# ---- Full-support rule: no ledges / floating boxes ----

def test_full_support_no_ledge():
    """A box cannot overhang (ledge) — its whole base must be supported.

    Box 100 x 100 x 100. Place a 60x60x10 base box, then a 60x60x10 box
    offset so it would overhang the first. With full support, the second
    cannot rest partially on the first (only 30x60 overlap < full 60x60), so
    it must sit on the floor, not ledge on the first.
    """
    r = check(Box(100, 100, 100), [
        Product("base", 60, 60, 10, 1),
        Product("top", 60, 60, 10, 1),
    ])
    assert r.fits
    (base, top) = r.placements
    # The top box must be fully supported: either on the floor (z=0) or its
    # base fully covered by the base box's top. Verify no partial overhang:
    # if top is at z=10 (on the base), its footprint must be within the base.
    if abs(top.z - 10) < 1e-6:
        # fully covered: top footprint inside base footprint
        assert top.x >= base.x - 1e-6 and top.x + top.dx <= base.x + base.dx + 1e-6
        assert top.y >= base.y - 1e-6 and top.y + top.dy <= base.y + base.dy + 1e-6
    else:
        assert top.z == 0  # on the floor


def test_full_support_rejects_partial_overhang():
    """A unit whose base is only partially covered by supporters cannot be
    placed at that position (no ledge). Construct a case where the only
    'fit' would be a ledge, and confirm it is rejected.

    Box 10 x 100 x 100 (narrow in x). A 20-wide unit cannot stand on the
    floor in x (20 > 10), and cannot ledge on a 10-wide supporter either
    (full 20 base not covered). So it must not fit.
    """
    r = check(Box(10, 100, 100), [
        Product("supporter", 10, 50, 50, 1),
        Product("overhang", 20, 50, 50, 1),
    ])
    # The 20-wide unit's base (20x50) cannot be fully supported: the floor
    # is only 10 wide in x, and the supporter is 10 wide. So it does not fit.
    assert not r.fits


def test_full_support_stacking_still_works():
    """Full support must not break normal stacking: a box exactly on top of
    another (full coverage) is fine."""
    r = check(Box(50, 50, 100), [
        Product("a", 50, 50, 50, 2),
    ])
    assert r.fits
    (p1, p2) = r.placements
    assert p1.z == 0
    assert p2.z == 50  # stacked, fully supported
