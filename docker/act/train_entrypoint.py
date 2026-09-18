#!/usr/bin/env python3
"""Training container entrypoint contract (spec section 2 & 3).

This is a stub: it does NOT actually train an ACT policy (this environment
has no GPU and no `lerobot` install to verify that against). What it does
implement for real is the *contract* the worker depends on:

- Read --source-type/--source-ref/--training-steps/--output-dir args.
- Periodically write `progress.json` into --output-dir with the exact
  shape the worker's `common.domain.heartbeat` / `Progress` model expects:
  {"step": int, "total_steps": int, "loss": float, "timestamp": iso8601}.
- On completion, write a checkpoint directory containing policy weights,
  `config.json`, and normalization stats, ready for the worker to zip and
  upload to GCS.

Replacing the body of `_run_training_loop` with a real lerobot ACT training
run (dataset loading, model, optimizer, checkpointing) is the follow-up
work once this runs on the actual GPU host.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

POLICY_NAME = "act"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-type", required=True, choices=["hf_hub", "zip_upload"])
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--training-steps", required=True, type=int)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def write_progress(output_dir: Path, step: int, total_steps: int, loss: float) -> None:
    progress = {
        "step": step,
        "total_steps": total_steps,
        "loss": loss,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    tmp_path = output_dir / "progress.json.tmp"
    tmp_path.write_text(json.dumps(progress))
    os.replace(tmp_path, output_dir / "progress.json")


def write_checkpoint(output_dir: Path, training_steps: int) -> None:
    checkpoint_dir = output_dir / "checkpoint"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    (checkpoint_dir / "model.safetensors").write_bytes(b"")  # placeholder weights
    (checkpoint_dir / "config.json").write_text(
        json.dumps({"policy": POLICY_NAME, "training_steps": training_steps})
    )
    (checkpoint_dir / "normalization_stats.json").write_text(json.dumps({}))


def run_training_loop(output_dir: Path, total_steps: int) -> None:
    progress_every = max(1, total_steps // 100)
    for step in range(1, total_steps + 1):
        if step % progress_every == 0 or step == total_steps:
            loss = 1.0 / step  # placeholder decreasing loss curve
            write_progress(output_dir, step, total_steps, loss)
        time.sleep(0)  # replace with a real training step


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_training_loop(output_dir, args.training_steps)
    write_checkpoint(output_dir, args.training_steps)


if __name__ == "__main__":
    main()
