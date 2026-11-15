"""Wishless V2: dense, low-memory grass carpet with GPU-only breezes.

Single 96-triangle mesh reused in hierarchical foliage clusters. A deterministic
near-overlapping tile grid covers every eligible loaded terrain area within a
fixed memory budget. Rendering-time wind is world-space WPO, not actors ticking
or simulating rigid bodies. Only Wishless's own V1 foliage is removed.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import shutil
from pathlib import Path

import unreal

from grass_hit import visible_ground_hit
from grass_layout import plan_level

ROOT = Path(unreal.Paths.project_dir()).resolve()
GENERATED = "/Game/WishlessGenerated/Vegetation"
MESH = GENERATED + "/SM_WishlessGrassCarpet"
MATERIAL = GENERATED + "/M_WishlessGrassBreeze"
FOLIAGE = GENERATED + "/FT_WishlessGrassCarpet"
OLD_FOLIAGE = GENERATED + "/FT_WishlessGrass"
VERSION = 2

# This HLSL runs on mesh vertices. Adjacent patches share smooth world-space
# gust fronts, and UV.y anchors the bottom of every blade. No CPU grass tick.
BREEZE_HLSL = """
float2 p = WS.xy * 0.0017;
float t = Clock;
float2 direction = normalize(float2(0.82 + 0.18 * sin(t * 0.067),
                                    0.53 + 0.16 * cos(t * 0.049)));
float phase = dot(p, direction);
float front = 0.5 + 0.5 * sin(phase * 1.35 - t * 0.27);
float gust = front * front * (3.0 - 2.0 * front);
float billow = sin(phase * 2.9 - t * 0.95);
float ripple = sin(p.x * 8.1 + p.y * 6.9 + t * 2.25);
float tether = saturate(UV.y);
tether = tether * tether;
float sideways = (3.8 + 11.0 * gust) *
                 (0.30 + 0.48 * billow + 0.22 * ripple) * tether;
return float3(direction.x * sideways, direction.y * sideways,
              -abs(sideways) * 0.12);
