"""Tests for the declarative grass operation (no Unreal installation required)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from bridge_schema import ManifestError, validate_manifest


class GrassSchemaTests(unittest.TestCase):
    def manifest(self, **overrides):
        operation = {
            "type": "scatter_grass",
            "mesh": "/Game/WishlessGenerated/Vegetation/SM_WishlessGrass",
            "spacing_cm": 125,
            "max_instances": 30000,
            "seed": 20261115,
            "include_floor": True,
        }
        operation.update(overrides)
        return {"schema_version": 1, "id": "wishless-grass-test", "operations": [operation]}

    def test_accept_grass_operation(self):
        self.assertEqual(
            validate_manifest(self.manifest())["operations"][0]["type"],
            "scatter_grass")

    def test_accept_obj_mesh_import(self):
        validate_manifest({
            "schema_version": 1, "id": "wishless-grass-import",
            "operations": [{
                "type": "import_asset",
                "source": "SourceAssets/Vegetation/SM_WishlessGrass.obj",
                "destination": "/Game/WishlessGenerated/Vegetation",
                "asset_name": "SM_WishlessGrass",
            }],
        })

    def test_reject_unbounded_density(self):
        for bad in (0, 1, 60001, True, 1.4, -1):
            with self.subTest(value=bad), self.assertRaises(ManifestError):
                validate_manifest(self.manifest(max_instances=bad))

    def test_reject_unsafe_mesh_path(self):
        for path in ("/Game/Other/SM_Foo", "/Engine/BasicShapes/Cube",
                     "../../Grass", "C:/Grass"):
            with self.subTest(path=path), self.assertRaises(ManifestError):
                validate_manifest(self.manifest(mesh=path))

    def test_reject_invalid_options(self):
        for kw in ({"spacing_cm": 10}, {"spacing_cm": True},
                   {"seed": -1}, {"seed": 2**32},
                   {"include_floor": "true"}, {"command": "run"}):
            with self.subTest(options=kw), self.assertRaises(ManifestError):
                validate_manifest(self.manifest(**kw))


if __name__ == "__main__":
    unittest.main()
