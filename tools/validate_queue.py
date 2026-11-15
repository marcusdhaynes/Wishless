"""Validate all source-asset declarations for the GitHub Actions workflow."""
from pathlib import Path
from bridge_schema import load_manifest

root = Path(__file__).resolve().parents[1]
queue = sorted((root / "Automation" / "Queue").glob("*.json"))
assert queue, "Queue must have at least one bootstrap operation"
ids = set()
for item in queue:
    manifest = load_manifest(item)
    if manifest["id"] in ids:
        raise ValueError(f"Duplicate manifest ID: {manifest['id']}")
    ids.add(manifest["id"])
    for op in manifest["operations"]:
        if op["type"] == "import_asset":
            source = (root / op["source"]).resolve()
            if not source.is_relative_to((root / "SourceAssets").resolve()) or not source.is_file():
                raise ValueError(f"Missing/unsafe source: {op['source']}")
    print(f"OK {item.relative_to(root)} [{len(manifest['operations'])} operations]")
print(f"Validated {len(queue)} manifest(s)")
