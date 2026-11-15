"""Regression tests for UE5 grass traces (UE editor not required)."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from grass_hit import visible_ground_hit


class ProtectedHit:
    def __init__(self, blocking=True):
        self.actor = SimpleNamespace(get_path_name=lambda: "/Game/Terrain")
        self.fields = [
            blocking, False, 0.5, 500.0,
            SimpleNamespace(x=0, y=0, z=0),
            SimpleNamespace(x=123, y=456, z=789),
            SimpleNamespace(x=0, y=0, z=1),
            SimpleNamespace(x=0, y=0, z=1),
            None, self.actor, None, "None", "None", 0, 0, 0,
            SimpleNamespace(x=0, y=0, z=500),
            SimpleNamespace(x=0, y=0, z=-500),
        ]

    def get_editor_property(self, name):
        raise RuntimeError("HitResult property is protected")

    def to_tuple(self):
        return tuple(self.fields)


class GrassHitTests(unittest.TestCase):
    def test_exposes_protected_trace_fields_without_get_editor_property(self):
        hit = ProtectedHit()
        actor, normal, point = visible_ground_hit(hit)
        self.assertEqual(actor.get_path_name(), "/Game/Terrain")
        self.assertEqual(normal.z, 1)
        self.assertEqual((point.x, point.y, point.z), (123, 456, 789))

    def test_missed_hit_is_ignored(self):
        self.assertIsNone(visible_ground_hit(None))
        self.assertIsNone(visible_ground_hit(ProtectedHit(False)))

    def test_unexpected_layout_fails_closed(self):
        hit = ProtectedHit()
        hit.fields = ["bad"]
        with self.assertRaisesRegex(RuntimeError, "layout"):
            visible_ground_hit(hit)
        hit.fields = [None] + [0] * 20
        with self.assertRaisesRegex(RuntimeError, "blocking_hit"):
            visible_ground_hit(hit)


if __name__ == "__main__":
    unittest.main()
