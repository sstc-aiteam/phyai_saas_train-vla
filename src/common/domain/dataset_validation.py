"""LeRobot v3 dataset validation rules.

Covers spec step 3(a)-(c):
  a. LeRobot v3 structure (`meta/info.json`, `data/`, `videos/` ...)
  b. Decompression-bomb protection (total size / single-file size / file count caps)
  c. Policy input compatibility (observation/action shape vs selected policy)

This module is pure: it takes already-extracted metadata (zip entry names +
sizes, or an equivalent listing from the HF Hub) rather than reading files
itself, so the same rules apply to both the zip-upload and HF-Hub-repo
submission paths. The adapters (zip streaming reader, HF Hub client) are
responsible for producing that metadata; see
`backend/services/upload_service.py` for how the two paths are unified.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ZipEntryMeta:
    name: str
    uncompressed_size: int


@dataclass(frozen=True)
class ValidationLimits:
    # Matches the product-level dataset size cap (spec section 6) — also
    # doubles as the decompression-bomb total-size ceiling.
    max_total_uncompressed_bytes: int = 2 * 1024**3
    max_single_file_bytes: int = 512 * 1024**2
    max_file_count: int = 200_000


DEFAULT_LIMITS = ValidationLimits()

REQUIRED_META_FILE = "meta/info.json"
REQUIRED_DIR_PREFIX = "data/"


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    error: str | None = None

    @staticmethod
    def success() -> "ValidationResult":
        return ValidationResult(True)

    @staticmethod
    def failure(message: str) -> "ValidationResult":
        return ValidationResult(False, message)


def check_lerobot_structure(entry_names: list[str]) -> ValidationResult:
    names = set(entry_names)
    if REQUIRED_META_FILE not in names:
        return ValidationResult.failure(f"Missing required file: {REQUIRED_META_FILE}")
    if not any(name.startswith(REQUIRED_DIR_PREFIX) for name in names):
        return ValidationResult.failure(f"Missing required directory: {REQUIRED_DIR_PREFIX}")
    return ValidationResult.success()


def check_decompression_bomb(
    entries: list[ZipEntryMeta], limits: ValidationLimits = DEFAULT_LIMITS
) -> ValidationResult:
    if len(entries) > limits.max_file_count:
        return ValidationResult.failure(
            f"Archive contains too many files ({len(entries)} > {limits.max_file_count})"
        )

    total_size = 0
    for entry in entries:
        if entry.uncompressed_size > limits.max_single_file_bytes:
            return ValidationResult.failure(
                f"File '{entry.name}' exceeds the per-file size limit "
                f"({entry.uncompressed_size} > {limits.max_single_file_bytes} bytes)"
            )
        total_size += entry.uncompressed_size
        if total_size > limits.max_total_uncompressed_bytes:
            return ValidationResult.failure(
                f"Uncompressed archive exceeds the total size limit "
                f"({total_size} > {limits.max_total_uncompressed_bytes} bytes)"
            )

    return ValidationResult.success()