""".strip()


def _make_material(mesh):
    material = unreal.load_asset(MATERIAL)
    if material is None:
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        material = asset_tools.create_asset(
            "M_WishlessGrassBreeze", GENERATED, unreal.Material, unreal.MaterialFactoryNew())
        if material is None:
            raise RuntimeError("Grass wind material could not be created")
        material.set_editor_property("two_sided", True)

        edit = unreal.MaterialEditingLibrary

        dark = edit.create_material_expression(material, unreal.MaterialExpressionConstant3Vector, -780, -340)
        dark.set_editor_property("constant", unreal.LinearColor(0.105, 0.172, 0.07, 1))
        light = edit.create_material_expression(material, unreal.MaterialExpressionConstant3Vector, -780, -160)
        light.set_editor_property("constant", unreal.LinearColor(0.238, 0.31, 0.118, 1))
        uv = edit.create_material_expression(material, unreal.MaterialExpressionTextureCoordinate, -850, 160)
        mask = edit.create_material_expression(material, unreal.MaterialExpressionComponentMask, -570, 130)
        mask.set_editor_property("r", False)
        mask.set_editor_property("g", True)
        mask.set_editor_property("b", False)
        mask.set_editor_property("a", False)
        edit.connect_material_expressions(uv, "", mask, "")
        blend = edit.create_material_expression(material, unreal.MaterialExpressionLinearInterpolate, -290, -200)
        edit.connect_material_expressions(dark, "", blend, "A")
        edit.connect_material_expressions(light, "", blend, "B")
        edit.connect_material_expressions(mask, "", blend, "Alpha")
        if not edit.connect_material_property(blend, "", unreal.MaterialProperty.MP_BASE_COLOR):
            raise RuntimeError("Unable to attach grass color shader")

        rough = edit.create_material_expression(material, unreal.MaterialExpressionConstant, -300, -30)
        rough.set_editor_property("r", 0.94)
        edit.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)

        world_position = edit.create_material_expression(
            material, unreal.MaterialExpressionWorldPosition, -850, 350)
        game_time = edit.create_material_expression(
            material, unreal.MaterialExpressionTime, -840, 550)
        wind = edit.create_material_expression(material, unreal.MaterialExpressionCustom, -400, 330)
        wind.set_editor_property("desc", "Wishless: world-coherent irregular gusts / anchored blades")
        wind.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT3)
        wind.set_editor_property("inputs", [
            unreal.CustomInput(input_name="WS"),
            unreal.CustomInput(input_name="Clock"),
            unreal.CustomInput(input_name="UV"),
        ])
        wind.set_editor_property("code", BREEZE_HLSL)
        for node, input_name in [
                (world_position, "WS"), (game_time, "Clock"), (uv, "UV")]:
            if not edit.connect_material_expressions(node, "", wind, input_name):
                raise RuntimeError("Could not attach grass wind input " + input_name)
        if not edit.connect_material_property(
                wind, "", unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET):
            raise RuntimeError("Could not connect breeze animation to grass mesh")
        try:
            material.set_editor_property("max_world_position_offset_displacement", 32.0)
        except (AttributeError, RuntimeError):
            pass
        issues = edit.recompile_material(material)
        if issues:
            raise RuntimeError("Grass wind shader compile failed: " + repr(issues))
        unreal.EditorAssetLibrary.save_loaded_asset(material)

    if mesh.get_material(0) != material:
        mesh.set_material(0, material)
        unreal.EditorAssetLibrary.save_loaded_asset(mesh)
    return material


def _make_foliage(mesh):
    foliage = unreal.load_asset(FOLIAGE)
    if foliage is None:
        foliage = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            "FT_WishlessGrassCarpet", GENERATED,
            unreal.FoliageType_InstancedStaticMesh,
            unreal.FoliageType_InstancedStaticMeshFactory())
        if foliage is None:
            raise RuntimeError("Cannot create dense grass foliage type")
    foliage.set_editor_property("mesh", mesh)
    foliage.set_editor_property("cast_shadow", False)
    foliage.set_editor_property("cast_dynamic_shadow", False)
    foliage.set_editor_property("cast_static_shadow", False)
    foliage.set_editor_property("enable_density_scaling", True)
    foliage.set_editor_property("collision_with_world", False)
    # Cull whole instance clusters beyond 90m. All instances share the same
    # mesh and material; no grass component or actor per blade/patch.
    foliage.set_editor_property("cull_distance", unreal.Int32Interval(min=3500, max=9000))
    for prop, value in (("evaluate_world_position_offset", True),
                        ("world_position_offset_disable_distance", 10000)):
        try:
            foliage.set_editor_property(prop, value)
        except (AttributeError, RuntimeError):
            unreal.log_warning("[WishlessGrass] UE lacks foliage setting " + prop)
    try:
        body = foliage.get_editor_property("body_instance")
        body.set_editor_property("collision_enabled", unreal.CollisionEnabled.NO_COLLISION)
        foliage.set_editor_property("body_instance", body)
    except (AttributeError, RuntimeError):
        unreal.log_warning("[WishlessGrass] Confirm grass collision is disabled in foliage asset")
    unreal.EditorAssetLibrary.save_loaded_asset(foliage)
    return foliage


def _surfaces():
    result = []
    for actor in unreal.EditorLevelLibrary.get_all_level_actors():
        if isinstance(actor, unreal.LandscapeProxy):
            result.append(actor)
        elif isinstance(actor, unreal.StaticMeshActor):
            tags = {str(t).lower() for t in actor.get_editor_property("tags")}
            name = actor.get_actor_label().lower()
            if ("grasssurface" in tags or name in ("floor", "ground", "terrain")
                    or name.startswith(("floor_", "ground_", "terrain_"))):
                result.append(actor)
    return result


def _backup_map(world):
    name = world.get_path_name().split(".", 1)[0]
    if not name.startswith("/Game/"):
        raise RuntimeError("Save the current level under /Game before adding grass")
    map_file = (ROOT / "Content" / (name[6:] + ".umap")).resolve()
    if not map_file.is_relative_to((ROOT / "Content").resolve()) or not map_file.is_file():
        raise RuntimeError("Cannot locate the on-disk level for backup: " + name)
    map_hash = hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]
    dest = ROOT / "Saved" / "WishlessBridge" / "GrassBackups" / (map_hash + "_before_dense_v2.umap")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        shutil.copy2(map_file, dest)
    return dest


def _get_hit(world, x, y, center, extent, names):
    hit = unreal.SystemLibrary.line_trace_single(
        world,
        unreal.Vector(x, y, center.z + extent.z + 600.0),
        unreal.Vector(x, y, center.z - extent.z - 600.0),
        unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, [],
        unreal.DrawDebugTrace.NONE)
    result = visible_ground_hit(hit)
    if result is None:
        return None
    actor, normal, point = result
    if actor.get_path_name() not in names or normal.z < 0.82:
        return None
    return point, normal


def _generate(world, surfaces, plans, seed):
    names = {a.get_path_name() for a in surfaces}
    for surface, grid in zip(surfaces, plans):
        center, bounds = surface.get_actor_bounds(False)
        salt = int(hashlib.sha256((surface.get_path_name() + str(seed)).encode("utf8")).hexdigest()[:8], 16)
        rng = random.Random(salt)
        start_x, start_y = center.x - bounds.x, center.y - bounds.y
        buffer = []
        for j in range(grid.ny):
            for i in range(grid.nx):
                # Jitter by at most 5%, preserving carpet footprint overlap.
                x = start_x + (i + 0.5 + rng.uniform(-.05, .05)) * grid.step_x
                y = start_y + (j + 0.5 + rng.uniform(-.05, .05)) * grid.step_y
                hit = _get_hit(world, x, y, center, bounds, names)
                if hit is None:
                    continue
                point, normal = hit
                # Align blades with the ground normal on rolling terrain.
                # This prevents the 2.6m footprint hovering above a hillside.
                rotation = unreal.MathLibrary.make_rot_from_z(normal)
                rotation.yaw += rng.uniform(-8, 8)
                size = rng.uniform(0.97, 1.06)
                buffer.append(unreal.Transform(
                    location=unreal.Vector(point.x, point.y, point.z - 1.5),
                    rotation=rotation,
                    scale=unreal.Vector(size, size, rng.uniform(0.85, 1.17))))
                if len(buffer) >= 2500:
                    yield buffer
                    buffer = []
        if buffer:
            yield buffer


def scatter_dense_grass(op):
    world = unreal.EditorLevelLibrary.get_editor_world()
    if not world or unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor():
        raise RuntimeError("Grass generation requires an open editor level outside Play mode")
    surfaces = _surfaces()
    if not surfaces:
        raise RuntimeError("No Landscape or GrassSurface ground is currently loaded")
    mesh = unreal.load_asset(MESH)
    if not isinstance(mesh, unreal.StaticMesh):
        raise RuntimeError("Missing dense grass carpet mesh; asset import must complete first")

    # Each grass patch spans 260cm; ~185cm grid = regular continuous overlap.
    bounds = [s.get_actor_bounds(False)[1] for s in surfaces]
    sizes = [(max(1.0, 2*b.x), max(1.0, 2*b.y)) for b in bounds]
    spacing, plans = plan_level(
        sizes, op.get("max_instances", 110000), op.get("spacing_cm", 185))
    estimate = sum(p.count for p in plans)
    unreal.log("[WishlessGrass] Coverage plan: {} tiles; step {:.1f}cm; {} eligible surfaces".format(
        estimate, spacing, len(surfaces)))

    state_dir = ROOT / "Saved" / "WishlessBridge" / "DenseGrassV2"
    state_dir.mkdir(parents=True, exist_ok=True)
    world_hash = hashlib.sha256(world.get_path_name().encode("utf8")).hexdigest()
    guard = state_dir / (world_hash + ".json")
    if guard.is_file():
        data = json.loads(guard.read_text(encoding="utf8"))
        if data.get("state") == "saved" and data.get("version") == VERSION:
            unreal.log("[WishlessGrass] V2 already saved for this map; skipping duplication")
            return data.get("count", 0)
        raise RuntimeError("Grass V2 was interrupted; inspect map and guard before retry")

    _make_material(mesh)
    foliage = _make_foliage(mesh)
    backup = _backup_map(world)
    unreal.log("[WishlessGrass] Original map backed up to " + str(backup))

    def state(value, count):
        temp = guard.with_suffix(".tmp")
        temp.write_text(json.dumps({
            "state": value, "count": count, "version": VERSION,
            "map": world.get_path_name(), "backup": str(backup),
            "spacing_cm": spacing}, indent=2) + "\n", encoding="utf8")
        os.replace(temp, guard)

    # Persist in-progress before any world mutation. No automatic retry after
    # partial error: this avoids multiplying foliage in an unsaved level.
    state("started", 0)
    count = 0
    for transforms in _generate(world, surfaces, plans, op.get("seed", 20261115)):
        unreal.InstancedFoliageActor.add_instances(world, foliage, transforms)
        count += len(transforms)
    if count == 0:
        raise RuntimeError("No ground hits: verify landscape collisions on Visibility channel")
    # Remove only the exact dedicated *Wishless V1* foliage type, not any
    # foliage hand-painted with another type or owned by the artist.
    legacy = unreal.load_asset(OLD_FOLIAGE)
    if legacy:
        unreal.InstancedFoliageActor.remove_all_instances(world, legacy)
    if not unreal.EditorLevelLibrary.save_current_level():
        raise RuntimeError("UE5 could not save level; duplicate-safe guard requires inspection")
    state("saved", count)
    unreal.log("[WishlessGrass] Dense V2 saved: {} carpet tiles; GPU breezes active".format(count))
    return count
