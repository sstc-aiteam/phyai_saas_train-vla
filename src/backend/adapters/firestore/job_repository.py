"""Real Firestore-backed JobRepository.

Thin translation layer only — all business rules live in
`common.domain.*`. Not covered by unit tests in this repo (would need a
Firestore emulator); keep this file small and obviously correct instead.
"""

from __future__ import annotations

from google.cloud import firestore

from common.models import Job, JobStatus, PolicyType, Progress, SourceType
from common.ports.job_repository import JobRepository

COLLECTION = "jobs"


def _job_to_doc(job: Job) -> dict:
    return {
        "user_id": job.user_id,
        "policy": job.policy.value,
        "source_type": job.source_type.value,
        "source_ref": job.source_ref,
        "training_steps": job.training_steps,
        "status": job.status.value,
        "container_id": job.container_id,
        "heartbeat_at": job.heartbeat_at,
        "progress": (
            None
            if job.progress is None
            else {
                "step": job.progress.step,
                "total_steps": job.progress.total_steps,
                "loss": job.progress.loss,
                "updated_at": job.progress.updated_at,
            }
        ),
        "cancel_requested": job.cancel_requested,
        "checkpoint_gcs_path": job.checkpoint_gcs_path,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def _doc_to_job(job_id: str, doc: dict) -> Job:
    progress_doc = doc.get("progress")
    progress = (
        None
        if not progress_doc
        else Progress(
            step=progress_doc["step"],
            total_steps=progress_doc["total_steps"],
            loss=progress_doc["loss"],
            updated_at=progress_doc["updated_at"],
        )
    )
    return Job(
        id=job_id,
        user_id=doc["user_id"],
        policy=PolicyType(doc["policy"]),
        source_type=SourceType(doc["source_type"]),
        source_ref=doc["source_ref"],
        training_steps=doc["training_steps"],
        status=JobStatus(doc["status"]),
        container_id=doc.get("container_id"),
        heartbeat_at=doc.get("heartbeat_at"),
        progress=progress,
        cancel_requested=doc.get("cancel_requested", False),
        checkpoint_gcs_path=doc.get("checkpoint_gcs_path"),
        error_message=doc.get("error_message"),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


class FirestoreJobRepository(JobRepository):
    def __init__(self, client: firestore.Client) -> None:
        self._collection = client.collection(COLLECTION)

    def get(self, job_id: str) -> Job | None:
        snapshot = self._collection.document(job_id).get()
        if not snapshot.exists:
            return None
        return _doc_to_job(job_id, snapshot.to_dict())

    def create(self, job: Job) -> None:
        self._collection.document(job.id).set(_job_to_doc(job))

    def update(self, job: Job) -> None:
        self._collection.document(job.id).set(_job_to_doc(job))

    def list_for_user(self, user_id: str) -> list[Job]:
        query = self._collection.where("user_id", "==", user_id).order_by("created_at")
        return [_doc_to_job(snap.id, snap.to_dict()) for snap in query.stream()]

    def list_by_statuses(self, statuses: tuple[JobStatus, ...]) -> list[Job]:
        status_values = [s.value for s in statuses]
        query = self._collection.where("status", "in", status_values).order_by("created_at")
        return [_doc_to_job(snap.id, snap.to_dict()) for snap in query.stream()]
