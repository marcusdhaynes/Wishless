# Wishless — ChatGPT → GitHub → Unreal Engine 5

Repository: https://github.com/marcusdhaynes/Wishless  
Branch: `main` only.  
Status: UE5 starter project + source-control bridge. Game systems and art still need development and engine-side validation.

## Architecture

```text
You instruct ChatGPT
  → ChatGPT commits Wishless code/assets/automation to GitHub main
  → GitHub Actions validates JSON and Python tests
  → your Windows workstation polls origin/main (default 15 s)
  → non-conflicting local changes: fast-forward only, no force reset
  → open UE editor: only source assets/automation/docs sync live
  → UE5 Python startup script monitors queue every 3 s
  → supported operations import sources, create folders, or scatter grass on eligible terrain
  → native assets/C++/settings wait for editor exit and safe restart
```

## One-time Windows setup

1. Install Unreal Engine 5, Git for Windows, Git LFS, Python 3.11+. Run `git lfs install` once. Configure Windows to open `.uproject` files with Unreal Editor.
2. **If creating a new project**, clone the repo:
   ```powershell
   git clone https://github.com/marcusdhaynes/Wishless.git
   cd Wishless
   ```
   **If Wishless is already a local UE5 project**, back up that project and integrate the bridge into its current folder carefully; do not overwrite an existing `.uproject` or existing content.
3. Launch the bridge and UE5 together:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\Start-Wishless.ps1
   ```
   Leave the PowerShell window running for continuous GitHub polling.
4. In UE5 **Output Log**, check for `[WishlessBridge] Active` and `Applied: wishless-bootstrap-0001` the first time. The bootstrap creates the generated-content folder.

## How ChatGPT changes reach Unreal

For assets, commit source art/audio/mesh files under `SourceAssets/` and a JSON declaration under `Automation/Queue/`. Example (requires the referenced FBX to be committed):

```json
{
  "schema_version": 1,
  "id": "import-test-mesh-0002",
  "operations": [
    {"type": "ensure_folder", "path": "/Game/WishlessGenerated/Props"},
    {"type": "import_asset", "source": "SourceAssets/Props/example.fbx", "destination": "/Game/WishlessGenerated/Props", "asset_name": "SM_Example"}
  ]
}
```

The editor validates these operations again, imports them through Unreal's Asset Import Tasks API, and records completed manifests in `Saved/WishlessBridge/applied.json`. Generated assets under `Content/WishlessGenerated/` are not stored in Git; they are recreated by import. Version **hand-edited** `.uasset` and `.umap` files outside that folder using Git LFS.

## Dense grass and natural breezes (V2)

Current queue: `0005-import-dense-grass.json` imports the shared 96-triangle grass carpet; `0006-dense-grass-breezes.json` builds a texture-free grass material with root-anchored, world-coherent GPU gusts and densely tiles loaded outdoor ground (185 cm spacing, up to 110,000 patch instances). Old V1 scatter queue `0004` is retired. V2 preserves existing landscapes/materials, backs up the level and removes **only** Wishless's old foliage type. This is optimized to reuse one mesh and one material, not spawn separate grass actors or use per-blade CPU physics. **GitHub tests pass; Unreal editor import, rendering and memory are not yet independently verified.**

For exact terrain rules, World Partition scalability, backup/safe replay and viewport verification: [Docs/GRASS.md](Docs/GRASS.md).

## Safety and limits

- Only the `main` branch is used. The synchronizer **never** force-resets, rebases, or overwrites dirty local files. Unrelated local project files are preserved; overlapping incoming changes are blocked.
- A running UE5 editor is signaled by a heartbeat written under `Saved/`. Only source art, automation queue, and docs are fast-forwarded while the editor is active.
- **C++ code, loaded Blueprints, native Unreal asset packages and settings cannot be safely replaced live in all cases.** Close and reopen Unreal to receive these changes. C++ may require compilation.
- The manifest interpreter accepts only `ensure_folder`, `import_asset`, and the narrowly scoped `scatter_grass` (V1 retired) and `dense_grass` terrain operations; it rejects arbitrary command execution, path traversal, and imports outside `SourceAssets/` or `/Game/WishlessGenerated`.
- `python tools/wishless_sync.py once` checks once; `python tools/wishless_sync.py status` reports last status. Inspect `.wishless/status.json` for `updated`, `up_to_date`, `pending_editor_restart`, `blocked_local_changes`, `diverged`, or `lfs_error`.
- GitHub Actions checks JSON, Python syntax, and Git safety tests; **it does not run UE5 or compile/package the game**. A functioning UE5 workstation is needed for final integration proof.
- The GitHub repository is public. Never commit secrets, keys, proprietary licensed engine content, or materials you do not have distribution rights to.

## Supabase

The Wishless entry already exists in Somniel Holdings' Supabase project. No Supabase modification or API key is required for this GitHub → UE5 synchronization bridge. Supabase can later store build histories, workflow status, and canon decisions separately.

## Official implementation references

- Epic Python editor startup: https://dev.epicgames.com/documentation/unreal-engine/scripting-the-unreal-editor-using-python
- Epic automatic reimport: https://dev.epicgames.com/documentation/unreal-engine/reimporting-assets-automatically-in-unreal-engine
- Epic asset import task: https://dev.epicgames.com/documentation/unreal-engine/API/Editor/UnrealEd/UAssetImportTask
- Epic recommendation to shut the editor before source-control sync of in-use files: https://dev.epicgames.com/documentation/unreal-engine/using-source-control-in-the-unreal-editor
- Optional Git source-control editor UI: https://github.com/getnamo/GitSourceControl-Unreal
- GitHub Unreal ignore template: https://github.com/github/gitignore/blob/main/UnrealEngine.gitignore

