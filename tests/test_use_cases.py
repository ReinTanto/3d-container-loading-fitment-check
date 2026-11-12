"""Use-case tests: realistic loading scenarios."""

from fitcheck.solver import Box, Product, check


def test_eu_pallets_in_40ft_container():
    """EU pallets (120x80x100 cm) in a 40 ft container (1200x235x235 cm).

    Capacity analysis (canonical orientation, no rotation gain):
    - x: 1200 / 120 = 10
    - y: 235 / 80 = 2 (2*80=160 <= 235; 3*80=240 > 235)
    - z: 235 / 100 = 2
    => 10 * 2 * 2 = 40 pallets maximum. We ask for 30 -> must fit.
    """
    r = check(
        Box(1200, 235, 235),
        [Product("pallet", 120, 80, 100, 30)],
    )
    assert r.fits
    assert r.units_placed == 30
    # 30 * 960,000 cm^3 = 28,800,000; box = 1200*235*235 = 66,270,000
    assert abs(r.used_volume - 28_800_000) < 1e-3
    assert abs(r.box_volume - 66_270_000) < 1e-3
    assert 0 < r.remaining_volume_pct < 100


def test_pallets_over_capacity():
    """50 pallets in one 40 ft container: physically impossible (max 40)."""
    r = check(
        Box(1200, 235, 235),
        [Product("pallet", 120, 80, 100, 50)],
    )
    assert not r.fits
    assert r.units_placed == 40  # solver fills the container to capacity
    assert r.first_unplaced is not None


def test_mixed_parcel_truck():
    """Mixed parcel sizes in a 2.5 m truck box (250x180x180 cm)."""
    r = check(
        Box(250, 180, 180),
        [
            Product("large", 60, 40, 40, 10),
            Product("medium", 40, 30, 30, 15),
            Product("small", 20, 20, 20, 30),
        ],
    )
    # Total volume: 10*96000 + 15*36000 + 30*8000 = 960000+540000+240000
    # = 1,740,000 cm^3. Box = 250*180*180 = 8,100,000 cm^3.
    # Volume ratio ~21.5%, so it should fit geometrically.
    assert r.fits
    assert r.units_placed == 55
    assert abs(r.used_volume - 1_740_000) < 1e-3


def test_weight_limited_load():
    """Geometry fits but weight limit is exceeded -> fits: false."""
    r = check(
        Box(1200, 235, 235, max_weight=15_000),
        [Product("pallet", 120, 80, 100, 40, weight=500)],
    )
    # 40 pallets * 500 kg = 20,000 kg > 15,000 kg.
    assert not r.fits
    assert r.weight_ok is False
    assert r.units_placed == 40  # all placed geometrically


def test_weight_limited_load_ok():
    r = check(
        Box(1200, 235, 235, max_weight=30_000),
        [Product("pallet", 120, 80, 100, 40, weight=500)],
    )
    assert r.fits
    assert r.weight_ok
    assert r.total_weight == 20_000


def test_single_unit_too_big():
    """A unit larger than the box in one dimension cannot fit."""
    r = check(
        Box(1200, 235, 235),
        [Product("machine", 1300, 200, 200, 1)],
    )
    # 1300 > 1200, but rotated: 1300 could go along... no, the box's largest
    # dimension is 1200, and 1300 > 1200 in every orientation.
    assert not r.fits
    assert r.units_placed == 0
