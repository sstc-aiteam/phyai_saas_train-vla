import json

from worker.progress_reader import read_progress


def test_returns_none_when_file_missing(tmp_path):
    assert read_progress(tmp_path) is None


def test_reads_valid_progress_file(tmp_path):
    (tmp_path / "progress.json").write_text(
        json.dumps({"step": 42, "total_steps": 1000, "loss": 0.123, "timestamp": "2026-01-01T12:00:00+00:00"})
    )

    progress = read_progress(tmp_path)

    assert progress.step == 42
    assert progress.total_steps == 1000
    assert progress.loss == 0.123
    assert progress.updated_at.year == 2026


def test_returns_none_for_malformed_json(tmp_path):
    (tmp_path / "progress.json").write_text("not json {{{")
    assert read_progress(tmp_path) is None


def test_returns_none_for_missing_required_keys(tmp_path):
    (tmp_path / "progress.json").write_text(json.dumps({"step": 1}))
    assert read_progress(tmp_path) is None
