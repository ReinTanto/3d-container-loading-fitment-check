"""API tests using FastAPI TestClient."""

from fastapi.testclient import TestClient

from fitcheck.api import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_check_fits():
    r = client.post(
        "/check",
        json={
            "box": {"length": 1200, "width": 235, "height": 235},
            "products": [
                {
                    "id": "pallet",
                    "length": 120,
                    "width": 80,
                    "height": 100,
                    "quantity": 10,
                    "weight": 500,
                }
            ],
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["fits"] is True
    assert data["units_placed"] == 10
    assert data["units_total"] == 10
    assert data["weight_ok"] is True
    assert data["first_unplaced"] is None
    assert len(data["placements"]) == 10
    # Response must carry the remaining-space numbers.
    assert 0 <= data["remaining_volume_pct"] <= 100
    assert data["remaining_volume"] > 0
    # Placements must be inside the box.
    b = {"length": 1200, "width": 235, "height": 235}
    for p in data["placements"]:
        assert p["x"] + p["dx"] <= b["length"]
        assert p["y"] + p["dy"] <= b["width"]
        assert p["z"] + p["dz"] <= b["height"]


def test_check_does_not_fit():
    r = client.post(
        "/check",
        json={
            "box": {"length": 100, "width": 100, "height": 100},
            "products": [
                {
                    "id": "big",
                    "length": 101,
                    "width": 10,
                    "height": 10,
                    "quantity": 1,
                }
            ],
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["fits"] is False
    assert data["units_placed"] == 0
    assert data["first_unplaced"] == {"product_id": "big", "unit": 1}


def test_check_weight_rejected():
    r = client.post(
        "/check",
        json={
            "box": {"length": 100, "width": 100, "height": 100, "max_weight": 10},
            "products": [
                {
                    "id": "heavy",
                    "length": 10,
                    "width": 10,
                    "height": 10,
                    "quantity": 2,
                    "weight": 10,
                }
            ],
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["fits"] is False
    assert data["weight_ok"] is False


def test_missing_weight_with_max_weight_is_422():
    r = client.post(
        "/check",
        json={
            "box": {"length": 100, "width": 100, "height": 100, "max_weight": 100},
            "products": [
                {
                    "id": "noweight",
                    "length": 10,
                    "width": 10,
                    "height": 10,
                    "quantity": 1,
                }
            ],
        },
    )
    assert r.status_code == 422


def test_validation_negative_dimension():
    r = client.post(
        "/check",
        json={
            "box": {"length": -5, "width": 100, "height": 100},
            "products": [
                {
                    "id": "a",
                    "length": 10,
                    "width": 10,
                    "height": 10,
                    "quantity": 1,
                }
            ],
        },
    )
    assert r.status_code == 422


def test_validation_empty_products():
    r = client.post(
        "/check",
        json={
            "box": {"length": 100, "width": 100, "height": 100},
            "products": [],
        },
    )
    assert r.status_code == 422


def test_orientation_fixed_rejects_tilt():
    """A fixed-orientation unit that only fits tilted must not fit."""
    r = client.post(
        "/check",
        json={
            "box": {"length": 100, "width": 100, "height": 50},
            "products": [
                {
                    "id": "tall",
                    "length": 10,
                    "width": 10,
                    "height": 60,
                    "quantity": 1,
                    "orientation": "fixed",
                }
            ],
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["fits"] is False
    assert data["units_placed"] == 0


def test_orientation_any_allows_tilt():
    r = client.post(
        "/check",
        json={
            "box": {"length": 100, "width": 100, "height": 50},
            "products": [
                {
                    "id": "tall",
                    "length": 10,
                    "width": 10,
                    "height": 60,
                    "quantity": 1,
                    "orientation": "any",
                }
            ],
        },
    )
    assert r.status_code == 200
    assert r.json()["fits"] is True


def test_invalid_orientation_is_422():
    r = client.post(
        "/check",
        json={
            "box": {"length": 100, "width": 100, "height": 100},
            "products": [
                {
                    "id": "a",
                    "length": 10,
                    "width": 10,
                    "height": 10,
                    "quantity": 1,
                    "orientation": "sideways",
                }
            ],
        },
    )
    assert r.status_code == 422


def test_openapi_served():
    r = client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    assert "/check" in spec["paths"]
    assert "/health" in spec["paths"]
