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
    """Sanity: 1000 units should not take more than a few seconds."""
    start = time.perf_counter()
    check(Box(200, 200, 200), [Product("a", 20, 20, 20, 1000)])
    elapsed = time.perf_counter() - start
    assert elapsed < 10, f"took {elapsed:.2f}s"


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
