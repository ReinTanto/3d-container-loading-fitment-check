"""Unit tests for the core solver."""

from fitcheck.solver import Box, Product, check


def box(l=100, w=100, h=100, max_weight=None):
    return Box(l, w, h, max_weight)


def prod(pid, l, w, h, qty=1, weight=None):
    return Product(pid, l, w, h, qty, weight)


def test_trivially_fits():
    r = check(box(100, 100, 100), [prod("a", 10, 10, 10, qty=5)])
    assert r.fits
    assert r.units_placed == 5
    # 5 units * 10^3 = 5000; box = 100^3 = 1,000,000.
    assert r.used_volume == 5000
    assert r.remaining_volume == 995000
    assert r.remaining_volume_pct == 99.5


def test_exact_fit():
    # 2 x 2 x 2 grid of 50x50x50 boxes in a 100x100x100 box.
    # 8 * 125,000 = 1,000,000 = 100^3 -> exact fit.
    r = check(box(100, 100, 100), [prod("a", 50, 50, 50, qty=8)])
    assert r.fits
    assert r.used_volume == 1_000_000
    assert r.remaining_volume == 0
    assert r.remaining_volume_pct == 0.0


def test_does_not_fit_too_tall():
    r = check(box(100, 100, 100), [prod("a", 10, 10, 101)])
    assert not r.fits
    assert r.first_unplaced == ("a", 1)
    assert r.units_placed == 0


def test_does_not_fit_volume():
    # 30 units of 40x40x40 = 192000 > 100000 box volume.
    r = check(box(100, 100, 100), [prod("a", 40, 40, 40, qty=30)])
    assert not r.fits
    assert r.first_unplaced is not None


def test_rotation_dependent_fit():
    # Box 100 x 50 x 100. A 60x40x100 unit does not fit upright
    # (60 > 50 width? no: 60 fits in 100 length, 40 in 50 width, 100 in 100
    # height — that fits upright). Use a unit that only fits rotated:
    # box 100 x 30 x 100, unit 40 x 20 x 100 -> upright: 40 in 100 ok,
    # 20 in 30 ok, 100 in 100 ok. Still upright.
    # True rotation case: box 100 x 20 x 100, unit 30 x 15 x 90.
    # Upright: 30 in 100 ok, 15 in 20 ok, 90 in 100 ok -> fits upright.
    # Force rotation: box 25 x 100 x 100, unit 30 x 20 x 50.
    # Upright: 30 > 25 -> no. Rotated (20, 30, 50): 20 in 25 ok, 30 in 100
    # ok, 50 in 100 ok -> fits.
    r = check(box(25, 100, 100), [prod("a", 30, 20, 50)])
    assert r.fits
    # The placed orientation must be rotated (dx != 30).
    (pl,) = r.placements
    assert (pl.dx, pl.dy, pl.dz) != (30, 20, 50)
    assert sorted((pl.dx, pl.dy, pl.dz)) == [20, 30, 50]


def test_stacking():
    # Box 10 x 10 x 100. Two units of 10x10x60 must stack (60+60 > 100?
    # no, 120 > 100 -> does NOT fit). Use 10x10x50: two fit stacked.
    r = check(box(10, 10, 100), [prod("a", 10, 10, 50, qty=2)])
    assert r.fits
    (p1, p2) = r.placements
    assert p1.z == 0
    assert p2.z == 50  # stacked on top


def test_weight_limit_ok():
    r = check(box(100, 100, 100, max_weight=1000), [prod("a", 10, 10, 10, qty=5, weight=100)])
    assert r.fits
    assert r.weight_ok
    assert r.total_weight == 500


def test_weight_limit_exceeded():
    r = check(box(100, 100, 100, max_weight=400), [prod("a", 10, 10, 10, qty=5, weight=100)])
    assert not r.fits
    assert not r.weight_ok
    assert r.units_placed == 5  # geometry fits, weight does not


def test_deterministic():
    products = [
        prod("a", 30, 20, 10, qty=3),
        prod("b", 15, 15, 15, qty=5),
        prod("c", 40, 10, 20, qty=2),
    ]
    r1 = check(box(100, 60, 50), products)
    r2 = check(box(100, 60, 50), list(reversed(products)))
    assert r1.fits == r2.fits
    assert [(p.x, p.y, p.z, p.dx, p.dy, p.dz) for p in r1.placements] == [
        (p.x, p.y, p.z, p.dx, p.dy, p.dz) for p in r2.placements
    ]


def test_zero_quantity_product():
    r = check(box(10, 10, 10), [prod("a", 5, 5, 5, qty=0)])
    assert r.fits
    assert r.units_total == 0
    assert r.remaining_volume_pct == 100.0


def test_no_overlap_invariant():
    """Sanity: no two placements may overlap (AABB)."""
    products = [
        prod("a", 30, 25, 20, qty=6),
        prod("b", 15, 15, 15, qty=10),
        prod("c", 45, 10, 30, qty=4),
    ]
    r = check(box(100, 80, 60), products)
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


def test_invalid_dimensions_raise():
    import pytest

    with pytest.raises(ValueError):
        check(box(0, 10, 10), [prod("a", 5, 5, 5)])
    with pytest.raises(ValueError):
        check(box(10, 10, 10), [prod("a", -5, 5, 5)])


def test_invalid_orientation_raises():
    import pytest

    with pytest.raises(ValueError):
        check(box(10, 10, 10), [Product("a", 5, 5, 5, 1, None, "sideways")])


def test_fixed_orientation_forces_upright():
    """A 'fixed' unit that only fits tilted must NOT fit when fixed.

    Box 100 x 100 x 30 (short height). Unit 10 x 10 x 40: upright, its 40
    height exceeds the 30 box height, so it only fits if tilted (40 along a
    horizontal axis). 'any' fits; 'fixed' must not.
    """
    any_r = check(box(100, 100, 30), [prod("a", 10, 10, 40)])
    assert any_r.fits
    fixed_r = check(box(100, 100, 30), [Product("a", 10, 10, 40, 1, None, "fixed")])
    assert not fixed_r.fits
    assert fixed_r.units_placed == 0


def test_fixed_orientation_allows_base_swap():
    """A 'fixed' unit may still swap its base (l<->w), just not tilt.

    Box 40 x 30 x 100. Unit 30 x 40 x 50 (fixed): upright (30 in 40, 40 in
    30 fails) but base-swapped (40 in 40, 30 in 30) fits. So 'fixed' fits.
    """
    r = check(box(40, 30, 100), [Product("a", 30, 40, 50, 1, None, "fixed")])
    assert r.fits
    (pl,) = r.placements
    # height must stay 50 (upright); base is the 40x30 swap.
    assert pl.dz == 50
    assert sorted((pl.dx, pl.dy)) == [30, 40]


def test_fixed_tall_unit_cannot_tilt():
    """A tall 'fixed' unit that would need to lie on its side cannot fit.

    Box 100 x 100 x 50. Unit 10 x 10 x 60 (fixed): 60 > 50 height, so it
    cannot stand; 'any' would let it lie down (60 along a horizontal axis)
    and fit, but 'fixed' must reject it.
    """
    any_r = check(box(100, 100, 50), [prod("a", 10, 10, 60)])
    assert any_r.fits
    fixed_r = check(box(100, 100, 50), [Product("a", 10, 10, 60, 1, None, "fixed")])
    assert not fixed_r.fits
