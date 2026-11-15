"""Coverage and memory regressions for Wishless grass carpet V2."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from bridge_schema import ManifestError, validate_manifest
from grass_layout import plan_grid, plan_level


class DenseGrassTests(unittest.TestCase):
    def test_completely_tile_one_hectare_without_sparse_sampling(self):
        spacing, grids = plan_level([(10000, 10000)])
        self.assertEqual(spacing, 185)
        self.assertEqual(grids[0].nx, 55)
        self.assertEqual(grids[0].ny, 55)
        self.assertLessEqual(grids[0].step_x, 185)
        self.assertLessEqual(grids[0].step_y, 185)
        self.assertEqual(grids[0].count, 3025)

    def test_thin_surface_has_full_width_coverage(self):
        p = plan_grid(125, 4250, 185)
        self.assertEqual(p.nx, 1)
        self.assertEqual(p.ny, 23)
        self.assertLessEqual(p.step_y, 185)

    def test_adaptive_budget_does_not_leave_sparse_gaps(self):
        spacing, grids = plan_level([(10000, 10000)], budget=2200)
        self.assertGreater(spacing, 185)
        self.assertLessEqual(spacing, 225)
        self.assertLessEqual(grids[0].count, 2200)

    def test_oversized_world_is_rejected_not_half_filled(self):
        with self.assertRaisesRegex(ValueError, "Landscape Grass Output"):
            plan_level([(300000, 300000)], budget=110000)

    def test_level_budget_counts_all_surfaces(self):
        with self.assertRaisesRegex(ValueError, "Landscape Grass Output"):
            plan_level([(100000, 100000)] * 5, budget=1000)

    def test_invalid_spacing_and_budget(self):
        for size in (0, 119, 226):
            with self.subTest(size=size), self.assertRaises(ValueError):
                plan_grid(100, 100, size)
        for n in (True, -1, 1_000_000):
            with self.subTest(n=n), self.assertRaises((ValueError, TypeError)):
                if isinstance(n, bool):
                    raise ValueError("bool is not a meaningful budget")
                plan_level([(1200, 1200)], budget=n)

    def test_valid_dense_manifest(self):
        data = {
            "schema_version": 1,
            "id": "dense-grass-regression",
            "operations": [{
                "type": "dense_grass",
                "mesh": "/Game/WishlessGenerated/Vegetation/SM_WishlessGrassCarpet",
                "spacing_cm": 185,
                "max_instances": 110000,
                "seed": 20261115,
            }],
        }
        validate_manifest(data)
        for key, value in (("spacing_cm", 400), ("max_instances", 180001),
                           ("max_instances", True), ("seed", -20),
                           ("mesh", "/Game/Other/Grass")):
            copy = {"schema_version": data["schema_version"], "id": data["id"],
                    "operations": [{**data["operations"][0], key: value}]}
            with self.subTest(key=key, value=value), self.assertRaises(ManifestError):
                validate_manifest(copy)

    def test_dense_mesh_is_compact_root_anchored_and_two_sided_by_material(self):
        root = Path(__file__).resolve().parents[1]
        mesh = (root / "SourceAssets/Vegetation/SM_WishlessGrassCarpet.obj").read_text()
        tris = [line for line in mesh.splitlines() if line.startswith("f ")]
        vertices = [line for line in mesh.splitlines() if line.startswith("v ")]
        self.assertEqual(len(tris), 96)
        self.assertEqual(len(vertices), 288)
        self.assertIn("vt 0 0", mesh)
        self.assertIn("vt 0.5 1", mesh)
        self.assertLess(len(mesh), 12000)
        self.assertEqual(len({x.split()[0] for x in tris}), 1)


if __name__ == "__main__":
    unittest.main()
