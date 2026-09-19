"""Main queue-draining logic (spec sections 3.5 and 6).

Each poll tick:
1. Process cancellations first (frees a would-be-started queued job without
   ever touching Docker or the daily quota).
2. If a job is already `initializing`/`training`, do nothing else — the
   host only ever runs one training container at a time.
3. Otherwise, start the oldest remaining `queued` job: moving it to
   `initializing` is what marks the daily quota as consumed (spec: "容器已
   啟動後...計入額度" — "initializing" is defined as covering data
   download/prep, spec section 3.5), *then* fetch its dataset and launch
   the container. A fetch or launch failure marks the job `failed` (moving
   through `initializing` first is required either way, since `queued` ->
   `failed` isn't a valid direct transition) but the quota charge stands,
   matching "container 已啟動後...失敗:計入額度".
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from common.domain import job_state_machine, quota
from common.models import Job, JobStatus, PolicyType, utcnow
from common.ports.docker_client import ContainerSpec, DockerClient
from common.ports.job_repository import JobRepository
from common.ports.user_repository import UserRepository

from worker.cancel_watcher import process_cancellations
from worker.dataset_fetcher import DatasetFetcher, DatasetFetchError, FetchedDataset

_ACTIVE_CONTAINER_STATUSES = (JobStatus.INITIALIZING, JobStatus.TRAINING)


class UserMissingError(Exception):
    pass


class JobPoller:
    def __init__(
        self,
        job_repository: JobRepository,
        user_repository: UserRepository,
        docker_client: DockerClient,
        dataset_fetcher: DatasetFetcher,
        act_image: str,
        smolvla_image: str,
        workdir: str,
        now_fn=utcnow,
    ) -> None:
        self._jobs = job_repository
        self._users = user_repository
        self._docker = docker_client
        self._dataset_fetcher = dataset_fetcher
        self._images = {PolicyType.ACT: act_image, PolicyType.SMOLVLA: smolvla_image}
        self._workdir = workdir
        self._now = now_fn

    def tick(self) -> Job | None:
        """Run one poll cycle. Returns the job that was newly started or
        failed-during-startup, if any."""
        process_cancellations(self._jobs, self._docker, now_fn=self._now)

        if self._jobs.list_by_statuses(_ACTIVE_CONTAINER_STATUSES):
            return None  # a training container is already occupying the GPU

        return self._start_next_queued_job()

    def _start_next_queued_job(self) -> Job | None:
        queued_jobs = self._jobs.list_by_statuses((JobStatus.QUEUED,))
        if not queued_jobs:
            return None

        job = queued_jobs[0]
        now = self._now()

        user = self._users.get(job.user_id)
        if user is None:
            raise UserMissingError(job.user_id)

        job = job_state_machine.transition(job, JobStatus.INITIALIZING, now=now)
        job = dataclasses.replace(job, heartbeat_at=now)
        self._jobs.update(job)
        self._users.update(quota.record_job_started(user, now.date()))

        job_dir = f"{self._workdir}/{job.id}"

        try:
            dataset = self._dataset_fetcher.fetch_for_job(job, Path(job_dir))
        except DatasetFetchError as exc:
            return self._fail_during_start(job, f"Failed to fetch dataset: {exc}")

        spec = self._build_container_spec(job, job_dir, dataset)
        try:
            container_id = self._docker.run(spec)
        except Exception as exc:  # docker-py raises several distinct error types
            return self._fail_during_start(job, f"Failed to start training container: {exc}")

        job = dataclasses.replace(job, container_id=container_id)
        self._jobs.update(job)
        return job

    def _fail_during_start(self, job: Job, error_message: str) -> Job:
        failed = job_state_machine.transition(job, JobStatus.FAILED, now=self._now())
        failed = dataclasses.replace(failed, error_message=error_message)
        self._jobs.update(failed)
        return failed

    def _build_container_spec(self, job: Job, job_dir: str, dataset: FetchedDataset) -> ContainerSpec:
        input_host_path = str(dataset.input_dir)
        output_host_path = f"{job_dir}/output"

        volumes = {input_host_path: "/workspace/input", output_host_path: "/workspace/output"}
        read_only_paths = frozenset({input_host_path}) if dataset.read_only else frozenset()

        return ContainerSpec(
            image=self._images[job.policy],
            name=f"lerobot-job-{job.id}",
            # No "python train_entrypoint.py" prefix here: each image's
            # Dockerfile already sets that as its ENTRYPOINT, so `command`
            # only needs to be the args appended to it.
            command=[
                "--source-type",
                job.source_type.value,
                "--source-ref",
                job.source_ref,
                "--training-steps",
                str(job.training_steps),
                "--input-dir",
                "/workspace/input",
                "--output-dir",
                "/workspace/output",
            ],
            # Mount only these two subdirectories, not /workspace itself —
            # mounting the whole thing would shadow the entrypoint script
            # that's baked into the image at /workspace/train_entrypoint.py.
            # (DockerRunner pre-creates these host paths so they're owned by
            # the worker's own uid before the container's bind mount touches
            # them.)
            volumes=volumes,
            read_only_paths=read_only_paths,
            environment={"JOB_ID": job.id},
            labels={"lerobot.job_id": job.id},
            use_gpu=True,
        )
