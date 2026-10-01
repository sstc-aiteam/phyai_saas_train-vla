#!/usr/bin/env python3
"""Writes a minimal, validly-shaped LeRobot v3 dataset zip for manually
testing the zip-upload path (POST /uploads/zip/target + /uploads/zip/confirm)
without needing a real robot dataset.

Usage:
    uv run python scripts/make_demo_dataset_zip.py [--policy act|smolvla] [--out demo_dataset.zip]

The output only needs to satisfy `common.domain.dataset_validation` (a
meta/info.json file + something under data/) and
`common.domain.policy_shapes` (observation.state + action, plus a visual
feature for smolvla; act accepts either a visual feature or
observation.environment_state, matching real lerobot's ACTConfig — this
demo uses environment_state for act, since it has no video to include)
— it is not a real, trainable dataset.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path


def build_info_json(policy: str) -> dict:
    features = {
        "observation.state": {"shape": [14]},
        "action": {"shape": [7]},
    }
    if policy == "smolvla":
        features["observation.images.top"] = {"shape": [3, 224, 224]}
    else:
        features["observation.environment_state"] = {"shape": [10]}
    return {"features": features}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", choices=["act", "smolvla"], default="act")
    parser.add_argument("--out", default="demo_dataset.zip")
    args = parser.parse_args()

    out_path = Path(args.out)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("meta/info.json", json.dumps(build_info_json(args.policy)))
        zf.writestr("data/chunk-000/episode_000000.parquet", b"placeholder-not-real-parquet-data")
        if args.policy == "smolvla":
            zf.writestr("videos/chunk-000/observation.images.top/episode_000000.mp4", b"placeholder-not-real-video")

    print(f"Wrote {out_path} (policy={args.policy})")


if __name__ == "__main__":
    main()
