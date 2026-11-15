"""Deterministic, coverage-first grass tile planning (pure Python, no Unreal dependency).

One broad, root-anchored cluster per grid cell, not tens of independent foliage
actors. Never silently sparse-sample a large landscape to fit an arbitrary cap.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil, sqrt


@dataclass(frozen=True)
class TilePlan:
    nx: int
    ny: int
    step_x: float
    step_y: float

    @property
    def count(self) -> int:
        return self.nx * self.ny


def plan_grid(width: float, height: float, spacing: float) -> TilePlan:
    if width <= 0 or height <= 0 or not 120 <= spacing <= 225:
        raise ValueError("invalid grass coverage bounds or spacing")
    nx, ny = max(1, ceil(width / spacing)), max(1, ceil(height / spacing))
    return TilePlan(nx, ny, width / nx, height / ny)


def plan_level(sizes: list[tuple[float, float]], budget: int = 110000,
               preferred: float = 185.0, maximum: float = 225.0):
    if not 100 <= budget <= 180000:
        raise ValueError("grass instance budget outside safe range")
    if not 120 <= preferred <= maximum <= 225:
        raise ValueError("invalid grass tile spacing")
    if not sizes:
        raise ValueError("no eligible surfaces")
    # A single step across all surfaces avoids a sparse edge at surface borders.
    preferred_plans = [plan_grid(w, h, preferred) for w, h in sizes]
    if sum(p.count for p in preferred_plans) <= budget:
        return preferred, preferred_plans
    maximum_plans = [plan_grid(w, h, maximum) for w, h in sizes]
    required = sum(p.count for p in maximum_plans)
    if required > budget:
        raise ValueError(
            "Level requires at least {} dense grass carpet tiles, cap {}; "
            "use Landscape Grass Output / World Partition streaming rather "
            "than generating sparse or excessively scaled grass".format(required, budget))
    # Binary search spacing, preserving dense coverage but fitting the cap.
    low, high = preferred, maximum
    for _ in range(24):
        mid = (low + high) / 2
        if sum(plan_grid(w, h, mid).count for w, h in sizes) > budget:
            low = mid
        else:
            high = mid
    return high, [plan_grid(w, h, high) for w, h in sizes]
