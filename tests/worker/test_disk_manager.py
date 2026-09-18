import os
import time

from worker.disk_manager import (
    cleanup_stale_tmp_dirs,
    directory_size_bytes,
    evict_lru_until_under_cap,
    final_path_for,
    finalize_download,
    list_cache_entries,
    tmp_path_for,
)


def make_dir_with_file(path, size_bytes: int, mtime: float | None = None):
    path.mkdir(parents=True)
    (path / "data.bin").write_bytes(b"x" * size_bytes)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
        os.utime(path / "data.bin", (mtime, mtime))


def test_directory_size_bytes_sums_files_recursively(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    (d / "a.bin").write_bytes(b"x" * 100)
    (d / "sub").mkdir()
    (d / "sub" / "b.bin").write_bytes(b"y" * 50)

    assert directory_size_bytes(d) == 150


def test_list_cache_entries_ignores_tmp_dirs(tmp_path):
    make_dir_with_file(tmp_path / "repo-a", 10)
    make_dir_with_file(tmp_path / "repo-b.tmp", 10)

    entries = list_cache_entries(tmp_path)
    names = {e.path.name for e in entries}
    assert names == {"repo-a"}


def test_evict_lru_until_under_cap_removes_oldest_first(tmp_path):
    now = time.time()
    make_dir_with_file(tmp_path / "old", 100, mtime=now - 3600)
    make_dir_with_file(tmp_path / "newer", 100, mtime=now - 60)
    make_dir_with_file(tmp_path / "newest", 100, mtime=now)

    removed = evict_lru_until_under_cap(tmp_path, max_bytes=150)

    assert [p.name for p in removed] == ["old", "newer"]
    assert not (tmp_path / "old").exists()
    assert not (tmp_path / "newer").exists()
    assert (tmp_path / "newest").exists()


def test_evict_lru_noop_when_under_cap(tmp_path):
    make_dir_with_file(tmp_path / "repo", 100)
    removed = evict_lru_until_under_cap(tmp_path, max_bytes=1000)
    assert removed == []
    assert (tmp_path / "repo").exists()


def test_cleanup_stale_tmp_dirs_removes_old_ones_only(tmp_path):
    now = time.time()
    make_dir_with_file(tmp_path / "stale.tmp", 10, mtime=now - 7200)
    make_dir_with_file(tmp_path / "fresh.tmp", 10, mtime=now - 10)
    make_dir_with_file(tmp_path / "not-a-tmp-dir", 10, mtime=now - 7200)

    removed = cleanup_stale_tmp_dirs(tmp_path, older_than_seconds=3600, now=now)

    assert [p.name for p in removed] == ["stale.tmp"]
    assert not (tmp_path / "stale.tmp").exists()
    assert (tmp_path / "fresh.tmp").exists()
    assert (tmp_path / "not-a-tmp-dir").exists()


def test_cleanup_stale_tmp_dirs_on_missing_cache_dir_returns_empty(tmp_path):
    assert cleanup_stale_tmp_dirs(tmp_path / "does-not-exist", older_than_seconds=3600) == []


def test_finalize_download_renames_tmp_into_place(tmp_path):
    repo_id = "org/dataset"
    tmp_dir = tmp_path_for(tmp_path, repo_id)
    final_dir = final_path_for(tmp_path, repo_id)
    make_dir_with_file(tmp_dir, 10)

    finalize_download(tmp_dir, final_dir)

    assert not tmp_dir.exists()
    assert final_dir.exists()
    assert (final_dir / "data.bin").exists()


def test_tmp_path_for_sanitizes_repo_id_slashes(tmp_path):
    tmp_dir = tmp_path_for(tmp_path, "org/dataset")
    assert "/" not in tmp_dir.name
    assert tmp_dir.name.endswith(".tmp")
