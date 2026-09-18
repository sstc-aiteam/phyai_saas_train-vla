"""Dataset submission use cases (spec section 3, steps 2-3).

Two independent submission paths, sharing the same structure /
decompression-bomb / policy-shape validation rules from `common.domain`:

- Zip upload: the frontend uploads directly to GCS via a signed URL, then
  calls `confirm_zip_upload`, which streams the object back from GCS to
  validate it before creating a Job. Any failure deletes the GCS object.
- HF Hub dataset: `submit_hf_dataset` checks the repo via the HF Hub API
  without downloading the dataset.
"""

from __future__ import annotations

import uuid
import zipfile

from common.domain.dataset_validation import (
    DEFAULT_LIMITS,
    ValidationLimits,
    ZipEntryMeta,
    check_decompression_bomb,
    check_lerobot_structure,
)
from common.domain.policy_shapes import InvalidInfoJsonError, check_policy_compatibility, parse_info_json
from common.models import PolicyType, SourceType
from common.ports.hf_hub_client import HFHubClient
from common.ports.object_storage import ObjectStorage

from backend.services.job_service import JobService

INFO_JSON_PATH = "meta/info.json"
UPLOAD_URL_EXPIRES_IN_SECONDS = 15 * 60


class UploadValidationError(Exception):
    pass


class UploadNotFoundError(Exception):
    pass


class HFDatasetNotFoundError(Exception):
    pass


class UploadService:
    def __init__(
        self,
        storage: ObjectStorage,
        hf_hub_client: HFHubClient,
        job_service: JobService,
        limits: ValidationLimits = DEFAULT_LIMITS,
    ) -> None:
        self._storage = storage
        self._hf_hub = hf_hub_client
        self._jobs = job_service
        self._limits = limits

    # -- zip upload path ---------------------------------------------------

    def create_upload_target(self, user_id: str, upload_id: str | None = None) -> tuple[str, str]:
        """Return (upload_id, signed upload URL). The frontend PUTs the zip
        directly to that URL, then calls confirm_zip_upload with the same
        upload_id."""
        upload_id = upload_id or str(uuid.uuid4())
        object_path = self._object_path(user_id, upload_id)
        url = self._storage.generate_upload_url(
            object_path, content_type="application/zip", expires_in_seconds=UPLOAD_URL_EXPIRES_IN_SECONDS
        )
        return upload_id, url

    def confirm_zip_upload(
        self,
        user_id: str,
        upload_id: str,
        policy: PolicyType,
        training_steps: int,
    ):
        object_path = self._object_path(user_id, upload_id)
        if not self._storage.exists(object_path):
            raise UploadNotFoundError(object_path)

        try:
            entries, entry_names = self._read_zip_entries(object_path)
        except zipfile.BadZipFile:
            self._reject(object_path, "Uploaded file is not a valid zip archive")

        structure_result = check_lerobot_structure(entry_names)
        if not structure_result.ok:
            self._reject(object_path, structure_result.error)

        bomb_result = check_decompression_bomb(entries, self._limits)
        if not bomb_result.ok:
            self._reject(object_path, bomb_result.error)

        try:
            info_bytes = self._read_zip_member(object_path, INFO_JSON_PATH)
            info = parse_info_json(info_bytes)
        except (KeyError, FileNotFoundError):
            self._reject(object_path, f"Missing required file: {INFO_JSON_PATH}")
        except InvalidInfoJsonError as exc:
            self._reject(object_path, str(exc))

        shape_result = check_policy_compatibility(info, policy)
        if not shape_result.ok:
            self._reject(object_path, shape_result.error)

        return self._jobs.create_job(user_id, policy, SourceType.ZIP_UPLOAD, object_path, training_steps)

    def _reject(self, object_path: str, error_message: str | None):
        self._storage.delete(object_path)
        raise UploadValidationError(error_message or "Dataset validation failed")

    def _object_path(self, user_id: str, upload_id: str) -> str:
        return f"uploads/{user_id}/{upload_id}.zip"

    def _read_zip_entries(self, object_path: str) -> tuple[list[ZipEntryMeta], list[str]]:
        with self._storage.open_read_stream(object_path) as stream:
            with zipfile.ZipFile(stream) as zf:
                infos = zf.infolist()
                entries = [ZipEntryMeta(name=i.filename, uncompressed_size=i.file_size) for i in infos]
                names = [i.filename for i in infos]
        return entries, names

    def _read_zip_member(self, object_path: str, member_name: str) -> bytes:
        with self._storage.open_read_stream(object_path) as stream:
            with zipfile.ZipFile(stream) as zf:
                return zf.read(member_name)

    # -- HF Hub dataset path -------------------------------------------------

    def submit_hf_dataset(
        self,
        user_id: str,
        repo_id: str,
        policy: PolicyType,
        training_steps: int,
    ):
        if not self._hf_hub.repo_exists(repo_id):
            raise HFDatasetNotFoundError(repo_id)

        entry_names = self._hf_hub.list_repo_files(repo_id)
        structure_result = check_lerobot_structure(entry_names)
        if not structure_result.ok:
            raise UploadValidationError(structure_result.error)

        try:
            info_bytes = self._hf_hub.get_repo_file_bytes(repo_id, INFO_JSON_PATH)
            info = parse_info_json(info_bytes)
        except FileNotFoundError:
            raise UploadValidationError(f"Missing required file: {INFO_JSON_PATH}") from None
        except InvalidInfoJsonError as exc:
            raise UploadValidationError(str(exc)) from exc

        shape_result = check_policy_compatibility(info, policy)
        if not shape_result.ok:
            raise UploadValidationError(shape_result.error)

        return self._jobs.create_job(user_id, policy, SourceType.HF_HUB, repo_id, training_steps)
