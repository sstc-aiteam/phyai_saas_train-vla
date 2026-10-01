"""Port: Docker container lifecycle, used by the worker to run training containers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

# Every container this service starts (see worker/job_poller.py) carries this
# label. `DockerClient.list_running_container_ids()` implementations must
# filter to it -- this host may run other, unrelated Docker workloads, and
# `worker/orphan_reconciler.py` kills anything list_running_container_ids()
# returns that isn't a tracked job. An unfiltered "all running containers on
# this host" implementation has, in practice, killed an unrelated long-running
# service on a shared host; scoping to this label is the fix.
LEROBOT_JOB_ID_LABEL = "lerobot.job_id"


@dataclass(frozen=True)
class ContainerSpec:
    image: str
    name: str
    command: list[str]
    volumes: dict[str, str]  # host_path -> container_path
    environment: dict[str, str]
    labels: dict[str, str]
    use_gpu: bool = True
    # host paths (must be keys of `volumes`) to mount read-only — e.g. the
    # shared HF dataset cache, which no training container should mutate.
    read_only_paths: frozenset[str] = frozenset()


class DockerClient(ABC):
    @abstractmethod
    def run(self, spec: ContainerSpec) -> str:
        """Start a detached container and return its container id."""
        ...

    @abstractmethod
    def kill(self, container_id: str) -> None: ...

    @abstractmethod
    def is_running(self, container_id: str) -> bool: ...

    @abstractmethod
    def get_exit_code(self, container_id: str) -> int | None:
        """Return the container's exit code, or None if it's still running
        (or unknown/not found)."""
        ...

    @abstractmethod
    def get_logs(self, container_id: str, tail_lines: int = 50) -> str:
        """Return up to the last `tail_lines` lines of the container's
        combined stdout+stderr, for surfacing into a failed job's
        error_message. Empty string if the container/logs aren't found."""
        ...

    @abstractmethod
    def list_running_container_ids(self) -> list[str]:
        """List ids of currently-running containers *this service manages*
        (carrying the `LEROBOT_JOB_ID_LABEL` label) -- not every container on
        the host. See the module docstring above for why that scoping matters."""
        ...

    @abstractmethod
    def get_label(self, container_id: str, label: str) -> str | None: ...
