from __future__ import annotations

import itertools

from common.ports.docker_client import ContainerSpec, DockerClient


class FakeDockerClient(DockerClient):
    """In-memory container registry for testing the worker's orchestration
    logic without a real docker daemon."""

    def __init__(self) -> None:
        self._id_counter = itertools.count(1)
        self._running: dict[str, ContainerSpec] = {}
        self.killed: list[str] = []

    def run(self, spec: ContainerSpec) -> str:
        container_id = f"fake-container-{next(self._id_counter)}"
        self._running[container_id] = spec
        return container_id

    def kill(self, container_id: str) -> None:
        self._running.pop(container_id, None)
        self.killed.append(container_id)

    def is_running(self, container_id: str) -> bool:
        return container_id in self._running

    def list_running_container_ids(self) -> list[str]:
        return list(self._running.keys())

    def get_label(self, container_id: str, label: str) -> str | None:
        spec = self._running.get(container_id)
        if spec is None:
            return None
        return spec.labels.get(label)

    def seed_running_container(self, container_id: str, spec: ContainerSpec) -> None:
        """Simulate a container that was already running before the worker
        (re)started, e.g. left over from a previous worker process."""
        self._running[container_id] = spec

    def get_spec(self, container_id: str) -> ContainerSpec | None:
        return self._running.get(container_id)
