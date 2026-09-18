from __future__ import annotations

from common.ports.hf_hub_client import HFHubClient


class FakeHFHubClient(HFHubClient):
    """Test setup registers a repo's file listing + contents up front,
    mirroring what the real adapter would fetch from the HF Hub API."""

    def __init__(self) -> None:
        self._repo_files: dict[str, dict[str, bytes]] = {}

    def add_repo(self, repo_id: str, files: dict[str, bytes]) -> None:
        self._repo_files[repo_id] = files

    def repo_exists(self, repo_id: str) -> bool:
        return repo_id in self._repo_files

    def list_repo_files(self, repo_id: str) -> list[str]:
        if repo_id not in self._repo_files:
            raise FileNotFoundError(repo_id)
        return list(self._repo_files[repo_id].keys())

    def get_repo_file_bytes(self, repo_id: str, path_in_repo: str) -> bytes:
        files = self._repo_files.get(repo_id)
        if files is None or path_in_repo not in files:
            raise FileNotFoundError(f"{repo_id}:{path_in_repo}")
        return files[path_in_repo]
