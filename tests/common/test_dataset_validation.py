from common.domain.dataset_validation import (
    ValidationLimits,
    ZipEntryMeta,
    check_decompression_bomb,
    check_lerobot_structure,
)

VALID_NAMES = [
    "meta/info.json",
    "meta/stats.json",
    "data/chunk-000/episode_000000.parquet",
    "videos/chunk-000/observation.images.top/episode_000000.mp4",
]


def test_valid_structure_passes():
    result = check_lerobot_structure(VALID_NAMES)
    assert result.ok is True


def test_missing_info_json_fails():
    names = [n for n in VALID_NAMES if n != "meta/info.json"]
    result = check_lerobot_structure(names)
    assert result.ok is False
    assert "meta/info.json" in result.error


def test_missing_data_dir_fails():
    names = [n for n in VALID_NAMES if not n.startswith("data/")]
    result = check_lerobot_structure(names)
    assert result.ok is False
    assert "data/" in result.error


def test_videos_dir_is_optional():
    names = [n for n in VALID_NAMES if not n.startswith("videos/")]
    result = check_lerobot_structure(names)
    assert result.ok is True


LIMITS = ValidationLimits(
    max_total_uncompressed_bytes=1000,
    max_single_file_bytes=400,
    max_file_count=3,
)


def test_bomb_check_passes_under_all_limits():
    entries = [ZipEntryMeta("a", 100), ZipEntryMeta("b", 200)]
    result = check_decompression_bomb(entries, LIMITS)
    assert result.ok is True


def test_bomb_check_fails_on_file_count():
    entries = [ZipEntryMeta(f"f{i}", 10) for i in range(4)]
    result = check_decompression_bomb(entries, LIMITS)
    assert result.ok is False
    assert "too many files" in result.error


def test_bomb_check_fails_on_single_file_size():
    entries = [ZipEntryMeta("huge", 500)]
    result = check_decompression_bomb(entries, LIMITS)
    assert result.ok is False
    assert "per-file size limit" in result.error


def test_bomb_check_fails_on_total_size():
    entries = [ZipEntryMeta("a", 400), ZipEntryMeta("b", 400), ZipEntryMeta("c", 300)]
    # This is a classic decompression-bomb shape: many small-enough files
    # that individually pass the per-file cap but blow the total budget.
    result = check_decompression_bomb(entries, LIMITS)
    assert result.ok is False
    assert "total size limit" in result.error


def test_bomb_check_defaults_are_reasonable():
    entries = [ZipEntryMeta("a", 1024)]
    result = check_decompression_bomb(entries)
    assert result.ok is True
