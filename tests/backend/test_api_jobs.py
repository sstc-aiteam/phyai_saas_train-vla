import json


VALID_INFO_JSON = json.dumps(
    {
        "features": {
            "observation.state": {"shape": [14]},
            "action": {"shape": [7]},
        }
    }
).encode("utf-8")


def test_submit_hf_dataset_and_list_jobs(client, auth_headers, fakes):
    headers = auth_headers()
    fakes.hf_hub_client.add_repo(
        "org/dataset",
        {
            "meta/info.json": VALID_INFO_JSON,
            "data/chunk-000/episode_000000.parquet": b"x",
        },
    )

    response = client.post(
        "/uploads/hf-dataset",
        json={"repo_id": "org/dataset", "policy": "act", "training_steps": 1000},
        headers=headers,
    )
    assert response.status_code == 200
    job = response.json()
    assert job["status"] == "queued"

    jobs_response = client.get("/jobs", headers=headers)
    assert jobs_response.status_code == 200
    assert len(jobs_response.json()) == 1


def test_submit_hf_dataset_unknown_repo_returns_404(client, auth_headers):
    headers = auth_headers()
    response = client.post(
        "/uploads/hf-dataset",
        json={"repo_id": "org/missing", "policy": "act", "training_steps": 1000},
        headers=headers,
    )
    assert response.status_code == 404


def test_second_concurrent_job_returns_429(client, auth_headers, fakes):
    headers = auth_headers()
    fakes.hf_hub_client.add_repo(
        "org/dataset",
        {"meta/info.json": VALID_INFO_JSON, "data/x.parquet": b"x"},
    )
    body = {"repo_id": "org/dataset", "policy": "act", "training_steps": 1000}
    first = client.post("/uploads/hf-dataset", json=body, headers=headers)
    assert first.status_code == 200

    second = client.post("/uploads/hf-dataset", json=body, headers=headers)
    assert second.status_code == 429


def test_cancel_job(client, auth_headers, fakes):
    headers = auth_headers()
    fakes.hf_hub_client.add_repo(
        "org/dataset",
        {"meta/info.json": VALID_INFO_JSON, "data/x.parquet": b"x"},
    )
    created = client.post(
        "/uploads/hf-dataset",
        json={"repo_id": "org/dataset", "policy": "act", "training_steps": 1000},
        headers=headers,
    ).json()

    response = client.post(f"/jobs/{created['id']}/cancel", headers=headers)
    assert response.status_code == 200


def test_cancel_someone_elses_job_returns_403(client, auth_headers, fakes):
    headers_a = auth_headers("a@example.com")
    fakes.hf_hub_client.add_repo(
        "org/dataset",
        {"meta/info.json": VALID_INFO_JSON, "data/x.parquet": b"x"},
    )
    created = client.post(
        "/uploads/hf-dataset",
        json={"repo_id": "org/dataset", "policy": "act", "training_steps": 1000},
        headers=headers_a,
    ).json()

    headers_b = auth_headers("b@example.com")
    response = client.post(f"/jobs/{created['id']}/cancel", headers=headers_b)
    assert response.status_code == 403


def test_download_url_before_completion_returns_409(client, auth_headers, fakes):
    headers = auth_headers()
    fakes.hf_hub_client.add_repo(
        "org/dataset",
        {"meta/info.json": VALID_INFO_JSON, "data/x.parquet": b"x"},
    )
    created = client.post(
        "/uploads/hf-dataset",
        json={"repo_id": "org/dataset", "policy": "act", "training_steps": 1000},
        headers=headers,
    ).json()

    response = client.get(f"/jobs/{created['id']}/download-url", headers=headers)
    assert response.status_code == 409


def test_internal_check_timeouts_requires_secret(client):
    response = client.post("/internal/check-timeouts")
    assert response.status_code == 401


def test_internal_check_timeouts_with_valid_secret(client):
    response = client.post(
        "/internal/check-timeouts", headers={"X-Scheduler-Secret": "test-scheduler-secret"}
    )
    assert response.status_code == 200
    assert response.json() == {"failed_job_ids": []}
