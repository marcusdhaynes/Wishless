"""UE5-side declarative automation processor, called on the editor main thread."""
from __future__ import annotations
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import unreal

ROOT = Path(unreal.Paths.project_dir()).resolve()
SAVED = ROOT / "Saved" / "WishlessBridge"
QUEUE = ROOT / "Automation" / "Queue"
SOURCE = ROOT / "SourceAssets"
POLL_SECONDS = 3
_last_scan = 0.0
_tick_handle = None
sys.path.insert(0, str(ROOT / "tools"))
from bridge_schema import ManifestError, load_manifest

def _save_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)

def _apply_operation(op: dict) -> None:
    if op["type"] == "ensure_folder":
        unreal.EditorAssetLibrary.make_directory(op["path"])
        return
    if op["type"] == "scatter_grass":
        from wishless_grass import scatter_grass
        scatter_grass(op)
        return
    if op["type"] == "import_asset":
        source = (ROOT / op["source"]).resolve()
        if not source.is_relative_to(SOURCE.resolve()) or not source.is_file():
            raise ManifestError(f"missing/unsafe source: {op['source']}")
        task = unreal.AssetImportTask()
        task.filename = str(source)
        task.destination_path = op["destination"]
        if op.get("asset_name"):
            task.destination_name = op["asset_name"]
        task.automated = True
        task.replace_existing = True
        task.save = True
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        if not task.imported_object_paths:
            raise RuntimeError(f"Unreal returned no imported object: {op['source']}")
        unreal.log(f"[WishlessBridge] Imported {op['source']}")
        return
    raise ManifestError(f"unsupported operation type: {op['type']}")

def process_queue() -> None:
    SAVED.mkdir(parents=True, exist_ok=True)
    path = SAVED / "applied.json"
    try:
        applied = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(applied, dict):
            applied = {}
    except (OSError, json.JSONDecodeError):
        applied = {}
    for item in sorted(QUEUE.glob("*.json")):
        try:
            digest = hashlib.sha256(item.read_bytes()).hexdigest()
            # Grass is applied once per loaded map, not once per entire project.
            # Opening a different level can therefore apply the same declaration.
            manifest = load_manifest(item)
            has_grass = any(op["type"] == "scatter_grass" for op in manifest["operations"])
            world_name = unreal.EditorLevelLibrary.get_editor_world().get_path_name()
            applied_key = item.name + "::" + world_name if has_grass else item.name
            if applied.get(applied_key) == digest:
                continue
            for op in manifest["operations"]:
                _apply_operation(op)
            applied[applied_key] = digest
            _save_json(path, applied)
            unreal.log(f"[WishlessBridge] Applied: {manifest['id']}")
        except Exception as exc:
            unreal.log_error(f"[WishlessBridge] {item.name}: {exc}")

def _tick(delta_time: float) -> None:
    global _last_scan
    now = time.time()
    if now - _last_scan < POLL_SECONDS:
        return
    _last_scan = now
    try:
        _save_json(SAVED / "editor_alive.json", {"epoch": now})
        process_queue()
    except Exception as exc:
        unreal.log_error(f"[WishlessBridge] Polling failed: {exc}")

def start() -> None:
    global _tick_handle
    if _tick_handle is not None:
        return
    SAVED.mkdir(parents=True, exist_ok=True)
    _tick(0)
    _tick_handle = unreal.register_slate_post_tick_callback(_tick)
    unreal.log("[WishlessBridge] Active: monitoring automation queue and editor state")
