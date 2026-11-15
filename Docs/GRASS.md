# Wishless — Dense Grass Carpet V2 + Natural Breezes

Status: **GitHub source, queue and regression tests committed. Unreal editor import/render and frame-rate are not verified.**

## Design change

V1 created separate sparse tufts with up to 30,000 randomized points, visibly bare ground and no wind. V1's queued placement is now **retired**. V2 replaces it with:

- `SM_WishlessGrassCarpet.obj`: **96 opaque triangle leaves** distributed across a roughly 2.6 m patch; each blade's UV runs from root (0) to tip (1). The mesh is about 9 KB of OBJ source, one mesh reused everywhere. Two-sided *material*, **not** duplicated backface geometry.
- `0005-import-dense-grass.json`: imports that patch as a shared Static Mesh.
- `0006-dense-grass-breezes.json`: paints an **overlapping 1.85 m grid** over eligible terrain using the dedicated `FT_WishlessGrassCarpet` foliage type.
- `M_WishlessGrassBreeze`: texture-free, opaque, shaded, two-sided material, subtle green gradient and root-anchored GPU World Position Offset.
- Variable wind: a slowly rotating prevailing direction, a broad traveling gust front with smooth rise/fall, and smaller/faster secondary ripples. Adjacent patches experience coherent gusts because the shader reads world position. This visually approximates natural grass motion without any grass actor update, bone simulation, CPU wind simulation or per-blade physics bodies.

## Density and memory

- V2 *tiles the complete eligible bounding rectangles* instead of sparse sampling. A 100 × 100 m hectare produces **3,025 shared foliage patches**, about 290,400 leaf triangles before engine culling and mesh optimization.
- The hard budget defaults to **110,000 patch instances** per currently loaded map. The planner may widen spacing only to **2.25 m** while keeping overlap, and never silently drops random cells when the budget is exhausted.
- Extremely large or highly subdivided levels that exceed the budget **fail with a clear log** instead of producing visually empty ground. For production-scale World Partition landscapes, use Unreal's native **Landscape Grass Output + Landscape Grass Type streaming**, where dense grass is created and culled for the loaded area rather than baked across the whole world.
- HISM foliage type batches instances and supports distance culling and foliage scalability. The grasses cast no shadows and do not need collision. No alpha textures, GPU particles, per-instance actors, animation bones or per-frame Python work.
- The shader vertex movement is approximately several centimeters in light breezes and greater during gusts. It does **not** model fluid dynamics or collision with characters; this is intended as the low-memory, visually natural choice.
- Visibility in the distance depends on the underlying terrain material matching the grass tones; distant sparse/solid-looking terrain can still occur after foliage culling. Do not overwrite the artist's existing Landscape material automatically.

## Safe replacement and replay

- Only **the dedicated old `FT_WishlessGrass` type** is removed via Unreal's foliage API. Other user-painted foliage types remain untouched.
- Before writing the map, V2 saves a local backup of the original `.umap` under `Saved/WishlessBridge/GrassBackups/`. This is an extra backstop, not a substitute for an entire project/World Partition backup.
- Writes a per-map status guard under `Saved/WishlessBridge/DenseGrassV2/`. It refuses to retry automatically after partial failure or save error, preventing repeated foliage duplication.
- The old queue item `0004` no longer scatters V1 grass.
- Never edit the original `Wishless.uproject` or its world materials in this change.

## Terrain coverage rules

- All **loaded LandscapeProxy/Landscape** actors are considered.
- Any StaticMeshActor tagged `GrassSurface`, or named `Ground`, `Terrain`, `Floor` and their underscore-prefixed variants, is considered.
- Per-cell downward collision traces reject steep normals (Z below 0.82), occluding non-ground objects like buildings and paths if they block Visibility, and objects outside the eligible set.
- Holes, water volumes with no collision, roads implemented only as a Landscape painted texture, inaccessible World Partition cells, and other collision/layer-specific regions need additional masking. There is no guarantee that every ground pixel is visually filled without rendering in UE5.

## How to apply and confirm in Unreal 5

1. **Back up the Wishless folder, close the Unreal editor, and sync GitHub `main` safely.** Code under `Content/Python/` is not hot-replaced while the editor is open.
2. Open the level with terrain. Ensure the Wishless Python startup bridge actually loads; Output Log should show `[WishlessBridge] Active`.
3. Confirm `wishless-grass-carpet-mesh-20261115` imported and `wishless-grass-carpet-wind-20261115` ran.
4. Look for `[WishlessGrass] Dense V2 saved: <count> carpet tiles; GPU breezes active`. In Content Browser, locate `/Game/WishlessGenerated/Vegetation/SM_WishlessGrassCarpet`, `FT_WishlessGrassCarpet` and `M_WishlessGrassBreeze`.
5. In material editor verify the Custom HLSL node is connected to World Position Offset; in Play or Simulate mode observe sweeping wind waves rather than identical individual sways. Verify distant culling and low/medium graphics quality.
6. If V2 says the map's tile budget would be exceeded, do **not** simply raise the cap indefinitely: use landscape streaming. If a status guard says placement was interrupted, **do not delete the guard blindly**; inspect the level and its backup to avoid duplicate grass.
7. Manually inspect the Foliage Mode panel and confirm `FT_WishlessGrass` is empty while `FT_WishlessGrassCarpet` has instances. Evaluate memory consumption and frame rate on the target machine. No claim of completed UE5 verification has been made.

## Quality checks

GitHub Actions validates manifests, Python compilation, and layout coverage/memory planning tests. The CI workflow **cannot run Unreal**, compile the HLSL shader, confirm collision hits, confirm output animations, or profile actual VRAM/CPU. Those steps must pass in a real Unreal editor session.

References:
- [Epic: grass quick start / native landscape streaming](https://dev.epicgames.com/documentation/unreal-engine/grass-quick-start-in-unreal-engine)
- [Epic: World Position Offset and SimpleGrassWind](https://dev.epicgames.com/documentation/en-us/unreal-engine/world-position-offset-material-functions-in-unreal-engine)
- [Epic: InstancedFoliageActor Python API](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/InstancedFoliageActor)
