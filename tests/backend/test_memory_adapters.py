from pathlib import Path

import pytest

from backend.adapters.memory import InMemoryHFHubClient, InMemoryObjectStorage


def test_object_storage_upload_url_points_at_dev_storage_route():
    storage = InMemoryObjectStorage(base_url="http://localhost:9999")
    url = storage.generate_upload_url("uploads/u1/a.zip", "application/zip", 900)
    assert url == "http://localhost:9999/dev-storage/uploads/u1/a.zip"


def test_object_storage_download_url_points_at_dev_storage_route():
    storage = InMemoryObjectStorage(base_url="http://localhost:9999")
    url = storage.generate_download_url("checkpoints/job-1.zip", 3600)
    assert url == "http://localhost:9999/dev-storage/checkpoints/job-1.zip"


def test_object_storage_base_url_trailing_slash_is_stripped():
    storage = InMemoryObjectStorage(base_url="http://localhost:9999/")
    url = storage.generate_upload_url("uploads/u1/a.zip", "application/zip", 900)
    assert url == "http://localhost:9999/dev-storage/uploads/u1/a.zip"


def test_object_storage_put_bytes_then_read_and_exists():
    storage = InMemoryObjectStorage()
    storage.put_bytes("uploads/u1/a.zip", b"hello")

    assert storage.exists("uploads/u1/a.zip") is True
    with storage.open_read_stream("uploads/u1/a.zip") as stream:
        assert stream.read() == b"hello"


def test_object_storage_delete_removes_object():
    storage = InMemoryObjectStorage()
    storage.put_bytes("uploads/u1/a.zip", b"hello")
    storage.delete("uploads/u1/a.zip")
    assert storage.exists("uploads/u1/a.zip") is False


def test_hf_hub_client_repo_lifecycle():
    client = InMemoryHFHubClient()
    assert client.repo_exists("demo/dataset") is False

    client.add_repo("demo/dataset", {"meta/info.json": b"{}", "data/x.parquet": b"x"})

    assert client.repo_exists("demo/dataset") is True
    assert set(client.list_repo_files("demo/dataset")) == {"meta/info.json", "data/x.parquet"}
    assert client.get_repo_file_bytes("demo/dataset", "meta/info.json") == b"{}"


def test_hf_hub_client_unknown_repo_raises():
    client = InMemoryHFHubClient()
    with pytest.raises(FileNotFoundError):
        client.list_repo_files("does/not-exist")


def test_hf_hub_client_download_dataset_writes_files(tmp_path: Path):
    client = InMemoryHFHubClient()
    client.add_repo("demo/dataset", {"meta/info.json": b"{}", "data/chunk/x.parquet": b"x"})

    client.download_dataset("demo/dataset", tmp_path)

    assert (tmp_path / "meta" / "info.json").read_bytes() == b"{}"
    assert (tmp_path / "data" / "chunk" / "x.parquet").read_bytes() == b"x"


def test_hf_hub_client_download_dataset_unknown_repo_raises(tmp_path: Path):
    client = InMemoryHFHubClient()
    with pytest.raises(FileNotFoundError):
        client.download_dataset("does/not-exist", tmp_path)
