"""Reads `progress.json` off the shared volume a training container writes
to (spec section 2: "Worker 與訓練容器透過共享 volume 上的 progress.json 溝通
訓練進度"). The container writes it atomically (write to a temp file, then
os.replace) — see docker/*/train_entrypoint.py — so a concurrent read here
never observes a half-written file.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from common.models import Progress

PROGRESS_FILENAME = "progress.json"


def read_progress(output_dir: Path) -> Progress | None:
    """Return the current progress, or None if the container hasn't written
    one yet (still `initializing`) or the file is unreadable/malformed."""
    progress_path = output_dir / PROGRESS_FILENAME
    if not progress_path.exists():
        return None

    try:
        raw = json.loads(progress_path.read_text())
        return Progress(
            step=raw["step"],
            total_steps=raw["total_steps"],
            loss=raw["loss"],
            updated_at=datetime.fromisoformat(raw["timestamp"]),
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        # A torn read (file mid-rename) or an unexpected shape — treat as
        # "no progress yet" rather than crashing the poll loop; the next
        # tick will pick up the next successfully-written file.
        return None
