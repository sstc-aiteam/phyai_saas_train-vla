"""Real GCS-backed ObjectStorage.

`open_read_stream` uses `Blob.open("rb")`, which returns a seekable
`BlobReader` backed by ranged HTTP reads — this is what makes the zip
structure/decompression-bomb check in `upload_service.py` "streaming"
(reads the central directory + the one small meta file, never the whole
object) rather than downloading the full dataset first.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import BinaryIO, ContextManager

from google.cloud import storage

from common.ports.object_storage import ObjectStorage


class GCSObjectStorage(ObjectStorage):
    def __init__(self, client: storage.Client, bucket_name: str) -> None:
        self._bucket = client.bucket(bucket_name)

    def generate_upload_url(self, object_path: str, content_type: str, expires_in_seconds: int) -> str:
        blob = self._bucket.blob(object_path)
        return blob.generate_signed_url(
            version="v4",
            expiration=expires_in_seconds,
            method="PUT",
            content_type=content_type,
        )

    def generate_download_url(self, object_path: str, expires_in_seconds: int) -> str:
        blob = self._bucket.blob(object_path)
        return blob.generate_signed_url(
            version="v4",
            expiration=expires_in_seconds,
            method="GET",
        )

    def open_read_stream(self, object_path: str) -> ContextManager[BinaryIO]:
        blob = self._bucket.blob(object_path)

        @contextmanager
        def _open():
            reader = blob.open("rb")
            try:
                yield reader
            finally:
                reader.close()

        return _open()

    def exists(self, object_path: str) -> bool:
        return self._bucket.blob(object_path).exists()

    def delete(self, object_path: str) -> None:
        blob = self._bucket.blob(object_path)
        if blob.exists():
            blob.delete()

    def upload_file(self, object_path: str, local_path: str) -> None:
        self._bucket.blob(object_path).upload_from_filename(local_path)
