"""Makes a job's training data available on local disk before its
container starts (spec sections 3 and 5).

- `hf_hub` jobs: the dataset is downloaded into the shared, LRU-evicted
  cache (see `disk_manager.py` for the `<repo_id>.tmp/` -> final-path
  convention) and reused by any later job training on the same repo.
- `zip_upload` jobs: the already-validated zip is downloaded from GCS and
  extracted straight into that job's own (uncached, per-job) input dir —
  spec section 5 says this gets deleted when the job ends either way. The
  GCS object itself is deleted right after a successful extraction (it's
  now fully consumed), which also keeps it well clear of the 1-day
  orphaned-upload bucket lifecycle rule even if a job sat queued for a
  while first.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from common.models import Job, SourceType
from common.ports.hf_hub_client import HFHubClient
from common.ports.object_storage import ObjectStorage

from worker.disk_manager import (
    evict_lru_until_under_cap,
    final_path_for,
    finalize_download,
    tmp_path_for,
)


@dataclass(frozen=True)
class FetchedDataset:
    input_dir: Path
    read_only: bool  # True for the shared HF cache; False for a job's own zip extraction


class DatasetFetchError(Exception):
    pass


class DatasetFetcher:
    def __init__(self, hf_hub_client: HFHubClient, storage: ObjectStorage, cache_dir: str, cache_max_bytes: int) -> None:
        self._hf_hub = hf_hub_client
        self._storage = storage
        self._cache_dir = Path(cache_dir)
        self._cache_max_bytes = cache_max_bytes

    def fetch_for_job(self, job: Job, job_dir: Path) -> FetchedDataset:
        if job.source_type == SourceType.HF_HUB:
            return FetchedDataset(input_dir=self._fetch_hf_dataset(job.source_ref), read_only=True)
        if job.source_type == SourceType.ZIP_UPLOAD:
            return FetchedDataset(
                input_dir=self._extract_zip_upload(job.source_ref, job_dir / "input"), read_only=False
            )
        raise DatasetFetchError(f"Unknown source type: {job.source_type}")

    def _fetch_hf_dataset(self, repo_id: str) -> Path:
        final_dir = final_path_for(self._cache_dir, repo_id)
        if final_dir.exists():
            final_dir.touch()  # bump mtime so the LRU evictor sees it as recently used
            return final_dir

        self._cache_dir.mkdir(parents=True, exist_ok=True)
        tmp_dir = tmp_path_for(self._cache_dir, repo_id)
        try:
            self._hf_hub.download_dataset(repo_id, tmp_dir)
        except FileNotFoundError as exc:
            raise DatasetFetchError(f"HF Hub dataset not found: {repo_id}") from exc

        finalize_download(tmp_dir, final_dir)
        evict_lru_until_under_cap(self._cache_dir, self._cache_max_bytes)
        return final_dir

    def _extract_zip_upload(self, object_path: str, target_dir: Path) -> Path:
        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            with self._storage.open_read_stream(object_path) as stream:
                with zipfile.ZipFile(stream) as zf:
                    zf.extractall(target_dir)
        except (FileNotFoundError, zipfile.BadZipFile) as exc:
            raise DatasetFetchError(f"Failed to extract uploaded dataset {object_path}: {exc}") from exc

        try:
            self._storage.delete(object_path)
        except Exception:
            pass  # best-effort: the bucket lifecycle rule is the backstop

        return target_dir
