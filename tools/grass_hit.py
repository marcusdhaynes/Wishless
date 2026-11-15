"""Read Unreal HitResult without accessing protected editor properties.

UE5's SystemLibrary.line_trace_single returns a HitResult or None. Its struct
fields may be protected from get_editor_property(), but StructBase.to_tuple()
exposes the documented FHitResult field order (UE 5.x).
"""
from __future__ import annotations


def visible_ground_hit(hit):
    """Return (actor, impact_normal, impact_point) or None for a miss.

    Early FHitResult field order: blocking_hit[0], impact_point[5],
    impact_normal[7], hit_actor[9]. Fail closed on unfamiliar layouts.
    """
    if hit is None:
        return None
    fields = hit.to_tuple()
    if len(fields) < 10:
        raise RuntimeError("Unexpected UE5 HitResult layout; refusing grass placement")
    if not isinstance(fields[0], bool):
        raise RuntimeError("Unexpected blocking_hit field in UE5 HitResult")
    if not fields[0]:
        return None
    actor, normal, point = fields[9], fields[7], fields[5]
    if (actor is None or not hasattr(actor, "get_path_name")
            or normal is None or not hasattr(normal, "z")
            or point is None or not all(hasattr(point, name) for name in ("x", "y", "z"))):
        raise RuntimeError("Unexpected actor/point/normal in UE5 HitResult")
    return actor, normal, point
