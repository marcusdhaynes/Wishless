import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from wishless_sync import editor_active, live_safe, sync_once, git as real_git, origin_is_wishless

def run(*cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=True).stdout.strip()

class GitSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.remote = root / "remote.git"
        self.work = root / "work"
        self.author = root / "author"
        run("git", "init", "--bare", "--initial-branch=main", str(self.remote))
        run("git", "clone", str(self.remote), str(self.author))
        run("git", "config", "user.name", "Unit Test", cwd=self.author)
        run("git", "config", "user.email", "unit@test.invalid", cwd=self.author)
        (self.author / "README.md").write_text("first\n")
        (self.author / ".gitignore").write_text("Saved/\n.wishless/\n")
        run("git", "add", ".", cwd=self.author)
        run("git", "commit", "-m", "initial", cwd=self.author)
        run("git", "push", "origin", "main", cwd=self.author)
        run("git", "clone", str(self.remote), str(self.work))
        run("git", "config", "user.name", "Unit Test", cwd=self.work)
        run("git", "config", "user.email", "unit@test.invalid", cwd=self.work)

    def add_remote_commit(self, path, content):
        dest = self.author / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
        run("git", "add", ".", cwd=self.author)
        run("git", "commit", "-m", path, cwd=self.author)
        run("git", "push", "origin", "main", cwd=self.author)

    def sync(self):
        def fake_git(root, *args, **kw):
            if args[:3] == ("remote", "get-url", "origin"):
                return "https://github.com/marcusdhaynes/Wishless.git"
            if args[:1] == ("lfs",):
                return ""
            return real_git(root, *args, **kw)
        with patch("wishless_sync.git", side_effect=fake_git):
            return sync_once(self.work)

    def test_fast_forward(self):
        self.add_remote_commit("Docs/test.md", "abc")
        self.assertEqual(self.sync()["state"], "updated")
        self.assertEqual((self.work / "Docs/test.md").read_text(), "abc")

    def test_dirty_worktree_blocks(self):
        self.add_remote_commit("Docs/test.md", "abc")
        (self.work / "local.txt").write_text("unsaved")
        self.assertEqual(self.sync()["state"], "blocked_local_changes")
        self.assertFalse((self.work / "Docs/test.md").exists())
        self.assertTrue((self.work / "local.txt").exists())

    def test_editor_defers_native_files(self):
        self.add_remote_commit("Config/DefaultEngine.ini", "[Test]")
        marker = self.work / "Saved/WishlessBridge/editor_alive.json"
        marker.parent.mkdir(parents=True)
        marker.write_text(json.dumps({"epoch": time.time()}))
        self.assertEqual(self.sync()["state"], "pending_editor_restart")
        self.assertFalse((self.work / "Config/DefaultEngine.ini").exists())
        marker.unlink()
        self.assertEqual(self.sync()["state"], "updated")

    def test_editor_accepts_queue(self):
        self.add_remote_commit("Automation/Queue/0002.json", "{}")
        marker = self.work / "Saved/WishlessBridge/editor_alive.json"
        marker.parent.mkdir(parents=True)
        marker.write_text(json.dumps({"epoch": time.time()}))
        self.assertEqual(self.sync()["state"], "updated")

    def test_diverged_without_reset(self):
        self.add_remote_commit("Docs/remote.md", "remote")
        (self.work / "local.md").write_text("local")
        run("git", "add", ".", cwd=self.work)
        run("git", "commit", "-m", "local", cwd=self.work)
        self.assertEqual(self.sync()["state"], "diverged")
        self.assertTrue((self.work / "local.md").is_file())

    def test_old_heartbeat(self):
        marker = self.work / "Saved/WishlessBridge/editor_alive.json"
        marker.parent.mkdir(parents=True)
        marker.write_text(json.dumps({"epoch": time.time() - 1000}))
        self.assertFalse(editor_active(self.work))

    def test_path_allowlist(self):
        self.assertTrue(live_safe("SourceAssets/a.png"))
        self.assertTrue(live_safe("Automation/Queue/0002.json"))
        self.assertFalse(live_safe("Content/Foo.uasset"))
        self.assertFalse(live_safe("Source/Foo.cpp"))

    def test_origin_guard(self):
        self.assertTrue(origin_is_wishless("https://github.com/marcusdhaynes/Wishless.git"))
        self.assertTrue(origin_is_wishless("git@github.com:marcusdhaynes/Wishless.git"))
        self.assertFalse(origin_is_wishless("https://evil.com/a/github.com/marcusdhaynes/Wishless.git"))

if __name__ == "__main__":
    unittest.main()
