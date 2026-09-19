"""Real docker-py-backed DockerClient. Thin translation layer, not covered
by unit tests here (would need a real docker daemon) — see
common/ports/docker_client.py for the contract this must satisfy."""

from __future__ import annotations

import os
from pathlib import Path

import docker
from docker.types import DeviceRequest

from common.ports.docker_client import ContainerSpec, DockerClient


class DockerRunner(DockerClient):
    def __init__(self, client: docker.DockerClient | None = None) -> None:
        self._client = client or docker.from_env()

    def run(self, spec: ContainerSpec) -> str:
        # Pre-create bind-mount host paths ourselves (owned by the worker's
        # own uid:gid) before docker gets a chance to auto-create them as
        # root — otherwise the container's own `--user` below can't write
        # into a directory the docker daemon just created as root.
        for host_path in spec.volumes:
            Path(host_path).mkdir(parents=True, exist_ok=True)

        device_requests = [DeviceRequest(count=-1, capabilities=[["gpu"]])] if spec.use_gpu else None
        container = self._client.containers.run(
            spec.image,
            command=spec.command,
            name=spec.name,
            volumes={host: {"bind": container_path, "mode": "rw"} for host, container_path in spec.volumes.items()},
            environment=spec.environment,
            labels=spec.labels,
            device_requests=device_requests,
            # Run as the worker's own uid:gid rather than the image's
            # default (root): the worker process needs to read progress.json
            # and later package/delete the checkpoint dir the container
            # writes into the shared bind mount, which fails with a
            # permission error if the container wrote those as root.
            user=f"{os.getuid()}:{os.getgid()}",
            detach=True,
        )
        return container.id

    def kill(self, container_id: str) -> None:
        try:
            container = self._client.containers.get(container_id)
        except docker.errors.NotFound:
            return
        container.kill()

    def is_running(self, container_id: str) -> bool:
        try:
            container = self._client.containers.get(container_id)
        except docker.errors.NotFound:
            return False
        container.reload()
        return container.status == "running"

    def get_exit_code(self, container_id: str) -> int | None:
        try:
            container = self._client.containers.get(container_id)
        except docker.errors.NotFound:
            return None
        container.reload()
        if container.status == "running":
            return None
        return container.attrs["State"]["ExitCode"]

    def list_running_container_ids(self) -> list[str]:
        return [c.id for c in self._client.containers.list(filters={"status": "running"})]

    def get_label(self, container_id: str, label: str) -> str | None:
        try:
            container = self._client.containers.get(container_id)
        except docker.errors.NotFound:
            return None
        return container.labels.get(label)
