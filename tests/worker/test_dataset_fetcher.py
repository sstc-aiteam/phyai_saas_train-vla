import io
import zipfile

import pytest

from common.models import Job, PolicyType, SourceType
from worker.dataset_fetcher import DatasetFetchError, DatasetFetcher

from tests.backend.fakes.fake_hf_hub_client import FakeHFHubClient
from tests.backend.fakes.fake_object_storage import FakeObjectStorage


def make_job(source_type, source_ref, job_id="job-1") -> Job:
    return Job(
        id=job_id,
        user_id="user-1",
        policy=PolicyType.ACT,
        source_type=source_type,
        source_ref=source_ref,
        training_steps=1000,
    )


def make_zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


@pytest.fixture
def hf_hub():
    return FakeHFHubClient()


@pytest.fixture
def storage():
    return FakeObjectStorage()


def make_fetcher(hf_hub, storage, tmp_path, cache_max_bytes=20 * 1024**3):
    return DatasetFetcher(hf_hub, storage, cache_dir=str(tmp_path / "cache"), cache_max_bytes=cache_max_bytes)


def test_fetches_hf_dataset_into_cache(hf_hub, storage, tmp_path):
    hf_hub.add_repo("org/dataset", {"meta/info.json": b"{}", "data/x.parquet": b"x"})
    job = make_job(SourceType.HF_HUB, "org/dataset")
    fetcher = make_fetcher(hf_hub, storage, tmp_path)

    result = fetcher.fetch_for_job(job, tmp_path / "jobs" / "job-1")

    assert result.read_only is True
    assert (result.input_dir / "meta" / "info.json").read_bytes() == b"{}"
    assert hf_hub.download_calls == ["org/dataset"]


def test_reuses_cached_hf_dataset_without_redownloading(hf_hub, storage, tmp_path):
    hf_hub.add_repo("org/dataset", {"meta/info.json": b"{}"})
    job = make_job(SourceType.HF_HUB, "org/dataset")
    fetcher = make_fetcher(hf_hub, storage, tmp_path)

    fetcher.fetch_for_job(job, tmp_path / "jobs" / "job-1")
    fetcher.fetch_for_job(job, tmp_path / "jobs" / "job-2")

    assert hf_hub.download_calls == ["org/dataset"]  # only downloaded once


def test_hf_dataset_not_found_raises_fetch_error(hf_hub, storage, tmp_path):
    job = make_job(SourceType.HF_HUB, "org/missing")
    fetcher = make_fetcher(hf_hub, storage, tmp_path)

    with pytest.raises(DatasetFetchError):
        fetcher.fetch_for_job(job, tmp_path / "jobs" / "job-1")


def test_hf_dataset_no_leftover_tmp_dir_after_success(hf_hub, storage, tmp_path):
    hf_hub.add_repo("org/dataset", {"meta/info.json": b"{}"})
    job = make_job(SourceType.HF_HUB, "org/dataset")
    fetcher = make_fetcher(hf_hub, storage, tmp_path)

    fetcher.fetch_for_job(job, tmp_path / "jobs" / "job-1")

    cache_dir = tmp_path / "cache"
    tmp_dirs = [p for p in cache_dir.iterdir() if p.name.endswith(".tmp")]
    assert tmp_dirs == []


def test_extracts_zip_upload_into_job_input_dir(hf_hub, storage, tmp_path):
    object_path = "uploads/user-1/upload-1.zip"
    storage.put_bytes(object_path, make_zip_bytes({"meta/info.json": b"{}", "data/x.parquet": b"x"}))
    job = make_job(SourceType.ZIP_UPLOAD, object_path)
    fetcher = make_fetcher(hf_hub, storage, tmp_path)

    result = fetcher.fetch_for_job(job, tmp_path / "jobs" / "job-1")

    assert result.read_only is False
    assert result.input_dir == tmp_path / "jobs" / "job-1" / "input"
    assert (result.input_dir / "meta" / "info.json").read_bytes() == b"{}"


def test_extracted_zip_upload_object_is_deleted_from_storage(hf_hub, storage, tmp_path):
    object_path = "uploads/user-1/upload-1.zip"
    storage.put_bytes(object_path, make_zip_bytes({"meta/info.json": b"{}"}))
    job = make_job(SourceType.ZIP_UPLOAD, object_path)
    fetcher = make_fetcher(hf_hub, storage, tmp_path)

    fetcher.fetch_for_job(job, tmp_path / "jobs" / "job-1")

    assert not storage.exists(object_path)


def test_zip_upload_delete_failure_does_not_fail_the_fetch(hf_hub, storage, tmp_path, monkeypatch):
    object_path = "uploads/user-1/upload-1.zip"
    storage.put_bytes(object_path, make_zip_bytes({"meta/info.json": b"{}"}))
    job = make_job(SourceType.ZIP_UPLOAD, object_path)
    fetcher = make_fetcher(hf_hub, storage, tmp_path)

    def boom(_object_path):
        raise ConnectionError("simulated GCS delete failure")

    monkeypatch.setattr(storage, "delete", boom)

    result = fetcher.fetch_for_job(job, tmp_path / "jobs" / "job-1")

    assert (result.input_dir / "meta" / "info.json").exists()


def test_zip_upload_missing_object_raises_fetch_error(hf_hub, storage, tmp_path):
    job = make_job(SourceType.ZIP_UPLOAD, "uploads/user-1/does-not-exist.zip")
    fetcher = make_fetcher(hf_hub, storage, tmp_path)

    with pytest.raises(DatasetFetchError):
        fetcher.fetch_for_job(job, tmp_path / "jobs" / "job-1")


def test_zip_upload_bad_zip_raises_fetch_error(hf_hub, storage, tmp_path):
    object_path = "uploads/user-1/upload-1.zip"
    storage.put_bytes(object_path, b"not a zip")
    job = make_job(SourceType.ZIP_UPLOAD, object_path)
    fetcher = make_fetcher(hf_hub, storage, tmp_path)

    with pytest.raises(DatasetFetchError):
        fetcher.fetch_for_job(job, tmp_path / "jobs" / "job-1")


def test_hf_cache_eviction_runs_after_download(hf_hub, storage, tmp_path):
    hf_hub.add_repo("org/small", {"data.bin": b"x" * 100})
    hf_hub.add_repo("org/big", {"data.bin": b"x" * 200})
    fetcher = make_fetcher(hf_hub, storage, tmp_path, cache_max_bytes=250)

    fetcher.fetch_for_job(make_job(SourceType.HF_HUB, "org/small"), tmp_path / "jobs" / "job-1")
    import time

    time.sleep(0.01)
    fetcher.fetch_for_job(make_job(SourceType.HF_HUB, "org/big", job_id="job-2"), tmp_path / "jobs" / "job-2")

    cache_dir = tmp_path / "cache"
    remaining = {p.name for p in cache_dir.iterdir() if not p.name.endswith(".tmp")}
    assert remaining == {"org__big"}
