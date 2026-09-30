"""These scripts live under docker/ (each policy's own Docker image, not
part of the installed src/ package), so we load them directly by path
rather than importing them as a package.

Only the parts of the contract that don't need `torch`/`lerobot` (neither is
an installed dependency of this project -- they only exist inside the
training images) are covered here: CLI parsing, `--input-dir` validation,
and the `progress.json` write shape/atomicity. The real training loop,
checkpoint writer, and `main()` end-to-end path need a real dataset, a real
policy, and (in practice) a GPU to mean anything; those were verified
manually against the real RTX 4090 training host instead -- see the
"Real ACT/SmolVLA training" section in the main README.
"""

import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("lerobot")

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


def test_check_input_dir_raises_when_missing(tmp_path, entrypoint):
    with pytest.raises(FileNotFoundError):
        entrypoint.check_input_dir(tmp_path / "does-not-exist")


def test_check_input_dir_raises_when_empty(tmp_path, entrypoint):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        entrypoint.check_input_dir(empty_dir)


def test_check_input_dir_passes_when_populated(tmp_path, entrypoint):
    populated_dir = tmp_path / "populated"
    populated_dir.mkdir()
    (populated_dir / "meta.json").write_text("{}")
    entrypoint.check_input_dir(populated_dir)  # should not raise


def test_main_raises_when_input_dir_empty(tmp_path, entrypoint, monkeypatch):
    # check_input_dir runs before any dataset/policy loading in main(), so this
    # stays a fast, GPU-free check even though main() otherwise needs both.
    input_dir = tmp_path / "input"
    input_dir.mkdir()  # empty
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
            "--input-dir",
            str(input_dir),
            "--output-dir",
            str(output_dir),
        ],
    )

    with pytest.raises(FileNotFoundError):
        entrypoint.main()
