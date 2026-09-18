"""These scripts live under docker/ (each policy's own Docker image, not
part of the installed src/ package), so we load them directly by path
rather than importing them as a package."""

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_entrypoint_module(policy: str):
    script_path = REPO_ROOT / "docker" / policy / "train_entrypoint.py"
    spec = importlib.util.spec_from_file_location(f"{policy}_train_entrypoint", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(params=["act", "smolvla"])
def entrypoint(request):
    return load_entrypoint_module(request.param)


def test_write_progress_creates_expected_shape(tmp_path, entrypoint):
    entrypoint.write_progress(tmp_path, step=5, total_steps=100, loss=0.42)

    progress = json.loads((tmp_path / "progress.json").read_text())
    assert progress["step"] == 5
    assert progress["total_steps"] == 100
    assert progress["loss"] == 0.42
    assert "timestamp" in progress
    assert not (tmp_path / "progress.json.tmp").exists()


def test_write_checkpoint_creates_expected_files(tmp_path, entrypoint):
    entrypoint.write_checkpoint(tmp_path, training_steps=1000)

    checkpoint_dir = tmp_path / "checkpoint"
    assert (checkpoint_dir / "model.safetensors").exists()
    assert (checkpoint_dir / "normalization_stats.json").exists()

    config = json.loads((checkpoint_dir / "config.json").read_text())
    assert config["policy"] == entrypoint.POLICY_NAME
    assert config["training_steps"] == 1000


def test_run_training_loop_writes_final_progress_at_total_steps(tmp_path, entrypoint):
    entrypoint.run_training_loop(tmp_path, total_steps=10)

    progress = json.loads((tmp_path / "progress.json").read_text())
    assert progress["step"] == 10
    assert progress["total_steps"] == 10


def test_main_end_to_end_produces_progress_and_checkpoint(tmp_path, entrypoint, monkeypatch):
    output_dir = tmp_path / "output"
    monkeypatch.setattr(
        "sys.argv",
        [
            "train_entrypoint.py",
            "--source-type",
            "hf_hub",
            "--source-ref",
            "org/dataset",
            "--training-steps",
            "5",
            "--output-dir",
            str(output_dir),
        ],
    )

    entrypoint.main()

    assert (output_dir / "progress.json").exists()
    assert (output_dir / "checkpoint" / "config.json").exists()
