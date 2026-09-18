"""Local disk management on the GPU worker host (spec section 5):

- HF Hub dataset cache: kept, LRU-evicted once it exceeds a total size cap.
  Downloads land in `<repo_id>.tmp/` first and are atomically renamed into
  place only once complete, so a crash mid-download never leaves a
  half-written cache entry that looks valid.
- Stale `.tmp` download directories older than a threshold are swept on
  worker startup.
- Uploaded zip contents and checkpoints are the caller's responsibility to
  delete (job_poller.py) — this module only manages the shared HF cache dir.
"""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

TMP_SUFFIX = ".tmp"


@dataclass(frozen=True)
class CacheEntry:
    path: Path
    size_bytes: int
    mtime: float


def directory_size_bytes(path: Path) -> int:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for filename in filenames:
            file_path = Path(dirpath) / filename
            if file_path.is_file():
                total += file_path.stat().st_size
    return total


def list_cache_entries(cache_dir: Path) -> list[CacheEntry]:
    if not cache_dir.exists():
        return []
    entries = []
    for child in cache_dir.iterdir():
        if not child.is_dir() or child.name.endswith(TMP_SUFFIX):
            continue
        entries.append(CacheEntry(path=child, size_bytes=directory_size_bytes(child), mtime=child.stat().st_mtime))
    return entries


def evict_lru_until_under_cap(cache_dir: Path, max_bytes: int) -> list[Path]:
    """Delete least-recently-used cache entries until total size <= max_bytes.
    Returns the list of removed directory paths, oldest first."""
    entries = sorted(list_cache_entries(cache_dir), key=lambda e: e.mtime)
    total = sum(e.size_bytes for e in entries)

    removed: list[Path] = []
    for entry in entries:
        if total <= max_bytes:
            break
        shutil.rmtree(entry.path, ignore_errors=True)
        total -= entry.size_bytes
        removed.append(entry.path)

    return removed


def cleanup_stale_tmp_dirs(cache_dir: Path, older_than_seconds: int, now: float | None = None) -> list[Path]:
    """Remove `*.tmp` directories left behind by an interrupted download,
    called once when the worker starts up."""
    if not cache_dir.exists():
        return []
    now = time.time() if now is None else now

    removed: list[Path] = []
    for child in cache_dir.iterdir():
        if not child.is_dir() or not child.name.endswith(TMP_SUFFIX):
            continue
        age = now - child.stat().st_mtime
        if age > older_than_seconds:
            shutil.rmtree(child, ignore_errors=True)
            removed.append(child)

    return removed


def tmp_path_for(cache_dir: Path, repo_id: str) -> Path:
    safe_name = repo_id.replace("/", "__")
    return cache_dir / f"{safe_name}{TMP_SUFFIX}"


def final_path_for(cache_dir: Path, repo_id: str) -> Path:
    safe_name = repo_id.replace("/", "__")
    return cache_dir / safe_name


def finalize_download(tmp_dir: Path, final_dir: Path) -> None:
    """Atomically publish a completed download by renaming its temp dir into
    place. Must be same filesystem (both under the same cache_dir)."""
    os.replace(tmp_dir, final_dir)
