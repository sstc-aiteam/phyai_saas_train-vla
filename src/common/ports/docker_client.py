"""Port: Docker container lifecycle, used by the worker to run training containers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ContainerSpec:
    image: str
    name: str
    command: list[str]
    volumes: dict[str, str]  # host_path -> container_path
    environment: dict[str, str]
    labels: dict[str, str]
    use_gpu: bool = True


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
    def list_running_container_ids(self) -> list[str]:
        """List ids of all currently-running containers on this host."""
        ...

    @abstractmethod
    def get_label(self, container_id: str, label: str) -> str | None: ...
