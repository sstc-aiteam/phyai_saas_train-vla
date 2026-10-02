def test_allowed_origin_gets_cors_headers(client):
    response = client.options(
        "/jobs",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_preflight_allows_put_for_the_local_dev_storage_upload_path(client):
    # PUT is only ever hit on this API by the local dev_storage.py stand-in
    # for a GCS signed URL -- make sure it's not silently missing from the
    # allowlist (it was, initially: only GET/POST were allowed, which
    # breaks the zip-upload golden path against fake adapters in the
    # browser even though curl-level backend tests never exercise it).
    response = client.options(
        "/dev-storage/some/object",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "PUT",
        },
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "PUT" in response.headers["access-control-allow-methods"]


def test_disallowed_origin_gets_no_cors_headers(client):
    response = client.options(
        "/jobs",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in response.headers
