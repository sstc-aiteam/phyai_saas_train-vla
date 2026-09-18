"""Port: read-only access to the Hugging Face Hub API for public datasets.

Only used to check repo/file existence and fetch small metadata files
(e.g. meta/info.json) without downloading the whole dataset.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class HFHubClient(ABC):
    @abstractmethod
    def repo_exists(self, repo_id: str) -> bool: ...

    @abstractmethod
    def list_repo_files(self, repo_id: str) -> list[str]: ...

    @abstractmethod
    def get_repo_file_bytes(self, repo_id: str, path_in_repo: str) -> bytes:
        """Raise FileNotFoundError if the file does not exist in the repo."""
        ...
