import pytest

from worker.lock import LockAcquisitionError, WorkerLock


def test_acquire_and_release(tmp_path):
    lock_path = str(tmp_path / "worker.lock")
    lock = WorkerLock(lock_path)
    lock.acquire()
    assert lock.is_held is True
    lock.release()
    assert lock.is_held is False


def test_second_lock_on_same_path_fails_while_first_is_held(tmp_path):
    lock_path = str(tmp_path / "worker.lock")
    first = WorkerLock(lock_path)
    second = WorkerLock(lock_path)

    first.acquire()
    try:
        with pytest.raises(LockAcquisitionError):
            second.acquire()
    finally:
        first.release()


def test_second_lock_succeeds_after_first_releases(tmp_path):
    lock_path = str(tmp_path / "worker.lock")
    first = WorkerLock(lock_path)
    second = WorkerLock(lock_path)

    first.acquire()
    first.release()

    second.acquire()
    assert second.is_held is True
    second.release()


def test_context_manager_releases_on_exit(tmp_path):
    lock_path = str(tmp_path / "worker.lock")
    with WorkerLock(lock_path) as lock:
        assert lock.is_held is True

    other = WorkerLock(lock_path)
    other.acquire()
    other.release()


def test_double_acquire_on_same_instance_is_a_noop(tmp_path):
    lock_path = str(tmp_path / "worker.lock")
    lock = WorkerLock(lock_path)
    lock.acquire()
    lock.acquire()  # should not raise or deadlock
    lock.release()
