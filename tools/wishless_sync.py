#!/usr/bin/env python3
"""Conflict-safe one-way GitHub -> local Unreal project sync. No forced reset."""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_INTERVAL = 15
EDITOR_TIMEOUT_SECONDS = 90

class SyncError(RuntimeError):
    pass

def git(root: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", "-C", str(root), *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        encoding="utf-8", errors="replace", timeout=90)
    if check and proc.returncode:
        raise SyncError(f"git {' '.join(args[:3])} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()

def origin_is_wishless(url: str) -> bool:
    target = "marcusdhaynes/wishless"
    if url.startswith("git@github.com:"):
        return url.split(":", 1)[1].removesuffix(".git").strip("/").lower() == target
    parsed = urlparse(url)
    return parsed.scheme in ("https", "ssh") and parsed.hostname == "github.com" and parsed.path.strip("/").removesuffix(".git").lower() == target

def editor_active(root: Path, now: float | None = None) -> bool:
    path = root / "Saved" / "WishlessBridge" / "editor_alive.json"
    try:
        timestamp = json.loads(path.read_text(encoding="utf-8"))["epoch"]
        age = (time.time() if now is None else now) - float(timestamp)
        return -5 <= age < EDITOR_TIMEOUT_SECONDS
    except (OSError, KeyError, ValueError, TypeError):
        return False

def live_safe(path: str) -> bool:
    return path.startswith(("Automation/Queue/", "SourceAssets/", "Docs/")) or path == "README.md"

def status_file(root: Path, outcome: dict) -> dict:
    dest = root / ".wishless" / "status.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    info = {"checked_at": datetime.now(timezone.utc).isoformat(), **outcome}
    temp = dest.with_suffix(".tmp")
    temp.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, dest)
    return info

def sync_once(root: Path, *, fetch: bool = True) -> dict:
    root = root.resolve()
    actual = Path(git(root, "rev-parse", "--show-toplevel")).resolve()
    if actual != root:
        raise SyncError("project must be at the Wishless Git checkout root")
    remote_url = git(root, "remote", "get-url", "origin")
    if not origin_is_wishless(remote_url):
        raise SyncError(f"origin is not the Wishless repository: {remote_url}")
    branch = git(root, "branch", "--show-current")
    if branch != "main":
        raise SyncError(f"expected single main branch; got {branch!r}")
    if fetch:
        git(root, "fetch", "--quiet", "origin", "main")
    remote = git(root, "rev-parse", "refs/remotes/origin/main")
    head = git(root, "rev-parse", "HEAD")
    if remote == head:
        return status_file(root, {"state": "up_to_date", "head": head, "changed_files": []})
    base = git(root, "merge-base", "HEAD", "refs/remotes/origin/main", check=False)
    if base != head:
        return status_file(root, {"state": "diverged", "reason": "Manual reconciliation required; no reset performed", "head": head})
    changes = git(root, "diff", "--name-only", "--diff-filter=ACDMRT", "HEAD", "refs/remotes/origin/main").splitlines()
    if git(root, "status", "--porcelain", "--untracked-files=normal"):
        return status_file(root, {"state": "blocked_local_changes", "reason": "Commit/stash local changes; no overwrite performed", "head": head, "changed_files": changes})
    if editor_active(root) and not all(live_safe(p) for p in changes):
        return status_file(root, {"state": "pending_editor_restart", "reason": "Loaded UE assets/code/settings require editor restart", "head": head, "changed_files": changes})
    git(root, "merge", "--ff-only", "--no-edit", "refs/remotes/origin/main")
    try:
        git(root, "lfs", "pull", "origin", "main")
    except SyncError as exc:
        return status_file(root, {"state": "lfs_error", "reason": str(exc), "head": git(root, "rev-parse", "HEAD"), "changed_files": changes})
    return status_file(root, {"state": "updated", "head": git(root, "rev-parse", "HEAD"), "changed_files": changes})

def main() -> int:
    parser = argparse.ArgumentParser(description="Safe Wishless GitHub -> UE5 synchronizer")
    parser.add_argument("mode", choices=("once", "watch", "status"), nargs="?", default="once")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL)
    args = parser.parse_args()
    if args.interval < 5:
        parser.error("--interval must be >= 5")
    while True:
        try:
            if args.mode == "status":
                status = args.root / ".wishless" / "status.json"
                result = json.loads(status.read_text(encoding="utf-8")) if status.is_file() else {"state": "never_checked"}
            else:
                result = sync_once(args.root)
            print(json.dumps(result, indent=2), flush=True)
            if args.mode != "watch":
                return 0 if result.get("state") in ("up_to_date", "updated") else 2
        except (SyncError, OSError, subprocess.TimeoutExpired) as exc:
            print(f"Wishless Sync ERROR: {exc}", file=sys.stderr, flush=True)
            if args.mode != "watch":
                return 1
        time.sleep(args.interval)

if __name__ == "__main__":
    raise SystemExit(main())
