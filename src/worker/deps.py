"""Dependency wiring for the worker, mirroring `backend/deps.py`: builds
`JobPoller`/`JobCompletionMonitor` from either fake (in-memory) or real
adapters depending on `WorkerSettings.use_fake_adapters`. Kept separate
from `main.py` so a manual-test harness can call `build_worker_dependencies`
directly with adapter instances it shares with the backend process (see
`scripts/manual_test.py`), instead of each process getting its own,
disconnected in-memory store.
"""

from __future__ import annotations

from dataclasses import dataclass

from common.ports.docker_client import DockerClient
from common.ports.hf_hub_client import HFHubClient
from common.ports.job_repository import JobRepository
from common.ports.object_storage import ObjectStorage
from common.ports.user_repository import UserRepository

from worker.config import WorkerSettings
from worker.dataset_fetcher import DatasetFetcher
from worker.job_completion import JobCompletionMonitor
from worker.job_poller import JobPoller


@dataclass
class WorkerDependencies:
    settings: WorkerSettings
    job_repository: JobRepository
    user_repository: UserRepository
    docker_client: DockerClient
    object_storage: ObjectStorage
    poller: JobPoller
    completion_monitor: JobCompletionMonitor


def build_worker_dependencies(
    settings: WorkerSettings,
    job_repository: JobRepository,
    user_repository: UserRepository,
    docker_client: DockerClient,
    object_storage: ObjectStorage,
    hf_hub_client: HFHubClient,
) -> WorkerDependencies:
    dataset_fetcher = DatasetFetcher(
        hf_hub_client,
        object_storage,
        cache_dir=settings.hf_cache_dir,
        cache_max_bytes=settings.hf_cache_max_bytes,
    )
    poller = JobPoller(
        job_repository,
        user_repository,
        docker_client,
        dataset_fetcher,
        act_image=settings.act_image,
        smolvla_image=settings.smolvla_image,
        workdir=settings.workdir,
        use_gpu=settings.use_gpu,
    )
    completion_monitor = JobCompletionMonitor(
        job_repository,
        docker_client,
        object_storage,
        workdir=settings.workdir,
    )
    return WorkerDependencies(
        settings=settings,
        job_repository=job_repository,
        user_repository=user_repository,
        docker_client=docker_client,
        object_storage=object_storage,
        poller=poller,
        completion_monitor=completion_monitor,
    )


def build_default_worker_dependencies(settings: WorkerSettings) -> WorkerDependencies:
    """Chooses real-vs-fake adapters per `settings.use_fake_adapters`. Each
    call with `use_fake_adapters=True` gets its own fresh, empty in-memory
    store — good for a standalone smoke test of the worker loop, but *not*
    connected to any backend process. For a real shared-state manual test
    of the whole system, build a `WorkerDependencies` directly with adapter
    instances borrowed from the backend process instead (see
    `scripts/manual_test.py`)."""
    if settings.use_fake_adapters:
        from backend.adapters.memory import (
            InMemoryHFHubClient,
            InMemoryJobRepository,
            InMemoryObjectStorage,
            InMemoryUserRepository,
        )

        return build_worker_dependencies(
            settings,
            job_repository=InMemoryJobRepository(),
            user_repository=InMemoryUserRepository(),
            docker_client=_docker_client_for(settings),
            object_storage=InMemoryObjectStorage(),
            hf_hub_client=InMemoryHFHubClient(),
        )

    from google.cloud import firestore, storage

    from backend.adapters.firestore.job_repository import FirestoreJobRepository
    from backend.adapters.firestore.user_repository import FirestoreUserRepository
    from backend.adapters.gcs.object_storage import GCSObjectStorage
    from backend.adapters.hf.hf_hub_client import RealHFHubClient

    firestore_client = firestore.Client(project=settings.gcp_project_id, database=settings.firestore_database_id)
    return build_worker_dependencies(
        settings,
        job_repository=FirestoreJobRepository(firestore_client),
        user_repository=FirestoreUserRepository(firestore_client),
        docker_client=_docker_client_for(settings),
        object_storage=GCSObjectStorage(storage.Client(project=settings.gcp_project_id), settings.gcs_bucket),
        hf_hub_client=RealHFHubClient(),
    )


def _docker_client_for(settings: WorkerSettings) -> DockerClient:
    # Always a real DockerRunner: even a "fake adapters" standalone smoke
    # test still needs to see a real container come and go, since that's
    # most of what the worker loop actually does.
    from worker.docker_runner import DockerRunner

    return DockerRunner()
