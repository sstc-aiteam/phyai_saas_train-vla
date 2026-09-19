"""Packages a finished training container's checkpoint directory (policy
weights + config.json + normalization stats, per spec section 3.7) into a
single zip file ready to upload to GCS."""

from __future__ import annotations

import zipfile
from pathlib import Path


class CheckpointNotFoundError(Exception):
    pass


def package_checkpoint(checkpoint_dir: Path, zip_path: Path) -> Path:
    if not checkpoint_dir.is_dir():
        raise CheckpointNotFoundError(str(checkpoint_dir))

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(checkpoint_dir.rglob("*")):
            if file_path.is_file():
                zf.write(file_path, arcname=file_path.relative_to(checkpoint_dir))

    return zip_path
