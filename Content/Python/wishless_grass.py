"""Conservative, deterministic foliage placement on loaded Wishless outdoor surfaces.

Only Landscape actors and explicitly tagged ground (or template Floor/Ground meshes)
are eligible. Never paints arbitrary actors, sky, walls, or roofs. Runs in the
Unreal editor, never in a cooked game. Caller tracks completion per map.
"""
from __future__ import annotations

import hashlib
import math
import random

import unreal

GRASS_DIR = "/Game/WishlessGenerated/Vegetation"
MATERIAL = GRASS_DIR + "/M_WishlessGrass"
FOLIAGE = GRASS_DIR + "/FT_WishlessGrass"
MIN_UP = 0.82


def _eligible_surfaces(include_floor: bool):
    candidates = []
    for actor in unreal.EditorLevelLibrary.get_all_level_actors():
        if isinstance(actor, unreal.LandscapeProxy):
            candidates.append(actor)
            continue
        if not include_floor or not isinstance(actor, unreal.StaticMeshActor):
            continue
        label = actor.get_actor_label().lower()
        tags = {str(t).lower() for t in actor.get_editor_property("tags")}
        # An explicit GrassSurface tag is preferred for non-landscape terrain.
        if "grasssurface" in tags or label in ("floor", "ground", "terrain") or label.startswith(("floor_", "ground_", "terrain_")):
            candidates.append(actor)
    return candidates


def _ensure_material(mesh):
    material = unreal.load_asset(MATERIAL)
    if material is None:
        factory = unreal.MaterialFactoryNew()
        material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            "M_WishlessGrass", GRASS_DIR, unreal.Material, factory)
        if material is None:
            raise RuntimeError("Could not create Wishless grass material")
        material.set_editor_property("two_sided", True)
        color = unreal.MaterialEditingLibrary.create_material_expression(
            material, unreal.MaterialExpressionConstant3Vector, -250, 0)
        color.set_editor_property("constant", unreal.LinearColor(0.20, 0.28, 0.14, 1.0))
        unreal.MaterialEditingLibrary.connect_material_property(
            color, "", unreal.MaterialProperty.MP_BASE_COLOR)
        rough = unreal.MaterialEditingLibrary.create_material_expression(
            material, unreal.MaterialExpressionConstant, -250, 170)
        rough.set_editor_property("r", 0.95)
        unreal.MaterialEditingLibrary.connect_material_property(
            rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
        errors = unreal.MaterialEditingLibrary.recompile_material(material)
        if errors:
            raise RuntimeError("Grass material compile failed: " + str(errors))
        unreal.EditorAssetLibrary.save_loaded_asset(material)
    mesh.set_material(0, material)
    unreal.EditorAssetLibrary.save_loaded_asset(mesh)
    return material


def _ensure_foliage(mesh):
    foliage = unreal.load_asset(FOLIAGE)
    if foliage is None:
        foliage = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            "FT_WishlessGrass", GRASS_DIR,
            unreal.FoliageType_InstancedStaticMesh,
            unreal.FoliageType_InstancedStaticMeshFactory())
        if foliage is None:
            raise RuntimeError("Could not create Wishless grass foliage type")
    foliage.set_editor_property("mesh", mesh)
    foliage.set_editor_property("enable_density_scaling", True)
    foliage.set_editor_property("cast_shadow", False)
    # Foliage scalability can discard grass on lower-end devices.
    # Clamp visual distance, without coupling the operation to engine-specific enums.
    try:
        foliage.set_editor_property(
            "cull_distance", unreal.Int32Interval(min=1800, max=9000))
    except (AttributeError, TypeError, RuntimeError) as exc:
        unreal.log_warning("[WishlessGrass] Cull interval unavailable: " + str(exc))
    unreal.EditorAssetLibrary.save_loaded_asset(foliage)
    return foliage


def _bounds(surface):
    center, extents = surface.get_actor_bounds(False)
    area = max(0, 2 * extents.x) * max(0, 2 * extents.y)
    return center, extents, area


