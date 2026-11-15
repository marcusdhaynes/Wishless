"""Strict schema for versioned, declarative UE editor operations."""
from __future__ import annotations
import json
import re
from pathlib import Path, PurePosixPath

MAX_MANIFEST_BYTES = 256_000
MAX_OPERATIONS = 100
ALLOWED_IMPORT_EXTS = {".obj", ".fbx", ".png", ".jpg", ".jpeg", ".tga", ".wav", ".mp3", ".ogg", ".glb", ".gltf"}
SAFE_GAME_PATH = re.compile(r"^/Game/WishlessGenerated(?:/[A-Za-z0-9_]+)*$")
SAFE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,79}$")
SAFE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,99}$")

class ManifestError(ValueError):
    pass

def _check_keys(obj: dict, required: set[str], optional: set[str] | None = None) -> None:
    if not isinstance(obj, dict):
        raise ManifestError("expected an object")
    optional = optional or set()
    if not required.issubset(obj) or set(obj) - (required | optional):
        raise ManifestError(f"invalid fields: required={sorted(required)}, allowed={sorted(required | optional)}")

def _destination(value: object) -> str:
    if not isinstance(value, str) or not SAFE_GAME_PATH.fullmatch(value):
        raise ManifestError("destination must be /Game/WishlessGenerated[/Safe_Folder]")
    return value

def _source(value: object) -> str:
    if not isinstance(value, str) or "\\" in value or "\x00" in value:
        raise ManifestError("source must be a normalized relative SourceAssets path")
    p = PurePosixPath(value)
    if (p.is_absolute() or len(p.parts) < 2 or p.parts[0] != "SourceAssets"
        or any(part in {".", ".."} for part in value.split("/"))
        or ":" in value or p.suffix.lower() not in ALLOWED_IMPORT_EXTS):
        raise ManifestError(f"unsupported or unsafe source: {value}")
    return value

def validate_manifest(data: object) -> dict:
    _check_keys(data, {"schema_version", "id", "operations"}, {"description"})
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ManifestError("schema_version must be 1")
    if not isinstance(data["id"], str) or not SAFE_ID.fullmatch(data["id"]):
        raise ManifestError("invalid id")
    if "description" in data and (not isinstance(data["description"], str) or len(data["description"]) > 500):
        raise ManifestError("description must be at most 500 characters")
    ops = data["operations"]
    if not isinstance(ops, list) or not 1 <= len(ops) <= MAX_OPERATIONS:
        raise ManifestError("operations must contain 1..100 entries")
    for op in ops:
        if not isinstance(op, dict) or "type" not in op:
            raise ManifestError("each operation must have a type")
        if op["type"] == "ensure_folder":
            _check_keys(op, {"type", "path"})
            _destination(op["path"])
        elif op["type"] == "import_asset":
            _check_keys(op, {"type", "source", "destination"}, {"asset_name"})
            _source(op["source"])
            _destination(op["destination"])
            if "asset_name" in op and (not isinstance(op["asset_name"], str)
                or not SAFE_NAME.fullmatch(op["asset_name"])):
                raise ManifestError("invalid asset_name")
        elif op["type"] == "scatter_grass":
            _check_keys(op, {"type", "mesh"}, {"spacing_cm", "max_instances", "seed", "include_floor"})
            if op["mesh"] != "/Game/WishlessGenerated/Vegetation/SM_WishlessGrass":
                raise ManifestError("scatter_grass accepts only the Wishless generated grass mesh")
            if "spacing_cm" in op and (type(op["spacing_cm"]) not in (int, float)
                or not 70 <= op["spacing_cm"] <= 500):
                raise ManifestError("spacing_cm must be 70..500 cm")
            if "max_instances" in op and (type(op["max_instances"]) is not int
                or not 100 <= op["max_instances"] <= 60000):
                raise ManifestError("max_instances must be 100..60000")
            if "seed" in op and (type(op["seed"]) is not int
                or not 0 <= op["seed"] <= 2147483647):
                raise ManifestError("seed must be a nonnegative 32-bit integer")
            if "include_floor" in op and type(op["include_floor"]) is not bool:
                raise ManifestError("include_floor must be boolean")
        elif op["type"] == "dense_grass":
            _check_keys(op, {"type", "mesh"}, {"spacing_cm", "max_instances", "seed"})
            if op["mesh"] != "/Game/WishlessGenerated/Vegetation/SM_WishlessGrassCarpet":
                raise ManifestError("dense_grass only accepts Wishless's generated carpet")
            if "spacing_cm" in op and (
                    type(op["spacing_cm"]) not in (int, float)
                    or not 120 <= op["spacing_cm"] <= 225):
                raise ManifestError("dense grass spacing must be 120..225 cm")
            if "max_instances" in op and (
                    type(op["max_instances"]) is not int
                    or not 100 <= op["max_instances"] <= 180000):
                raise ManifestError("dense grass count must be 100..180000")
            if "seed" in op and (
                    type(op["seed"]) is not int or not 0 <= op["seed"] <= 2147483647):
                raise ManifestError("invalid dense grass seed")
        else:
            raise ManifestError(f"unsupported operation type: {op['type']!r}")
    return data

def load_manifest(path: Path) -> dict:
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ManifestError("manifest too large")
    return validate_manifest(json.loads(path.read_text(encoding="utf-8")))
