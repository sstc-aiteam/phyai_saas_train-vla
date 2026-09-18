import io
import json
import zipfile
from datetime import datetime, timezone

import pytest

from backend.services.job_service import JobService
from backend.services.upload_service import (
    HFDatasetNotFoundError,
    UploadNotFoundError,
    UploadService,
    UploadValidationError,
)
from common.domain.dataset_validation import ValidationLimits
from common.models import AuthProvider, JobStatus, PolicyType, User

from tests.backend.fakes.fake_hf_hub_client import FakeHFHubClient
from tests.backend.fakes.fake_job_repository import FakeJobRepository
from tests.backend.fakes.fake_object_storage import FakeObjectStorage
from tests.backend.fakes.fake_user_repository import FakeUserRepository

FIXED_NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

VALID_INFO_JSON = json.dumps(
    {
        "features": {
            "observation.state": {"shape": [14]},
            "action": {"shape": [7]},
        }
    }
).encode("utf-8")


def make_zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


@pytest.fixture
def user_repo():
    repo = FakeUserRepository()
    repo.create(User(id="user-1", auth_provider=AuthProvider.EMAIL, email="a@example.com"))
    return repo


@pytest.fixture
def job_repo():
    return FakeJobRepository()


@pytest.fixture
def job_service(job_repo, user_repo):
    return JobService(job_repo, user_repo, now_fn=lambda: FIXED_NOW)


@pytest.fixture
def storage():
    return FakeObjectStorage()


@pytest.fixture
def hf_hub():
    return FakeHFHubClient()


@pytest.fixture
def service(storage, hf_hub, job_service):
    return UploadService(storage, hf_hub, job_service, limits=ValidationLimits(max_total_uncompressed_bytes=10_000_000))


VALID_ZIP_FILES = {
    "meta/info.json": VALID_INFO_JSON,
    "data/chunk-000/episode_000000.parquet": b"fake-parquet-bytes",
}


def test_confirm_zip_upload_creates_job(service, storage):
    upload_id, url = service.create_upload_target("user-1")
    assert url.startswith("https://")
    object_path = f"uploads/user-1/{upload_id}.zip"
    storage.put_bytes(object_path, make_zip_bytes(VALID_ZIP_FILES))

    job = service.confirm_zip_upload("user-1", upload_id, PolicyType.ACT, 1000)
    assert job.status == JobStatus.QUEUED
    assert job.source_ref == object_path
    assert storage.exists(object_path)  # kept for the worker to consume


def test_confirm_zip_upload_missing_object_raises(service):
    with pytest.raises(UploadNotFoundError):
        service.confirm_zip_upload("user-1", "nonexistent-upload-id", PolicyType.ACT, 1000)


def test_confirm_zip_upload_rejects_bad_zip_and_deletes_object(service, storage):
    upload_id, _ = service.create_upload_target("user-1")
    object_path = f"uploads/user-1/{upload_id}.zip"
    storage.put_bytes(object_path, b"this is not a zip file")

    with pytest.raises(UploadValidationError):
        service.confirm_zip_upload("user-1", upload_id, PolicyType.ACT, 1000)
    assert not storage.exists(object_path)


def test_confirm_zip_upload_rejects_missing_structure_and_deletes_object(service, storage):
    upload_id, _ = service.create_upload_target("user-1")
    object_path = f"uploads/user-1/{upload_id}.zip"
    storage.put_bytes(object_path, make_zip_bytes({"meta/info.json": VALID_INFO_JSON}))  # no data/

    with pytest.raises(UploadValidationError, match="data/"):
        service.confirm_zip_upload("user-1", upload_id, PolicyType.ACT, 1000)
    assert not storage.exists(object_path)


def test_confirm_zip_upload_rejects_decompression_bomb(service, storage):
    upload_id, _ = service.create_upload_target("user-1")
    object_path = f"uploads/user-1/{upload_id}.zip"
    files = dict(VALID_ZIP_FILES)
    files["data/chunk-000/huge.bin"] = b"x" * 20_000_000  # exceeds the 10MB test limit
    storage.put_bytes(object_path, make_zip_bytes(files))

    with pytest.raises(UploadValidationError):
        service.confirm_zip_upload("user-1", upload_id, PolicyType.ACT, 1000)
    assert not storage.exists(object_path)


def test_confirm_zip_upload_rejects_incompatible_policy_shape(service, storage):
    upload_id, _ = service.create_upload_target("user-1")
    object_path = f"uploads/user-1/{upload_id}.zip"
    storage.put_bytes(object_path, make_zip_bytes(VALID_ZIP_FILES))  # no visual feature

    with pytest.raises(UploadValidationError, match="visual"):
        service.confirm_zip_upload("user-1", upload_id, PolicyType.SMOLVLA, 1000)
    assert not storage.exists(object_path)


def test_submit_hf_dataset_creates_job(service, hf_hub):
    hf_hub.add_repo("some-org/some-dataset", VALID_ZIP_FILES)
    job = service.submit_hf_dataset("user-1", "some-org/some-dataset", PolicyType.ACT, 1000)
    assert job.status == JobStatus.QUEUED
    assert job.source_ref == "some-org/some-dataset"


def test_submit_hf_dataset_unknown_repo_raises(service):
    with pytest.raises(HFDatasetNotFoundError):
        service.submit_hf_dataset("user-1", "does-not/exist", PolicyType.ACT, 1000)


def test_submit_hf_dataset_missing_structure_raises(service, hf_hub):
    hf_hub.add_repo("some-org/some-dataset", {"meta/info.json": VALID_INFO_JSON})
    with pytest.raises(UploadValidationError, match="data/"):
        service.submit_hf_dataset("user-1", "some-org/some-dataset", PolicyType.ACT, 1000)


def test_submit_hf_dataset_incompatible_policy_shape_raises(service, hf_hub):
    hf_hub.add_repo("some-org/some-dataset", VALID_ZIP_FILES)
    with pytest.raises(UploadValidationError, match="visual"):
        service.submit_hf_dataset("user-1", "some-org/some-dataset", PolicyType.SMOLVLA, 1000)
