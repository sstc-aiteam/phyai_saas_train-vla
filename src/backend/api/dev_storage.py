"""Dev-only stand-in for GCS: turns `InMemoryObjectStorage`'s "signed" URLs
into real PUT/GET endpoints on the backend itself, so a manual test can
`curl -T dataset.zip <upload_url>` a dataset without any real cloud bucket.

Only mounted by `backend.main.build_app` when `Settings.use_fake_adapters`
is true — never registered against a real deployment.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from backend.adapters.memory import InMemoryObjectStorage

router = APIRouter(prefix="/dev-storage", tags=["dev-storage"])


def _in_memory_storage(request: Request) -> InMemoryObjectStorage:
    storage = request.app.state.deps.storage
    if not isinstance(storage, InMemoryObjectStorage):
        raise HTTPException(status_code=404, detail="Dev storage is only available with in-memory adapters")
    return storage


@router.put("/{object_path:path}")
async def put_object(object_path: str, request: Request) -> Response:
    body = await request.body()
    _in_memory_storage(request).put_bytes(object_path, body)
    return Response(status_code=204)


@router.get("/{object_path:path}")
def get_object(object_path: str, request: Request) -> Response:
    storage = _in_memory_storage(request)
    try:
        with storage.open_read_stream(object_path) as stream:
            data = stream.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Object not found") from None
    return Response(content=data, media_type="application/octet-stream")