def _surface_samples(world, surface, step, budget, seed, eligible_names):
    center, extent, _ = _bounds(surface)
    if min(extent.x, extent.y) < 25:
        return []
    nx = max(1, int((2 * extent.x) // step))
    ny = max(1, int((2 * extent.y) // step))
    count = min(budget, nx * ny)
    rng = random.Random(seed)
    # Covers the whole bounding rectangle, with a fixed seed and no expensive
    # square-meter-by-square-meter operations on vast landscapes.
    indices = list(range(nx * ny))
    if len(indices) > count:
        indices = rng.sample(indices, count)
    transforms = []
    ztop = center.z + extent.z + 500
    zbottom = center.z - extent.z - 500
    for index in indices:
        gx, gy = index % nx, index // nx
        x = center.x - extent.x + (gx + rng.uniform(0.2, 0.8)) * (2 * extent.x / nx)
        y = center.y - extent.y + (gy + rng.uniform(0.2, 0.8)) * (2 * extent.y / ny)
        hit = unreal.SystemLibrary.line_trace_single(
            world, unreal.Vector(x, y, ztop), unreal.Vector(x, y, zbottom),
            unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, [],
            unreal.DrawDebugTrace.NONE)
        if not hit or not hit.get_editor_property("blocking_hit"):
            continue
        struck = hit.get_editor_property("hit_actor")
        if struck is None or struck.get_path_name() not in eligible_names:
            # This also prevents grass penetrating buildings, roads represented
            # by blocking mesh actors, and other non-terrain objects.
            continue
        up = hit.get_editor_property("impact_normal")
        if up.z < MIN_UP:
            continue
        point = hit.get_editor_property("impact_point")
        scale = rng.uniform(0.78, 1.26)
        transforms.append(unreal.Transform(
            location=unreal.Vector(point.x, point.y, point.z - 2.0),
            rotation=unreal.Rotator(0, rng.uniform(0, 360), 0),
            scale=unreal.Vector(scale, scale, scale * rng.uniform(0.8, 1.15))))
    return transforms


def scatter_grass(operation: dict) -> int:
    subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if subsystem.is_in_play_in_editor():
        raise RuntimeError("Grass scattering cannot run during PIE")
    world = unreal.EditorLevelLibrary.get_editor_world()
    surfaces = _eligible_surfaces(operation.get("include_floor", True))
    if not surfaces:
        raise RuntimeError(
            "No loaded Landscape or eligible ground: add a Landscape or tag a "
            "ground StaticMeshActor GrassSurface, then open that level")
    mesh = unreal.load_asset(operation["mesh"])
    if mesh is None or not isinstance(mesh, unreal.StaticMesh):
        raise RuntimeError("Grass mesh not imported yet: " + operation["mesh"])
    unreal.EditorAssetLibrary.make_directory(GRASS_DIR)
    _ensure_material(mesh)
    foliage = _ensure_foliage(mesh)

    # Keep a single operation bounded and distribute the budget by surface area.
    surface_info = [(s, _bounds(s)[2]) for s in surfaces if _bounds(s)[2] > 0]
    total_area = sum(area for _, area in surface_info)
    if total_area <= 0:
        raise RuntimeError("No grass-capable terrain area was found")
    budget = operation.get("max_instances", 30000)
    spacing = operation.get("spacing_cm", 125)
    seed = operation.get("seed", 7241)
    names = {s.get_path_name() for s in surfaces}
    transforms = []
    for surface, area in surface_info:
        remaining = budget - len(transforms)
        if remaining <= 0:
            break
        share = max(1, min(remaining, round(budget * area / total_area)))
        step = max(spacing, math.sqrt(area / share))
        surface_seed = int(hashlib.sha256(
            (surface.get_path_name() + str(seed)).encode("utf-8")).hexdigest()[:8], 16)
        transforms.extend(_surface_samples(
            world, surface, step, share, surface_seed, names))
    if not transforms:
        raise RuntimeError(
            "Grass placement found no eligible terrain hits: verify Landscape/ground "
            "collision responds to Visibility, and terrain is not covered by blockers")

    unreal.InstancedFoliageActor.add_instances(world, foliage, transforms)
    if not unreal.EditorLevelLibrary.save_current_level():
        raise RuntimeError("Placed grass but the current UE level could not be saved")
    unreal.log("[WishlessGrass] Placed and saved {} foliage clumps in {} ({} surfaces)".format(
        len(transforms), world.get_path_name(), len(surfaces)))
    return len(transforms)
