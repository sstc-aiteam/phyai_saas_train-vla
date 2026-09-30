#!/usr/bin/env python3
"""Training container entrypoint contract (spec section 2 & 3).

Runs a real SmolVLA training run with `lerobot`. Unlike ACT, SmolVLA is a
VLM-based policy: "training" it from random weights is not a realistic
option on a single RTX 4090 within the spec's 20,000-step cap, so -- as
HuggingFace's own SmolVLA docs recommend -- this finetunes the official
pretrained checkpoint (`lerobot/smolvla_base`) on the submitted dataset
instead. That base checkpoint is baked into this image at build time (see
Dockerfile), so no network access is needed at run time beyond what the
worker already did to fetch the dataset. Everything else uses SmolVLA's
official defaults (frozen vision encoder, action-expert-only finetuning,
etc.) -- --training-steps is the spec's only tunable hyperparameter.

See docker/act/train_entrypoint.py for the full contract this preserves
for the worker (progress.json shape/cadence, checkpoint directory,
exit-code-only failure signaling) -- identical here, kept as its own file
per policy image rather than a shared import (spec section 2: each policy
gets its own independent Docker image / environment).

Note: SmolVLA's `SmolVLAConfig.validate_features()` requires at least one
visual observation feature, which this repo's dataset validation
(common/domain/policy_shapes.py) already enforces for smolvla specifically.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch
from torch.utils.data import DataLoader

from lerobot.datasets import EpisodeAwareSampler, LeRobotDataset, LeRobotDatasetMetadata, resolve_delta_timestamps
from lerobot.policies.factory import make_policy, make_pre_post_processors
from lerobot.policies.smolvla.configuration_smolvla import SmolVLAConfig
from lerobot.utils.collate import lerobot_collate_fn

POLICY_NAME = "smolvla"
BATCH_SIZE = 8  # lerobot's own TrainPipelineConfig default -- not spec-tunable
PRETRAINED_BASE = "lerobot/smolvla_base"  # baked into the image at build time

# The worker fails a `training` job if progress.json hasn't changed in 2
# minutes (common/domain/heartbeat.py). Force a write at least this often so
# a slow step (or a small dataset with few steps-per-percent) never trips
# that timeout, even though the main cadence below is percentage-based.
MAX_SECONDS_BETWEEN_PROGRESS_WRITES = 60.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-type", required=True, choices=["hf_hub", "zip_upload"])
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--training-steps", required=True, type=int)
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def check_input_dir(input_dir: Path) -> None:
    if not input_dir.is_dir() or not any(input_dir.iterdir()):
        raise FileNotFoundError(f"--input-dir is missing or empty: {input_dir}")


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


def build_policy_config(device: str) -> SmolVLAConfig:
    return SmolVLAConfig(device=device, pretrained_path=PRETRAINED_BASE)


def load_dataset(input_dir: Path, policy_cfg: SmolVLAConfig) -> LeRobotDataset:
    # `repo_id` is never resolved against the Hub here: `root` points straight at the
    # already-fetched dataset the worker mounted, so this stays fully offline.
    repo_id = "local/dataset"
    ds_meta = LeRobotDatasetMetadata(repo_id, root=input_dir)
    delta_timestamps = resolve_delta_timestamps(policy_cfg, ds_meta)
    return LeRobotDataset(repo_id, root=input_dir, delta_timestamps=delta_timestamps, return_uint8=True)


def build_dataloader(dataset: LeRobotDataset, policy_cfg: SmolVLAConfig) -> DataLoader:
    sampler = EpisodeAwareSampler(
        dataset.meta.episodes["dataset_from_index"],
        dataset.meta.episodes["dataset_to_index"],
        episode_indices_to_use=dataset.episodes,
        drop_n_last_frames=getattr(policy_cfg, "drop_n_last_frames", 0),
        shuffle=True,
        seed=1000,
    )
    collate_fn = lerobot_collate_fn if dataset.meta.has_language_columns else None
    return DataLoader(
        dataset,
        batch_size=BATCH_SIZE,
        sampler=sampler,
        # Single-process loading: the worker's `docker run` doesn't size /dev/shm for
        # multi-worker tensor passing (default 64MB), so num_workers>0 risks a crash on
        # image-heavy batches. GPU compute, not CPU dataloading, dominates step time here.
        num_workers=0,
        pin_memory=torch.cuda.is_available(),
        drop_last=False,
        collate_fn=collate_fn,
    )


def build_processors(policy_cfg: SmolVLAConfig, policy: Any, dataset: LeRobotDataset):
    device = policy_cfg.device
    # Mirrors lerobot's own `lerobot_train.py`: load the pretrained base's processor
    # pipeline (so image sizing / tokenizer settings match the base model exactly), but
    # override its normalization stats with this dataset's -- the base's stats were
    # computed on its own training data, not the dataset being finetuned on here.
    return make_pre_post_processors(
        policy_cfg=policy_cfg,
        pretrained_path=str(policy_cfg.pretrained_path),
        dataset_stats=dataset.meta.stats,
        preprocessor_overrides={
            "device_processor": {"device": device},
            "normalizer_processor": {
                "features": {**policy.config.input_features, **policy.config.output_features},
                "norm_map": policy.config.normalization_mapping,
                "stats": dataset.meta.stats,
            },
        },
        postprocessor_overrides={
            "unnormalizer_processor": {
                "features": policy.config.output_features,
                "norm_map": policy.config.normalization_mapping,
                "stats": dataset.meta.stats,
            },
        },
    )


def cycle(iterable) -> Iterator[Any]:
    while True:
        yield from iterable


def run_training_loop(
    dataset: LeRobotDataset,
    policy: Any,
    preprocessor: Any,
    dataloader: DataLoader,
    total_steps: int,
    output_dir: Path,
) -> None:
    optimizer_cfg = policy.config.get_optimizer_preset()
    optimizer = optimizer_cfg.build(policy.get_optim_params())
    scheduler_cfg = policy.config.get_scheduler_preset()
    lr_scheduler = scheduler_cfg.build(optimizer, total_steps) if scheduler_cfg is not None else None

    camera_keys = dataset.meta.camera_keys
    policy.train()

    data_iter = cycle(dataloader)
    progress_every = max(1, total_steps // 200)
    last_write_at = time.monotonic()

    for step in range(1, total_steps + 1):
        batch = next(data_iter)
        for cam_key in camera_keys:
            if cam_key in batch and batch[cam_key].dtype == torch.uint8:
                batch[cam_key] = batch[cam_key].to(dtype=torch.float32) / 255.0
        batch = preprocessor(batch)

        loss, _ = policy.forward(batch)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(policy.parameters(), optimizer_cfg.grad_clip_norm)
        optimizer.step()
        optimizer.zero_grad()
        if lr_scheduler is not None:
            lr_scheduler.step()
        if hasattr(policy, "update"):
            policy.update()

        now = time.monotonic()
        if (
            step % progress_every == 0
            or step == total_steps
            or now - last_write_at >= MAX_SECONDS_BETWEEN_PROGRESS_WRITES
        ):
            write_progress(output_dir, step, total_steps, loss.item())
            last_write_at = now

    policy.eval()


def write_checkpoint(output_dir: Path, policy: Any, preprocessor: Any, postprocessor: Any) -> None:
    checkpoint_dir = output_dir / "checkpoint"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    policy.save_pretrained(checkpoint_dir)
    preprocessor.save_pretrained(checkpoint_dir)
    postprocessor.save_pretrained(checkpoint_dir)


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    check_input_dir(Path(args.input_dir))

    device = "cuda" if torch.cuda.is_available() else "cpu"
    policy_cfg = build_policy_config(device)

    dataset = load_dataset(Path(args.input_dir), policy_cfg)
    policy = make_policy(cfg=policy_cfg, ds_meta=dataset.meta)
    preprocessor, postprocessor = build_processors(policy_cfg, policy, dataset)
    dataloader = build_dataloader(dataset, policy_cfg)

    run_training_loop(dataset, policy, preprocessor, dataloader, args.training_steps, output_dir)
    write_checkpoint(output_dir, policy, preprocessor, postprocessor)


if __name__ == "__main__":
    main()
