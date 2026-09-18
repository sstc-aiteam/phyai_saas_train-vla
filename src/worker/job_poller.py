"""Main queue-draining logic (spec sections 3.5 and 6).

Each poll tick:
1. Process cancellations first (frees a would-be-started queued job without
   ever touching Docker or the daily quota).
2. If a job is already `initializing`/`training`, do nothing else — the
   host only ever runs one training container at a time.
3. Otherwise, start the oldest remaining `queued` job: build its
   ContainerSpec from policy/training_steps, launch the container, record
   the daily-quota consumption (a container has now actually started), and
   move the job to `initializing`.
"""

from __future__ import annotations

import dataclasses

from common.domain import job_state_machine, quota
from common.models import Job, JobStatus, PolicyType, utcnow
from common.ports.docker_client import ContainerSpec, DockerClient
from common.ports.job_repository import JobRepository
from common.ports.user_repository import UserRepository

from worker.cancel_watcher import process_cancellations

_ACTIVE_CONTAINER_STATUSES = (JobStatus.INITIALIZING, JobStatus.TRAINING)


class UserMissingError(Exception):
    pass


class JobPoller:
    def __init__(
        self,
        job_repository: JobRepository,
        user_repository: UserRepository,
        docker_client: DockerClient,
        act_image: str,
        smolvla_image: str,
        workdir: str,
        now_fn=utcnow,
    ) -> None:
        self._jobs = job_repository
        self._users = user_repository
        self._docker = docker_client
        self._images = {PolicyType.ACT: act_image, PolicyType.SMOLVLA: smolvla_image}
        self._workdir = workdir
        self._now = now_fn

    def tick(self) -> Job | None:
        """Run one poll cycle. Returns the job that was newly started, if any."""
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

        spec = self._build_container_spec(job)
        container_id = self._docker.run(spec)

        started_job = job_state_machine.transition(job, JobStatus.INITIALIZING, now=now)
        started_job = dataclasses.replace(started_job, container_id=container_id, heartbeat_at=now)
        self._jobs.update(started_job)

        self._users.update(quota.record_job_started(user, now.date()))

        return started_job

    def _build_container_spec(self, job: Job) -> ContainerSpec:
        job_dir = f"{self._workdir}/{job.id}"
        return ContainerSpec(
            image=self._images[job.policy],
            name=f"lerobot-job-{job.id}",
            command=[
                "python",
                "train_entrypoint.py",
                "--source-type",
                job.source_type.value,
                "--source-ref",
                job.source_ref,
                "--training-steps",
                str(job.training_steps),
                "--output-dir",
                "/workspace/output",
            ],
            volumes={job_dir: "/workspace"},
            environment={"JOB_ID": job.id},
            labels={"lerobot.job_id": job.id},
            use_gpu=True,
        )
