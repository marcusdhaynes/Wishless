import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from bridge_schema import ManifestError, load_manifest, validate_manifest

class SchemaTests(unittest.TestCase):
    def base(self, op):
        return {"schema_version": 1, "id": "test-0001", "operations": [op]}
    def test_valid_folder(self):
        validate_manifest(self.base({"type": "ensure_folder", "path": "/Game/WishlessGenerated/Props"}))
    def test_valid_import(self):
        validate_manifest(self.base({"type": "import_asset", "source": "SourceAssets/Props/a.fbx", "destination": "/Game/WishlessGenerated/Props", "asset_name": "SM_A"}))
    def test_reject_traversal(self):
        for path in ("SourceAssets/../secret.png", "SourceAssets/../../x.fbx", "C:/secret.fbx", "SourceAssets\\bad.png"):
            with self.subTest(path=path), self.assertRaises(ManifestError):
                validate_manifest(self.base({"type": "import_asset", "source": path, "destination": "/Game/WishlessGenerated"}))
    def test_reject_arbitrary_execution(self):
        with self.assertRaises(ManifestError):
            validate_manifest(self.base({"type": "exec", "command": "calc.exe"}))
    def test_reject_target_overwrite(self):
        with self.assertRaises(ManifestError):
            validate_manifest(self.base({"type": "ensure_folder", "path": "/Game/Characters"}))
    def test_reject_extra_key(self):
        with self.assertRaises(ManifestError):
            validate_manifest(self.base({"type": "ensure_folder", "path": "/Game/WishlessGenerated", "bad": 1}))
    def test_reject_invalid_schema(self):
        with self.assertRaises(ManifestError):
            validate_manifest({"schema_version": True, "id": "test-0001", "operations": [{"type": "ensure_folder", "path": "/Game/WishlessGenerated"}]})
    def test_max_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "oversize.json"
            path.write_text("x" * 256001)
            with self.assertRaises(ManifestError):
                load_manifest(path)

if __name__ == "__main__":
    unittest.main()
