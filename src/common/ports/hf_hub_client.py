"""Port: access to the Hugging Face Hub API for public datasets.

`repo_exists`/`list_repo_files`/`get_repo_file_bytes` are used at upload-time
to check repo/file existence and fetch small metadata files (e.g.
meta/info.json) without downloading the whole dataset. `download_dataset`
is the one exception — used by the worker (see `worker/dataset_fetcher.py`)
to actually pull the full dataset into its local LRU cache once a job for
it starts training.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class HFHubClient(ABC):
    @abstractmethod
    def repo_exists(self, repo_id: str) -> bool: ...

    @abstractmethod
    def list_repo_files(self, repo_id: str) -> list[str]: ...

    @abstractmethod
    def get_repo_file_bytes(self, repo_id: str, path_in_repo: str) -> bytes:
        """Raise FileNotFoundError if the file does not exist in the repo."""
        ...

    @abstractmethod
    def download_dataset(self, repo_id: str, target_dir: Path) -> None:
        """Download the full dataset repo into target_dir (which the caller
        is responsible for treating as a temp/staging path until this
        returns successfully)."""
        ...
