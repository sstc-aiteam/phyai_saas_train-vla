import zipfile

import pytest

from worker.checkpoint_packager import CheckpointNotFoundError, package_checkpoint


def test_packages_all_files_in_checkpoint_dir(tmp_path):
    checkpoint_dir = tmp_path / "checkpoint"
    checkpoint_dir.mkdir()
    (checkpoint_dir / "model.safetensors").write_bytes(b"weights")
    (checkpoint_dir / "config.json").write_text('{"policy": "act"}')

    zip_path = tmp_path / "output" / "checkpoint.zip"
    result = package_checkpoint(checkpoint_dir, zip_path)

    assert result == zip_path
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as zf:
        assert set(zf.namelist()) == {"model.safetensors", "config.json"}
        assert zf.read("model.safetensors") == b"weights"


def test_packages_nested_files_with_relative_paths(tmp_path):
    checkpoint_dir = tmp_path / "checkpoint"
    (checkpoint_dir / "sub").mkdir(parents=True)
    (checkpoint_dir / "sub" / "extra.bin").write_bytes(b"x")

    zip_path = tmp_path / "checkpoint.zip"
    package_checkpoint(checkpoint_dir, zip_path)

    with zipfile.ZipFile(zip_path) as zf:
        assert "sub/extra.bin" in zf.namelist()


def test_raises_when_checkpoint_dir_missing(tmp_path):
    with pytest.raises(CheckpointNotFoundError):
        package_checkpoint(tmp_path / "does-not-exist", tmp_path / "out.zip")
