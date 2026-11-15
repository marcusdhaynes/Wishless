# Wishless grass coverage — 2026-11-15

Status: **GitHub implementation committed; UE5 editor execution not verified.**

## What is queued

- `0003-grass-mesh.json` imports `SourceAssets/Vegetation/SM_WishlessGrass.obj`, a tiny 12-blade, double-sided polygonal tuft.
- `0004-cover-terrain-grass.json` places up to 30,000 hardware-instanced grass clumps across eligible surfaces in the **currently loaded level**. This applies again when a different level is opened because the queue tracks grass placement per map.
- The engine creates generated vegetation mesh, material and foliage type assets below `/Game/WishlessGenerated/Vegetation/`; the original `.uproject`, game maps and gameplay assets are not replaced by GitHub.

## Placement rules

- All loaded **Landscape** actors and their proxies are eligible.
- Explicitly tag a ground StaticMeshActor `GrassSurface` to opt it in; when `include_floor=true`, template static meshes labeled `Floor`, `Ground`, `Terrain` and their underscore-prefixed variants are also eligible.
- Upward-facing surface normal must have `Z >= 0.82` (around 35 degrees maximum slope).
- Each point is verified by a downward collision trace. If a blocking path, wall, house, roof or similar non-ground mesh is above the terrain, that hit is rejected.
- **Painted path layers on a Landscape cannot be identified by the current filter**; to exclude them, use blocking path geometry or implement a landscape layer exclusion mask before production.
- Vegetation uses a muted green, two-sided opaque material, no grass shadow casting, foliage scalability and culling where available.
- Density adapts to the area to remain under the maximum instance count. This is a conservative first-pass, not an unlimited runtime grass system.

## How to observe

1. Back up your local Wishless project first, then ensure the GitHub `main` branch is safely synced. Changes to `Content/Python/` and `tools/` require the Unreal editor to be closed while syncing, then reopened.
2. Open an Unreal map containing a Landscape or eligible ground mesh.
3. Look for `[WishlessBridge] Applied: wishless-grass-mesh-20261115` and `[WishlessGrass] Placed and saved ...` in **Output Log**.
4. Inspect `Content/WishlessGenerated/Vegetation` and the current level's `InstancedFoliageActor` for generated grass. Look in `Saved/WishlessBridge/applied.json` for a per-map completion record. The asset-import entry should also appear.
5. If no terrain exists yet, the queue remains pending and displays a specific error; create a Landscape or tag ground and it will retry. Ensure terrain collision responds to the Visibility trace channel.
6. To adjust coverage, change `spacing_cm` (70–500) and `max_instances` (100–60,000), then test in a copy of the map. **Do not simply rerun on an already-painted map**, as existing grass instances are not removed automatically.

## Known limitations

Only open/loaded levels can be populated by this editor queue. Unloaded World Partition cells, painted material exclusion regions, water exclusions without collision, and performance on target devices need in-editor verification. GitHub Actions tests schema and source syntax, not asset import or rendering.

Useful engine API references:
- https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/InstancedFoliageActor
- https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/FoliageType_InstancedStaticMesh
- https://dev.epicgames.com/documentation/unreal-engine/foliage-mode-in-unreal-engine
