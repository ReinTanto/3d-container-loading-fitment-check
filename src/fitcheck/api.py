"""FastAPI application for the fitment check service."""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .solver import Box, CheckResult, Product, check

app = FastAPI(
    title="3D Container Loading Fitment Check",
    version="1.0.0",
    description=(
        "Check whether a set of products fits in a container (truck box, "
        "shipping container). Returns a boolean plus the remaining space in "
        "volume and percentage. Self-hosted, no credentials required.\n\n"
        "**Honesty caveat:** `fits: true` is reliable (a valid placement is "
        "returned). `fits: false` means the heuristic did not find an "
        "arrangement; it is not a proof that none exists."
    ),
)

# Allow the local test frontend (and any origin) to call the API. This is a
# self-hosted tool with no credentials, so permissive CORS is acceptable.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class BoxIn(BaseModel):
    length: float = Field(gt=0, description="Container length (any consistent unit)")
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    max_weight: float | None = Field(default=None, gt=0, description="Optional weight limit")


class ProductIn(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    length: float = Field(gt=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    quantity: int = Field(ge=0, le=100_000)
    weight: float | None = Field(default=None, ge=0)
    # "any" = may be rotated freely (all 6 orientations);
    # "fixed" = must stay upright (only the base length/width may swap).
    orientation: Literal["any", "fixed"] = "any"


class CheckRequest(BaseModel):
    box: BoxIn
    products: list[ProductIn] = Field(min_length=1)


class PlacementOut(BaseModel):
    product_id: str
    unit: int
    x: float
    y: float
    z: float
    dx: float
    dy: float
    dz: float


class CheckResponse(BaseModel):
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
    placements: list[PlacementOut]
    first_unplaced: dict | None = None


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/check", response_model=CheckResponse)
def check_endpoint(req: CheckRequest) -> CheckResponse:
    if req.box.max_weight is not None:
        for p in req.products:
            if p.weight is None:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"box.max_weight is set but product {p.id!r} has no "
                        "weight; add a weight to every product"
                    ),
                )

    box = Box(
        length=req.box.length,
        width=req.box.width,
        height=req.box.height,
        max_weight=req.box.max_weight,
    )
    products = [
        Product(
            id=p.id,
            length=p.length,
            width=p.width,
            height=p.height,
            quantity=p.quantity,
            weight=p.weight,
            orientation=p.orientation,
        )
        for p in req.products
    ]

    try:
        result: CheckResult = check(box, products)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return CheckResponse(
        fits=result.fits,
        units_total=result.units_total,
        units_placed=result.units_placed,
        box_volume=result.box_volume,
        used_volume=result.used_volume,
        remaining_volume=result.remaining_volume,
        remaining_volume_pct=result.remaining_volume_pct,
        used_volume_pct=result.used_volume_pct,
        total_weight=result.total_weight,
        max_weight=result.max_weight,
        weight_ok=result.weight_ok,
        placements=[
            PlacementOut(**vars(pl)) for pl in result.placements
        ],
        first_unplaced=(
            {"product_id": result.first_unplaced[0], "unit": result.first_unplaced[1]}
            if result.first_unplaced
            else None
        ),
    )
