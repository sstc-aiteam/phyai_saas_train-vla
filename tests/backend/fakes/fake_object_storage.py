from __future__ import annotations

import io
from contextlib import contextmanager
from typing import BinaryIO, ContextManager

from common.ports.object_storage import ObjectStorage


class FakeObjectStorage(ObjectStorage):
    """In-memory object store. Test setup can seed bytes directly via
    `put_bytes` to simulate a file the frontend already uploaded."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def put_bytes(self, object_path: str, data: bytes) -> None:
        self._objects[object_path] = data

    def generate_upload_url(self, object_path: str, content_type: str, expires_in_seconds: int) -> str:
        return f"https://fake-gcs.local/upload/{object_path}?content_type={content_type}"

    def generate_download_url(self, object_path: str, expires_in_seconds: int) -> str:
        return f"https://fake-gcs.local/download/{object_path}"

    def open_read_stream(self, object_path: str) -> ContextManager[BinaryIO]:
        if object_path not in self._objects:
            raise FileNotFoundError(object_path)

        @contextmanager
        def _open():
            yield io.BytesIO(self._objects[object_path])

        return _open()

    def exists(self, object_path: str) -> bool:
        return object_path in self._objects

    def delete(self, object_path: str) -> None:
        self._objects.pop(object_path, None)
        self.deleted.append(object_path)

    def upload_file(self, object_path: str, local_path: str) -> None:
        with open(local_path, "rb") as f:
            self._objects[object_path] = f.read()
