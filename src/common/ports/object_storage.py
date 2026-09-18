"""Port: object storage (implemented by GCS adapter / in-memory fake).

The zip-upload flow never proxies file bytes through the backend — the
frontend uploads directly via a signed URL. The backend only needs to
mint URLs, stream-read objects for validation, check existence, and delete.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import BinaryIO, ContextManager


class ObjectStorage(ABC):
    @abstractmethod
    def generate_upload_url(self, object_path: str, content_type: str, expires_in_seconds: int) -> str: ...

    @abstractmethod
    def generate_download_url(self, object_path: str, expires_in_seconds: int) -> str: ...

    @abstractmethod
    def open_read_stream(self, object_path: str) -> ContextManager[BinaryIO]:
        """Open a streaming, seekable-or-not file-like object for reading."""
        ...

    @abstractmethod
    def exists(self, object_path: str) -> bool: ...

    @abstractmethod
    def delete(self, object_path: str) -> None: ...

    @abstractmethod
    def upload_file(self, object_path: str, local_path: str) -> None: ...
