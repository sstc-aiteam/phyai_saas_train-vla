"""Real Hugging Face Hub client: checks a public dataset repo's structure
via the Hub API without downloading the dataset (spec section 3), and
downloads the full dataset on demand for the worker (spec section 5)."""

from __future__ import annotations

from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download, snapshot_download
from huggingface_hub.utils import EntryNotFoundError, RepositoryNotFoundError

from common.ports.hf_hub_client import HFHubClient


class RealHFHubClient(HFHubClient):
    def __init__(self, api: HfApi | None = None) -> None:
        self._api = api or HfApi()

    def repo_exists(self, repo_id: str) -> bool:
        return self._api.repo_exists(repo_id, repo_type="dataset")

    def list_repo_files(self, repo_id: str) -> list[str]:
        try:
            return list(self._api.list_repo_files(repo_id, repo_type="dataset"))
        except RepositoryNotFoundError as exc:
            raise FileNotFoundError(repo_id) from exc

    def get_repo_file_bytes(self, repo_id: str, path_in_repo: str) -> bytes:
        try:
            local_path = hf_hub_download(repo_id=repo_id, repo_type="dataset", filename=path_in_repo)
        except (EntryNotFoundError, RepositoryNotFoundError) as exc:
            raise FileNotFoundError(f"{repo_id}:{path_in_repo}") from exc
        with open(local_path, "rb") as f:
            return f.read()

    def download_dataset(self, repo_id: str, target_dir: Path) -> None:
        try:
            snapshot_download(repo_id=repo_id, repo_type="dataset", local_dir=str(target_dir))
        except RepositoryNotFoundError as exc:
            raise FileNotFoundError(repo_id) from exc
